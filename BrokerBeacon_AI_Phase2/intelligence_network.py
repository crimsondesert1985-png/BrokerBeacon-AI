"""Shared intelligence graph, company profiles, growth planning, and voice feedback.

This module connects discoveries, companies, people, AI memories, strategies, and
business outcomes without changing source facts or bypassing review gates.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists intelligence_nodes(
    id integer primary key,
    node_type text not null,
    external_key text not null,
    label text not null,
    attributes_json text not null default '{}',
    confidence integer not null default 50,
    source text default '',
    created_at text not null,
    updated_at text not null,
    unique(node_type,external_key)
);
create table if not exists intelligence_edges(
    id integer primary key,
    from_node_id integer not null,
    relationship text not null,
    to_node_id integer not null,
    attributes_json text not null default '{}',
    confidence integer not null default 50,
    source text default '',
    created_at text not null,
    updated_at text not null,
    unique(from_node_id,relationship,to_node_id),
    foreign key(from_node_id) references intelligence_nodes(id),
    foreign key(to_node_id) references intelligence_nodes(id)
);
create table if not exists company_intelligence_profiles(
    id integer primary key,
    company_key text not null unique,
    company_name text not null,
    website text default '',
    states_json text not null default '[]',
    products_json text not null default '[]',
    leadership_json text not null default '[]',
    growth_signals_json text not null default '[]',
    hiring_signals_json text not null default '[]',
    technology_signals_json text not null default '[]',
    public_news_json text not null default '[]',
    opportunity_summary text default '',
    confidence integer not null default 50,
    last_refreshed_at text default '',
    created_at text not null,
    updated_at text not null
);
create table if not exists planner_cycles(
    id integer primary key,
    status text not null default 'Planned',
    selected_state text default '',
    selected_strategy text default '',
    rationale text default '',
    actions_json text not null default '[]',
    created_at text not null,
    executed_at text default ''
);
create table if not exists voice_outcomes(
    id integer primary key,
    prospect_type text default '',
    prospect_id integer,
    company_key text default '',
    agent_key text not null default 'coach',
    outcome text not null,
    disposition text default '',
    duration_seconds integer not null default 0,
    notes text default '',
    metadata_json text not null default '{}',
    approved_for_learning integer not null default 0,
    created_at text not null
);
create index if not exists idx_intelligence_nodes_type on intelligence_nodes(node_type,label);
create index if not exists idx_intelligence_edges_from on intelligence_edges(from_node_id,relationship);
create index if not exists idx_voice_outcomes_learning on voice_outcomes(approved_for_learning,agent_key,id);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_node(conn: sqlite3.Connection, node_type: str, external_key: str, label: str,
                attributes: dict | None = None, confidence: int = 50, source: str = "") -> int:
    initialize(conn)
    now = NOW()
    conn.execute(
        """insert into intelligence_nodes(node_type,external_key,label,attributes_json,confidence,source,created_at,updated_at)
           values(?,?,?,?,?,?,?,?) on conflict(node_type,external_key) do update set
           label=excluded.label,attributes_json=excluded.attributes_json,
           confidence=max(intelligence_nodes.confidence,excluded.confidence),
           source=excluded.source,updated_at=excluded.updated_at""",
        (node_type, external_key, label, json.dumps(attributes or {}, sort_keys=True, default=str),
         min(max(int(confidence), 0), 100), source, now, now),
    )
    row = conn.execute("select id from intelligence_nodes where node_type=? and external_key=?",
                       (node_type, external_key)).fetchone()
    conn.commit()
    return int(row[0])


def link_nodes(conn: sqlite3.Connection, from_id: int, relationship: str, to_id: int,
               attributes: dict | None = None, confidence: int = 50, source: str = "") -> int:
    initialize(conn)
    now = NOW()
    conn.execute(
        """insert into intelligence_edges(from_node_id,relationship,to_node_id,attributes_json,
           confidence,source,created_at,updated_at) values(?,?,?,?,?,?,?,?)
           on conflict(from_node_id,relationship,to_node_id) do update set
           attributes_json=excluded.attributes_json,
           confidence=max(intelligence_edges.confidence,excluded.confidence),
           source=excluded.source,updated_at=excluded.updated_at""",
        (from_id, relationship, to_id, json.dumps(attributes or {}, sort_keys=True, default=str),
         min(max(int(confidence), 0), 100), source, now, now),
    )
    row = conn.execute("select id from intelligence_edges where from_node_id=? and relationship=? and to_node_id=?",
                       (from_id, relationship, to_id)).fetchone()
    conn.commit()
    return int(row[0])


def sync_discoveries(conn: sqlite3.Connection, limit: int = 5000) -> dict:
    initialize(conn)
    rows = conn.execute(
        """select d.*,a.opportunity_score,a.confidence ai_confidence,a.canonical_company_name,a.canonical_person_name
           from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id
           order by d.id desc limit ?""", (min(max(int(limit), 1), 50000),)
    ).fetchall()
    companies = people = edges = 0
    for row in rows:
        company_name = (row["canonical_company_name"] or row["company_name"] or "").strip()
        if not company_name:
            continue
        company_key = (row["nmls_id"] or row["source_domain"] or company_name.lower()).strip()
        company_id = upsert_node(conn, "company", company_key, company_name,
                                 {"state": row["state"], "domain": row["source_domain"],
                                  "email": row["public_email"], "phone": row["phone"],
                                  "opportunity_score": row["opportunity_score"] or 0},
                                 row["ai_confidence"] or row["confidence"] or 50, row["source_url"])
        companies += 1
        person_name = (row["canonical_person_name"] or row["person_name"] or "").strip()
        if person_name:
            person_key = (row["nmls_id"] or f"{company_key}:{person_name.lower()}").strip()
            person_id = upsert_node(conn, "person", person_key, person_name,
                                    {"role": row["role"], "email": row["public_email"], "phone": row["phone"],
                                     "state": row["state"]}, row["ai_confidence"] or 60, row["source_url"])
            people += 1
            link_nodes(conn, person_id, "WORKS_AT", company_id, {"role": row["role"]}, 75, row["source_url"])
            edges += 1
    return {"records": len(rows), "company_nodes": companies, "person_nodes": people, "edges": edges}


def upsert_company_profile(conn: sqlite3.Connection, company_key: str, company_name: str, **fields) -> int:
    initialize(conn)
    now = NOW()
    def encoded(name):
        value = fields.get(name, [])
        return json.dumps(value if isinstance(value, list) else [value], sort_keys=True, default=str)
    conn.execute(
        """insert into company_intelligence_profiles(company_key,company_name,website,states_json,products_json,
           leadership_json,growth_signals_json,hiring_signals_json,technology_signals_json,public_news_json,
           opportunity_summary,confidence,last_refreshed_at,created_at,updated_at)
           values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) on conflict(company_key) do update set
           company_name=excluded.company_name,website=excluded.website,states_json=excluded.states_json,
           products_json=excluded.products_json,leadership_json=excluded.leadership_json,
           growth_signals_json=excluded.growth_signals_json,hiring_signals_json=excluded.hiring_signals_json,
           technology_signals_json=excluded.technology_signals_json,public_news_json=excluded.public_news_json,
           opportunity_summary=excluded.opportunity_summary,confidence=excluded.confidence,
           last_refreshed_at=excluded.last_refreshed_at,updated_at=excluded.updated_at""",
        (company_key, company_name, str(fields.get("website") or ""), encoded("states"), encoded("products"),
         encoded("leadership"), encoded("growth_signals"), encoded("hiring_signals"), encoded("technology_signals"),
         encoded("public_news"), str(fields.get("opportunity_summary") or ""),
         min(max(int(fields.get("confidence") or 50), 0), 100), now, now, now),
    )
    row = conn.execute("select id from company_intelligence_profiles where company_key=?", (company_key,)).fetchone()
    conn.commit()
    return int(row[0])


def plan_growth(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    policy = conn.execute("select * from autonomy_policies where policy_key='default'").fetchone()
    if not policy or not policy["enabled"]:
        return {"status": "Paused", "reason": "Autonomy is disabled"}
    approved = json.loads(policy["approved_states_json"] or "[]")
    if not approved:
        return {"status": "Paused", "reason": "No approved states configured"}
    coverage = {row[0]: row[1] for row in conn.execute(
        "select state,count(*) from discovered_contacts group by state")}
    yield_by_state = {row[0]: row[1] for row in conn.execute(
        """select d.state,avg(a.opportunity_score) from discovered_contacts d
           join ai_contact_insights a on a.discovered_contact_id=d.id group by d.state""
    )}
    selected = sorted(approved, key=lambda s: (coverage.get(s, 0), -(yield_by_state.get(s, 0) or 0), s))[0]
    strategy = "metro_depth" if coverage.get(selected, 0) > 500 else "broad_state_discovery"
    actions = [
        {"agent": "scout", "action": "discover", "state": selected, "strategy": strategy},
        {"agent": "atlas", "action": "resolve_entities", "state": selected},
        {"agent": "signal", "action": "score_new_contacts", "state": selected},
        {"agent": "ash", "action": "prepare_briefing", "state": selected},
    ]
    rationale = f"Selected {selected} because it has the lowest current coverage among approved states while preserving observed opportunity yield."
    cur = conn.execute(
        "insert into planner_cycles(status,selected_state,selected_strategy,rationale,actions_json,created_at) values('Planned',?,?,?,?,?)",
        (selected, strategy, rationale, json.dumps(actions, sort_keys=True), NOW()),
    )
    conn.commit()
    return {"status": "Planned", "cycle_id": int(cur.lastrowid), "state": selected,
            "strategy": strategy, "rationale": rationale, "actions": actions}


