"""Adaptive AI orchestrator for BrokerBeacon.

Agents have distinct roles and personalities, but they do not self-modify code.
They improve through approved feedback, outcome metrics, and versioned memory.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists ai_agents(
    id integer primary key,
    agent_key text not null unique,
    display_name text not null,
    role text not null,
    personality text not null,
    system_prompt text not null,
    preferred_model text default '',
    enabled integer not null default 1,
    version integer not null default 1,
    created_at text not null,
    updated_at text not null
);
create table if not exists ai_tasks(
    id integer primary key,
    agent_id integer not null,
    task_type text not null,
    entity_type text default '',
    entity_id integer,
    priority integer not null default 50,
    status text not null default 'Queued',
    input_json text not null default '{}',
    output_json text not null default '{}',
    model text default '',
    attempts integer not null default 0,
    error text default '',
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    foreign key(agent_id) references ai_agents(id)
);
create table if not exists ai_agent_memory(
    id integer primary key,
    agent_id integer not null,
    memory_type text not null,
    memory_key text not null,
    value_json text not null,
    confidence integer not null default 50,
    source text not null default 'system',
    approved integer not null default 0,
    created_at text not null,
    updated_at text not null,
    unique(agent_id,memory_type,memory_key),
    foreign key(agent_id) references ai_agents(id)
);
create table if not exists ai_feedback(
    id integer primary key,
    agent_id integer not null,
    task_id integer,
    rating integer,
    outcome text default '',
    correction_json text not null default '{}',
    notes text default '',
    approved_for_learning integer not null default 0,
    created_at text not null,
    foreign key(agent_id) references ai_agents(id),
    foreign key(task_id) references ai_tasks(id)
);
create table if not exists ai_agent_metrics(
    agent_id integer primary key,
    tasks_completed integer not null default 0,
    tasks_failed integer not null default 0,
    average_rating real not null default 0,
    accepted_outcomes integer not null default 0,
    rejected_outcomes integer not null default 0,
    last_task_at text default '',
    updated_at text not null,
    foreign key(agent_id) references ai_agents(id)
);
create index if not exists idx_ai_tasks_queue on ai_tasks(status,priority desc,id);
create index if not exists idx_ai_feedback_learning on ai_feedback(approved_for_learning,agent_id,id);
"""

DEFAULT_AGENTS = (
    {
        "agent_key": "scout",
        "display_name": "Scout",
        "role": "Discovery analyst",
        "personality": "Curious, persistent, evidence-first, concise",
        "system_prompt": "Find and classify mortgage prospects. Preserve provenance. Never invent missing facts.",
        "preferred_model": "gpt-5-mini",
    },
    {
        "agent_key": "atlas",
        "display_name": "Atlas",
        "role": "Entity resolution specialist",
        "personality": "Methodical, skeptical, detail-oriented",
        "system_prompt": "Resolve companies, branches, and people into canonical entities. Prefer stable identifiers and explain uncertainty.",
        "preferred_model": "gpt-5-mini",
    },
    {
        "agent_key": "signal",
        "display_name": "Signal",
        "role": "Prospect intelligence analyst",
        "personality": "Analytical, commercially minded, transparent",
        "system_prompt": "Score opportunity, territory fit, and product fit using only available evidence. Explain every score.",
        "preferred_model": "gpt-5-mini",
    },
    {
        "agent_key": "coach",
        "display_name": "Coach",
        "role": "Sales preparation specialist",
        "personality": "Encouraging, practical, respectful, direct",
        "system_prompt": "Prepare useful outreach guidance without overstating facts or initiating outreach automatically.",
        "preferred_model": "gpt-5-mini",
    },
    {
        "agent_key": "ash",
        "display_name": "Ash",
        "role": "Executive orchestrator",
        "personality": "Warm, strategic, decisive, ownership-minded",
        "system_prompt": "Coordinate specialist agents, prioritize work, surface risks, and recommend the next best operational action.",
        "preferred_model": "gpt-5",
    },
)


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    now = NOW()
    for agent in DEFAULT_AGENTS:
        conn.execute(
            """insert into ai_agents(agent_key,display_name,role,personality,system_prompt,preferred_model,created_at,updated_at)
               values(:agent_key,:display_name,:role,:personality,:system_prompt,:preferred_model,:now,:now)
               on conflict(agent_key) do nothing""",
            {**agent, "now": now},
        )
    conn.commit()


