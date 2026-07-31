"""Shared growth mission and reward system for BrokerBeacon AI agents.

The agents may adapt tactics within guardrails, but their objective is explicit:
maximize verified, unique, high-potential broker prospects and measurable
business opportunity while preserving provenance, quality, and owner control.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists growth_objectives(
    id integer primary key,
    objective_key text not null unique,
    mission text not null,
    active integer not null default 1,
    weight_unique_verified real not null default 1.0,
    weight_contactability real not null default 0.8,
    weight_opportunity real not null default 1.2,
    weight_business_outcome real not null default 1.5,
    penalty_duplicate real not null default 0.8,
    penalty_rejected real not null default 1.0,
    penalty_stale real not null default 0.4,
    minimum_quality_score integer not null default 55,
    created_at text not null,
    updated_at text not null
);
create table if not exists agent_strategy_variants(
    id integer primary key,
    agent_key text not null,
    strategy_key text not null,
    description text not null,
    parameters_json text not null default '{}',
    enabled integer not null default 1,
    trials integer not null default 0,
    accepted_prospects integer not null default 0,
    rejected_prospects integer not null default 0,
    unique_verified integer not null default 0,
    business_outcomes integer not null default 0,
    total_reward real not null default 0,
    last_used_at text default '',
    created_at text not null,
    updated_at text not null,
    unique(agent_key,strategy_key)
);
create table if not exists growth_outcomes(
    id integer primary key,
    agent_key text not null,
    strategy_key text default '',
    entity_type text default '',
    entity_id integer,
    outcome_type text not null,
    value real not null default 1,
    metadata_json text not null default '{}',
    created_at text not null
);
create table if not exists growth_experiments(
    id integer primary key,
    agent_key text not null,
    state text default '',
    experiment_type text not null,
    control_strategy text default '',
    challenger_strategy text not null,
    status text not null default 'Running',
    control_reward real not null default 0,
    challenger_reward real not null default 0,
    sample_size integer not null default 0,
    winner text default '',
    created_at text not null,
    finished_at text default ''
);
create index if not exists idx_growth_outcomes_agent on growth_outcomes(agent_key,strategy_key,created_at);
create index if not exists idx_growth_experiments_status on growth_experiments(status,agent_key,id desc);
"""

MISSION = (
    "Continuously grow BrokerBeacon's database by discovering as many legitimate, unique, "
    "contactable mortgage brokers, companies, branches, and loan officers as possible, while "
    "increasing measurable business opportunity. Favor verified, current, high-potential "
    "prospects over duplicate, stale, or low-confidence volume. Preserve source provenance, "
    "stay within owner-defined budgets and approved states, and keep CRM promotion and outreach "
    "behind the configured approval gates."
)

DEFAULT_STRATEGIES = (
    ("scout", "broad_state_discovery", "Broad multi-provider searches across an approved state", {"query_depth": "broad"}),
    ("scout", "metro_depth", "Deep searches across high-yield metros and nearby markets", {"query_depth": "metro"}),
    ("scout", "source_exploitation", "Prioritize domains and query patterns with strong approval yield", {"query_depth": "adaptive"}),
    ("atlas", "identifier_first", "Resolve entities using NMLS and stable identifiers first", {"match_mode": "identifier"}),
    ("atlas", "weighted_fuzzy", "Use weighted company, person, location, phone, and domain matching", {"match_mode": "weighted"}),
    ("signal", "quality_first", "Prioritize verified and contactable prospects", {"scoring_mode": "quality"}),
    ("signal", "growth_first", "Prioritize prospects with stronger business-growth signals", {"scoring_mode": "growth"}),
    ("ash", "coverage_balance", "Balance under-covered states with demonstrated source yield", {"planning_mode": "balanced"}),
)


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    now = NOW()
    conn.execute(
        """insert into growth_objectives(objective_key,mission,created_at,updated_at)
           values('primary',?,?,?) on conflict(objective_key) do update set mission=excluded.mission,updated_at=excluded.updated_at""",
        (MISSION, now, now),
    )
    for agent_key, strategy_key, description, params in DEFAULT_STRATEGIES:
        conn.execute(
            """insert into agent_strategy_variants(agent_key,strategy_key,description,parameters_json,created_at,updated_at)
               values(?,?,?,?,?,?) on conflict(agent_key,strategy_key) do nothing""",
            (agent_key, strategy_key, description, json.dumps(params, sort_keys=True), now, now),
        )
    conn.commit()