def record_voice_outcome(conn: sqlite3.Connection, *, prospect_type: str, prospect_id: int | None,
                         company_key: str, outcome: str, disposition: str = "", duration_seconds: int = 0,
                         notes: str = "", metadata: dict | None = None, approve_learning: bool = False) -> int:
    initialize(conn)
    cur = conn.execute(
        """insert into voice_outcomes(prospect_type,prospect_id,company_key,outcome,disposition,
           duration_seconds,notes,metadata_json,approved_for_learning,created_at)
           values(?,?,?,?,?,?,?,?,?,?)""",
        (prospect_type, prospect_id, company_key, outcome[:120], disposition[:120],
         max(int(duration_seconds), 0), notes[:2000], json.dumps(metadata or {}, sort_keys=True, default=str),
         int(bool(approve_learning)), NOW()),
    )
    conn.commit()
    return int(cur.lastrowid)


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    node_counts = {row[0]: row[1] for row in conn.execute("select node_type,count(*) from intelligence_nodes group by node_type")}
    edge_counts = {row[0]: row[1] for row in conn.execute("select relationship,count(*) from intelligence_edges group by relationship")}
    profiles = conn.execute("select count(*) from company_intelligence_profiles").fetchone()[0]
    learning_calls = conn.execute("select count(*) from voice_outcomes where approved_for_learning=1").fetchone()[0]
    recent_cycles = [dict(row) for row in conn.execute("select * from planner_cycles order by id desc limit 10")]
    for item in recent_cycles:
        item["actions"] = json.loads(item.pop("actions_json") or "[]")
    return {"nodes": node_counts, "edges": edge_counts, "company_profiles": int(profiles or 0),
            "approved_voice_outcomes": int(learning_calls or 0), "recent_plans": recent_cycles}