def queue_task(conn: sqlite3.Connection, agent_key: str, task_type: str, payload: dict,
               entity_type: str = "", entity_id: int | None = None, priority: int = 50) -> int:
    initialize(conn)
    agent = conn.execute("select id from ai_agents where agent_key=? and enabled=1", (agent_key,)).fetchone()
    if not agent:
        raise ValueError("AI agent is unavailable")
    cur = conn.execute(
        """insert into ai_tasks(agent_id,task_type,entity_type,entity_id,priority,input_json,created_at)
           values(?,?,?,?,?,?,?)""",
        (agent[0], task_type, entity_type, entity_id, min(max(int(priority), 1), 100),
         json.dumps(payload, sort_keys=True, default=str), NOW()),
    )
    conn.commit()
    return int(cur.lastrowid)


def route_task(task_type: str) -> str:
    task_type = (task_type or "").lower()
    if any(x in task_type for x in ("discover", "classify", "search")):
        return "scout"
    if any(x in task_type for x in ("duplicate", "resolve", "canonical", "merge")):
        return "atlas"
    if any(x in task_type for x in ("score", "fit", "opportunity", "priority")):
        return "signal"
    if any(x in task_type for x in ("script", "outreach", "talking", "coach")):
        return "coach"
    return "ash"


def record_feedback(conn: sqlite3.Connection, agent_key: str, *, task_id: int | None,
                    rating: int | None, outcome: str, correction: dict | None = None,
                    notes: str = "", approve_learning: bool = False) -> int:
    initialize(conn)
    agent = conn.execute("select id from ai_agents where agent_key=?", (agent_key,)).fetchone()
    if not agent:
        raise ValueError("Unknown AI agent")
    if rating is not None and not 1 <= int(rating) <= 5:
        raise ValueError("Rating must be between 1 and 5")
    cur = conn.execute(
        """insert into ai_feedback(agent_id,task_id,rating,outcome,correction_json,notes,
           approved_for_learning,created_at) values(?,?,?,?,?,?,?,?)""",
        (agent[0], task_id, rating, outcome[:80], json.dumps(correction or {}, sort_keys=True),
         notes[:1000], int(bool(approve_learning)), NOW()),
    )
    conn.commit()
    return int(cur.lastrowid)


def learn_from_approved_feedback(conn: sqlite3.Connection, agent_key: str, limit: int = 100) -> dict:
    """Convert approved corrections into versioned agent memory.

    This is supervised adaptation, not autonomous prompt rewriting.
    """
    initialize(conn)
    agent = conn.execute("select * from ai_agents where agent_key=?", (agent_key,)).fetchone()
    if not agent:
        raise ValueError("Unknown AI agent")
    rows = conn.execute(
        """select * from ai_feedback where agent_id=? and approved_for_learning=1
           order by id desc limit ?""",
        (agent["id"], min(max(int(limit), 1), 1000)),
    ).fetchall()
    learned = 0
    for row in rows:
        correction = json.loads(row["correction_json"] or "{}")
        for key, value in correction.items():
            memory_key = str(key)[:160]
            conn.execute(
                """insert into ai_agent_memory(agent_id,memory_type,memory_key,value_json,confidence,source,
                   approved,created_at,updated_at) values(?,?,?,?,?,'approved_feedback',1,?,?)
                   on conflict(agent_id,memory_type,memory_key) do update set
                     value_json=excluded.value_json,confidence=min(100,ai_agent_memory.confidence+5),
                     source=excluded.source,approved=1,updated_at=excluded.updated_at""",
                (agent["id"], "preference", memory_key, json.dumps(value, default=str), 70, NOW(), NOW()),
            )
            learned += 1
    if learned:
        conn.execute("update ai_agents set version=version+1,updated_at=? where id=?", (NOW(), agent["id"]))
    conn.commit()
    return {"agent": agent_key, "feedback_items": len(rows), "memories_updated": learned}


def agent_context(conn: sqlite3.Connection, agent_key: str) -> dict:
    initialize(conn)
    agent = conn.execute("select * from ai_agents where agent_key=?", (agent_key,)).fetchone()
    if not agent:
        raise ValueError("Unknown AI agent")
    memories = [dict(row) for row in conn.execute(
        """select memory_type,memory_key,value_json,confidence,source from ai_agent_memory
           where agent_id=? and approved=1 order by confidence desc,updated_at desc limit 50""",
        (agent["id"],),
    )]
    for memory in memories:
        memory["value"] = json.loads(memory.pop("value_json") or "null")
    return {"agent": dict(agent), "memories": memories}


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    agents = [dict(row) for row in conn.execute(
        """select a.*,coalesce(m.tasks_completed,0) tasks_completed,
           coalesce(m.tasks_failed,0) tasks_failed,coalesce(m.average_rating,0) average_rating
           from ai_agents a left join ai_agent_metrics m on m.agent_id=a.id order by a.id"""
    )]
    queue = {row[0]: row[1] for row in conn.execute("select status,count(*) from ai_tasks group by status")}
    return {"agents": agents, "queue": queue,
            "approved_memories": conn.execute("select count(*) from ai_agent_memory where approved=1").fetchone()[0]}