def objective(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    return dict(conn.execute("select * from growth_objectives where objective_key='primary'").fetchone())


def reward_for_outcomes(conn: sqlite3.Connection, outcomes: dict) -> float:
    goal = objective(conn)
    return round(
        float(outcomes.get("unique_verified", 0)) * goal["weight_unique_verified"]
        + float(outcomes.get("contactable", 0)) * goal["weight_contactability"]
        + float(outcomes.get("high_opportunity", 0)) * goal["weight_opportunity"]
        + float(outcomes.get("business_outcomes", 0)) * goal["weight_business_outcome"]
        - float(outcomes.get("duplicates", 0)) * goal["penalty_duplicate"]
        - float(outcomes.get("rejected", 0)) * goal["penalty_rejected"]
        - float(outcomes.get("stale", 0)) * goal["penalty_stale"],
        3,
    )


def record_strategy_result(conn: sqlite3.Connection, agent_key: str, strategy_key: str,
                           outcomes: dict) -> dict:
    initialize(conn)
    reward = reward_for_outcomes(conn, outcomes)
    conn.execute(
        """update agent_strategy_variants set trials=trials+1,
           accepted_prospects=accepted_prospects+?,rejected_prospects=rejected_prospects+?,
           unique_verified=unique_verified+?,business_outcomes=business_outcomes+?,
           total_reward=total_reward+?,last_used_at=?,updated_at=?
           where agent_key=? and strategy_key=?""",
        (int(outcomes.get("accepted", 0)), int(outcomes.get("rejected", 0)),
         int(outcomes.get("unique_verified", 0)), int(outcomes.get("business_outcomes", 0)),
         reward, NOW(), NOW(), agent_key, strategy_key),
    )
    for outcome_type, value in outcomes.items():
        if isinstance(value, (int, float)):
            conn.execute(
                """insert into growth_outcomes(agent_key,strategy_key,outcome_type,value,metadata_json,created_at)
                   values(?,?,?,?,?,?)""",
                (agent_key, strategy_key, outcome_type, float(value), "{}", NOW()),
            )
    conn.commit()
    return {"agent": agent_key, "strategy": strategy_key, "reward": reward, "outcomes": outcomes}


def choose_strategy(conn: sqlite3.Connection, agent_key: str, exploration_rate: float = 0.15) -> dict:
    """Select a strategy using a bounded explore/exploit policy.

    The agents may try alternatives, but only from enabled owner-visible strategies.
    """
    initialize(conn)
    rows = [dict(row) for row in conn.execute(
        "select * from agent_strategy_variants where agent_key=? and enabled=1 order by strategy_key",
        (agent_key,),
    )]
    if not rows:
        raise ValueError("No enabled strategy is available for this agent")
    import random
    if random.random() < min(max(float(exploration_rate), 0.0), 0.5):
        chosen = random.choice(rows)
        mode = "explore"
    else:
        def score(row):
            trials = max(int(row["trials"]), 1)
            return float(row["total_reward"]) / trials
        chosen = max(rows, key=score)
        mode = "exploit"
    chosen["parameters"] = json.loads(chosen.pop("parameters_json") or "{}")
    chosen["selection_mode"] = mode
    return chosen


def leaderboard(conn: sqlite3.Connection) -> list[dict]:
    initialize(conn)
    rows = [dict(row) for row in conn.execute(
        """select agent_key,strategy_key,description,trials,accepted_prospects,rejected_prospects,
           unique_verified,business_outcomes,total_reward,
           case when trials>0 then round(total_reward/trials,3) else 0 end average_reward,
           last_used_at from agent_strategy_variants order by agent_key,average_reward desc"""
    )]
    return rows


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    totals = conn.execute(
        """select count(*),coalesce(sum(unique_verified),0),coalesce(sum(accepted_prospects),0),
           coalesce(sum(rejected_prospects),0),coalesce(sum(business_outcomes),0),coalesce(sum(total_reward),0)
           from agent_strategy_variants"""
    ).fetchone()
    return {
        "mission": objective(conn),
        "strategies": leaderboard(conn),
        "summary": {
            "strategies": int(totals[0] or 0),
            "unique_verified": int(totals[1] or 0),
            "accepted": int(totals[2] or 0),
            "rejected": int(totals[3] or 0),
            "business_outcomes": int(totals[4] or 0),
            "total_reward": round(float(totals[5] or 0), 3),
        },
    }
