"""Bounded autonomy engine for BrokerBeacon AI agents.

Allows agents to grow and improve the prospect warehouse within owner-defined
budgets, approved states, provider limits, and mandatory review gates.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from ai_intelligence import process_batch as process_ai_batch
from ai_orchestrator import initialize as init_agents, queue_task, record_feedback
from public_search_connector import build_queries
from website_enrichment import enqueue_search_results, run_batch as run_enrichment_batch

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists autonomy_policies(
    id integer primary key,
    policy_key text not null unique,
    enabled integer not null default 0,
    approved_states_json text not null default '[]',
    max_search_queries_per_day integer not null default 100,
    max_results_per_provider integer not null default 20,
    max_enrichment_pages_per_day integer not null default 1000,
    max_ai_tasks_per_day integer not null default 1000,
    max_daily_cost_cents integer not null default 1000,
    require_human_review integer not null default 1,
    allow_crm_promotion integer not null default 0,
    allow_outreach integer not null default 0,
    allow_permission_changes integer not null default 0,
    pause_on_error_rate integer not null default 25,
    created_at text not null,
    updated_at text not null
);
create table if not exists autonomy_runs(
    id integer primary key,
    policy_id integer not null,
    state text default '',
    status text not null default 'Queued',
    search_queries integer not null default 0,
    search_results integer not null default 0,
    enrichment_claimed integer not null default 0,
    enrichment_processed integer not null default 0,
    contacts_found integer not null default 0,
    ai_processed integer not null default 0,
    estimated_cost_cents integer not null default 0,
    decisions_json text not null default '[]',
    error text default '',
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    foreign key(policy_id) references autonomy_policies(id)
);
create table if not exists autonomy_daily_usage(
    usage_date text not null,
    policy_id integer not null,
    search_queries integer not null default 0,
    search_results integer not null default 0,
    enrichment_pages integer not null default 0,
    ai_tasks integer not null default 0,
    estimated_cost_cents integer not null default 0,
    primary key(usage_date,policy_id),
    foreign key(policy_id) references autonomy_policies(id)
);
create table if not exists autonomy_recommendations(
    id integer primary key,
    agent_key text not null,
    recommendation_type text not null,
    state text default '',
    title text not null,
    rationale text not null,
    payload_json text not null default '{}',
    confidence integer not null default 50,
    status text not null default 'Pending',
    created_at text not null,
    reviewed_at text default ''
);
create index if not exists idx_autonomy_runs_status on autonomy_runs(status,id desc);
create index if not exists idx_autonomy_recommendations_status on autonomy_recommendations(status,confidence desc,id desc);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    init_agents(conn)
    now = NOW()
    conn.execute(
        """insert into autonomy_policies(
           policy_key,enabled,approved_states_json,max_search_queries_per_day,
           max_results_per_provider,max_enrichment_pages_per_day,max_ai_tasks_per_day,
           max_daily_cost_cents,require_human_review,allow_crm_promotion,allow_outreach,
           allow_permission_changes,pause_on_error_rate,created_at,updated_at)
           values('default',0,'[]',100,20,1000,1000,1000,1,0,0,0,25,?,?)
           on conflict(policy_key) do nothing""",
        (now, now),
    )
    conn.commit()


def _today() -> str:
    return datetime.now().date().isoformat()


def get_policy(conn: sqlite3.Connection, policy_key: str = "default") -> dict:
    initialize(conn)
    row = conn.execute("select * from autonomy_policies where policy_key=?", (policy_key,)).fetchone()
    if not row:
        raise ValueError("Autonomy policy not found")
    policy = dict(row)
    policy["approved_states"] = json.loads(policy.pop("approved_states_json") or "[]")
    return policy


def update_policy(conn: sqlite3.Connection, policy_key: str, updates: dict) -> dict:
    initialize(conn)
    allowed = {
        "enabled", "approved_states", "max_search_queries_per_day", "max_results_per_provider",
        "max_enrichment_pages_per_day", "max_ai_tasks_per_day", "max_daily_cost_cents",
        "require_human_review", "allow_crm_promotion", "allow_outreach",
        "allow_permission_changes", "pause_on_error_rate",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ValueError("Unsupported autonomy setting: " + ", ".join(sorted(unknown)))
    current = get_policy(conn, policy_key)
    current.update(updates)
    states = []
    for value in current.get("approved_states") or []:
        state = str(value).strip().upper()
        if len(state) == 2 and state.isalpha() and state not in states:
            states.append(state)
    values = {
        "policy_key": policy_key,
        "enabled": int(bool(current["enabled"])),
        "approved_states_json": json.dumps(states),
        "max_search_queries_per_day": min(max(int(current["max_search_queries_per_day"]), 0), 10000),
        "max_results_per_provider": min(max(int(current["max_results_per_provider"]), 1), 100),
        "max_enrichment_pages_per_day": min(max(int(current["max_enrichment_pages_per_day"]), 0), 100000),
        "max_ai_tasks_per_day": min(max(int(current["max_ai_tasks_per_day"]), 0), 100000),
        "max_daily_cost_cents": min(max(int(current["max_daily_cost_cents"]), 0), 1000000),
        "require_human_review": int(bool(current["require_human_review"])),
        "allow_crm_promotion": int(bool(current["allow_crm_promotion"])),
        "allow_outreach": int(bool(current["allow_outreach"])),
        "allow_permission_changes": int(bool(current["allow_permission_changes"])),
        "pause_on_error_rate": min(max(int(current["pause_on_error_rate"]), 1), 100),
        "updated_at": NOW(),
    }
    conn.execute(
        """update autonomy_policies set enabled=:enabled,approved_states_json=:approved_states_json,
           max_search_queries_per_day=:max_search_queries_per_day,
           max_results_per_provider=:max_results_per_provider,
           max_enrichment_pages_per_day=:max_enrichment_pages_per_day,
           max_ai_tasks_per_day=:max_ai_tasks_per_day,max_daily_cost_cents=:max_daily_cost_cents,
           require_human_review=:require_human_review,allow_crm_promotion=:allow_crm_promotion,
           allow_outreach=:allow_outreach,allow_permission_changes=:allow_permission_changes,
           pause_on_error_rate=:pause_on_error_rate,updated_at=:updated_at where policy_key=:policy_key""",
        values,
    )
    conn.commit()
    return get_policy(conn, policy_key)


def _usage(conn: sqlite3.Connection, policy_id: int) -> dict:
    row = conn.execute(
        "select * from autonomy_daily_usage where usage_date=? and policy_id=?",
        (_today(), policy_id),
    ).fetchone()
    if row:
        return dict(row)
    conn.execute(
        "insert into autonomy_daily_usage(usage_date,policy_id) values(?,?)",
        (_today(), policy_id),
    )
    conn.commit()
    return dict(conn.execute(
        "select * from autonomy_daily_usage where usage_date=? and policy_id=?",
        (_today(), policy_id),
    ).fetchone())


def _remaining(policy: dict, usage: dict) -> dict:
    return {
        "search_queries": max(0, policy["max_search_queries_per_day"] - usage["search_queries"]),
        "enrichment_pages": max(0, policy["max_enrichment_pages_per_day"] - usage["enrichment_pages"]),
        "ai_tasks": max(0, policy["max_ai_tasks_per_day"] - usage["ai_tasks"]),
        "cost_cents": max(0, policy["max_daily_cost_cents"] - usage["estimated_cost_cents"]),
    }


def choose_next_state(conn: sqlite3.Connection, policy: dict) -> str:
    states = policy.get("approved_states") or []
    if not states:
        return ""
    counts = {row[0]: int(row[1]) for row in conn.execute(
        "select state,count(*) from public_search_results group by state"
    )}
    failures = {row[0]: int(row[1]) for row in conn.execute(
        "select state,count(*) from autonomy_runs where status='Failed' group by state"
    )}
    return sorted(states, key=lambda state: (counts.get(state, 0), failures.get(state, 0), state))[0]


def create_recommendation(conn: sqlite3.Connection, *, agent_key: str,
                          recommendation_type: str, state: str, title: str,
                          rationale: str, payload: dict, confidence: int = 50) -> int:
    initialize(conn)
    cur = conn.execute(
        """insert into autonomy_recommendations(agent_key,recommendation_type,state,title,rationale,
           payload_json,confidence,created_at) values(?,?,?,?,?,?,?,?)""",
        (agent_key, recommendation_type, state, title[:240], rationale[:2000],
         json.dumps(payload, sort_keys=True, default=str), min(max(int(confidence), 0), 100), NOW()),
    )
    conn.commit()
    return int(cur.lastrowid)


def plan_cycle(conn: sqlite3.Connection, policy_key: str = "default") -> dict:
    policy = get_policy(conn, policy_key)
    usage = _usage(conn, policy["id"])
    remaining = _remaining(policy, usage)
    if not policy["enabled"]:
        return {"status": "Paused", "reason": "Autonomy is disabled", "remaining": remaining}
    state = choose_next_state(conn, policy)
    if not state:
        return {"status": "Paused", "reason": "No approved states configured", "remaining": remaining}
    actions = []
    if remaining["search_queries"] >= len(build_queries(state)) and remaining["cost_cents"] > 0:
        actions.append({"type": "discovery", "agent": "scout", "state": state})
    queued = conn.execute(
        "select count(*) from website_enrichment_queue where status='Queued' and state=?", (state,)
    ).fetchone()[0]
    if queued > 0 and remaining["enrichment_pages"] > 0:
        actions.append({"type": "enrichment", "agent": "scout", "state": state,
                        "batch_size": min(100, remaining["enrichment_pages"])})
    pending_ai = conn.execute(
        """select count(*) from discovered_contacts d left join ai_contact_insights a
           on a.discovered_contact_id=d.id where a.id is null and d.state=?""", (state,)
    ).fetchone()[0]
    if pending_ai > 0 and remaining["ai_tasks"] > 0:
        actions.append({"type": "ai_enrichment", "agent": "signal", "state": state,
                        "batch_size": min(100, remaining["ai_tasks"], pending_ai)})
    return {"status": "Ready", "state": state, "actions": actions, "remaining": remaining}


def run_cycle(conn: sqlite3.Connection, policy_key: str = "default") -> dict:
    initialize(conn)
    policy = get_policy(conn, policy_key)
    plan = plan_cycle(conn, policy_key)
    if plan["status"] != "Ready":
        return plan
    now = NOW()
    run_id = int(conn.execute(
        "insert into autonomy_runs(policy_id,state,status,created_at,started_at) values(?,?,'Running',?,?)",
        (policy["id"], plan["state"], now, now),
    ).lastrowid)
    decisions = []
    usage_delta = {"search_queries": 0, "search_results": 0, "enrichment_pages": 0,
                   "ai_tasks": 0, "estimated_cost_cents": 0}
    totals = {"enrichment_claimed": 0, "enrichment_processed": 0, "contacts_found": 0, "ai_processed": 0}
    try:
        for action in plan["actions"]:
            if action["type"] == "discovery":
                task_id = queue_task(conn, "scout", "autonomous_discovery", action, "state", None, 70)
                queries = len(build_queries(action["state"]))
                decisions.append({**action, "task_id": task_id, "status": "Queued"})
                usage_delta["search_queries"] += queries
            elif action["type"] == "enrichment":
                enqueue_search_results(conn, state=action["state"], limit=5000)
                result = run_enrichment_batch(conn, state=action["state"], batch_size=action["batch_size"])
                totals["enrichment_claimed"] += int(result.get("claimed", 0))
                totals["enrichment_processed"] += int(result.get("processed", 0))
                totals["contacts_found"] += int(result.get("contacts_found", 0))
                usage_delta["enrichment_pages"] += int(result.get("pages_fetched", 0))
                decisions.append({**action, "result": result, "status": "Completed"})
            elif action["type"] == "ai_enrichment":
                result = process_ai_batch(conn, limit=action["batch_size"])
                totals["ai_processed"] += int(result.get("processed", 0))
                usage_delta["ai_tasks"] += int(result.get("processed", 0))
                decisions.append({**action, "result": result, "status": "Completed"})
        usage_delta["estimated_cost_cents"] = max(0, usage_delta["ai_tasks"] + usage_delta["search_queries"])
        conn.execute(
            """insert into autonomy_daily_usage(usage_date,policy_id,search_queries,search_results,
               enrichment_pages,ai_tasks,estimated_cost_cents) values(?,?,?,?,?,?,?)
               on conflict(usage_date,policy_id) do update set
                 search_queries=search_queries+excluded.search_queries,
                 search_results=search_results+excluded.search_results,
                 enrichment_pages=enrichment_pages+excluded.enrichment_pages,
                 ai_tasks=ai_tasks+excluded.ai_tasks,
                 estimated_cost_cents=estimated_cost_cents+excluded.estimated_cost_cents""",
            (_today(), policy["id"], usage_delta["search_queries"], usage_delta["search_results"],
             usage_delta["enrichment_pages"], usage_delta["ai_tasks"], usage_delta["estimated_cost_cents"]),
        )
        finished = NOW()
        conn.execute(
            """update autonomy_runs set status='Completed',search_queries=?,search_results=?,
               enrichment_claimed=?,enrichment_processed=?,contacts_found=?,ai_processed=?,
               estimated_cost_cents=?,decisions_json=?,finished_at=? where id=?""",
            (usage_delta["search_queries"], usage_delta["search_results"], totals["enrichment_claimed"],
             totals["enrichment_processed"], totals["contacts_found"], totals["ai_processed"],
             usage_delta["estimated_cost_cents"], json.dumps(decisions, default=str), finished, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "state": plan["state"], "decisions": decisions, **totals,
                "estimated_cost_cents": usage_delta["estimated_cost_cents"]}
    except Exception as exc:
        conn.execute(
            "update autonomy_runs set status='Failed',error=?,decisions_json=?,finished_at=? where id=?",
            (str(exc)[:500], json.dumps(decisions, default=str), NOW(), run_id),
        )
        conn.commit()
        raise


def learn_from_outcomes(conn: sqlite3.Connection, limit: int = 500) -> dict:
    initialize(conn)
    rows = conn.execute(
        """select a.id insight_id,a.discovered_contact_id,a.opportunity_score,
           a.reviewed_status,d.state,d.source_domain from ai_contact_insights a
           join discovered_contacts d on d.id=a.discovered_contact_id
           where a.reviewed_status in ('Approved','Rejected') order by a.updated_at desc limit ?""",
        (min(max(int(limit), 1), 5000),),
    ).fetchall()
    accepted = rejected = 0
    by_domain: dict[str, dict[str, int]] = {}
    for row in rows:
        domain = row["source_domain"] or "unknown"
        stats = by_domain.setdefault(domain, {"approved": 0, "rejected": 0})
        if row["reviewed_status"] == "Approved":
            stats["approved"] += 1
            accepted += 1
        else:
            stats["rejected"] += 1
            rejected += 1
    for domain, stats in by_domain.items():
        total = stats["approved"] + stats["rejected"]
        if total < 3:
            continue
        approval_rate = round(stats["approved"] / total, 3)
        record_feedback(
            conn,
            "scout",
            task_id=None,
            rating=5 if approval_rate >= 0.75 else 2 if approval_rate < 0.25 else 3,
            outcome="source_quality",
            correction={f"source_domain:{domain}": {"approval_rate": approval_rate, "sample_size": total}},
            notes="Derived from owner review outcomes",
            approve_learning=True,
        )
    return {"records_evaluated": len(rows), "accepted": accepted, "rejected": rejected,
            "domains_learned": len(by_domain)}


def dashboard(conn: sqlite3.Connection, policy_key: str = "default") -> dict:
    initialize(conn)
    policy = get_policy(conn, policy_key)
    usage = _usage(conn, policy["id"])
    recent_runs = [dict(row) for row in conn.execute(
        "select * from autonomy_runs where policy_id=? order by id desc limit 20", (policy["id"],)
    )]
    recommendations = [dict(row) for row in conn.execute(
        "select * from autonomy_recommendations where status='Pending' order by confidence desc,id desc limit 50"
    )]
    for item in recommendations:
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
    return {"policy": policy, "usage": usage, "remaining": _remaining(policy, usage),
            "plan": plan_cycle(conn, policy_key), "recent_runs": recent_runs,
            "recommendations": recommendations}
