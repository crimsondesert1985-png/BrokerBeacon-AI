"""State connector registry and queue framework for Sprint 37.

Connectors describe approved data feeds; they do not scrape or activate outreach.
Every queued state import remains visible in the unified Scout Control Tower.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists state_connectors(
    id integer primary key,
    source_id integer not null,
    connector_key text not null unique,
    label text not null,
    connector_type text not null,
    states_json text not null default '[]',
    refresh_hours integer not null default 168,
    status text not null default 'Draft',
    health_status text not null default 'Not tested',
    last_checked_at text default '',
    last_success_at text default '',
    last_error text default '',
    created_at text not null,
    updated_at text not null,
    foreign key(source_id) references warehouse_sources(id)
);
create table if not exists state_import_queue(
    id integer primary key,
    connector_id integer not null,
    state text not null,
    status text not null default 'Queued',
    priority integer not null default 50,
    requested_by text default '',
    import_job_id integer,
    attempts integer not null default 0,
    next_attempt_at text default '',
    error text default '',
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    updated_at text not null,
    foreign key(connector_id) references state_connectors(id),
    foreign key(import_job_id) references warehouse_import_jobs(id)
);
create index if not exists idx_state_connectors_status on state_connectors(status,health_status);
create index if not exists idx_state_import_queue on state_import_queue(status,priority desc,id);
create unique index if not exists idx_state_import_active_unique
on state_import_queue(connector_id,state)
where status in ('Queued','Running','Retry scheduled');
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _states(values) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        state = str(value or "").strip().upper()
        if len(state) == 2 and state.isalpha() and state not in result:
            result.append(state)
    return result


def register_connector(conn: sqlite3.Connection, *, source_id: int, connector_key: str,
                       label: str, connector_type: str, states: list[str],
                       refresh_hours: int = 168, status: str = "Draft") -> int:
    initialize(conn)
    now = NOW()
    clean_states = _states(states)
    if not connector_key.strip() or not label.strip() or not connector_type.strip():
        raise ValueError("Connector key, label, and connector type are required")
    refresh_hours = min(max(int(refresh_hours), 1), 24 * 365)
    allowed = {"Draft", "Ready", "Paused", "Disabled"}
    if status not in allowed:
        raise ValueError("Invalid connector status")
    conn.execute(
        """insert into state_connectors(source_id,connector_key,label,connector_type,states_json,
           refresh_hours,status,created_at,updated_at) values(?,?,?,?,?,?,?,?,?)
           on conflict(connector_key) do update set source_id=excluded.source_id,label=excluded.label,
           connector_type=excluded.connector_type,states_json=excluded.states_json,
           refresh_hours=excluded.refresh_hours,status=excluded.status,updated_at=excluded.updated_at""",
        (source_id, connector_key.strip(), label.strip(), connector_type.strip(),
         json.dumps(clean_states), refresh_hours, status, now, now),
    )
    row = conn.execute("select id from state_connectors where connector_key=?", (connector_key.strip(),)).fetchone()
    conn.commit()
    return int(row[0])


def queue_state_import(conn: sqlite3.Connection, connector_id: int, state: str,
                       requested_by: str = "", priority: int = 50) -> int:
    initialize(conn)
    state = str(state or "").strip().upper()
    if len(state) != 2 or not state.isalpha():
        raise ValueError("A valid two-letter state is required")
    connector = conn.execute("select * from state_connectors where id=?", (connector_id,)).fetchone()
    if not connector:
        raise ValueError("Connector not found")
    if connector["status"] != "Ready":
        raise ValueError("Connector must be Ready before imports can be queued")
    supported = json.loads(connector["states_json"] or "[]")
    if supported and state not in supported and "*" not in supported:
        raise ValueError("Connector does not support this state")
    existing = conn.execute(
        """select id from state_import_queue where connector_id=? and state=?
           and status in ('Queued','Running','Retry scheduled') order by id desc limit 1""",
        (connector_id, state),
    ).fetchone()
    if existing:
        return int(existing[0])
    now = NOW()
    cur = conn.execute(
        """insert into state_import_queue(connector_id,state,priority,requested_by,created_at,updated_at)
           values(?,?,?,?,?,?)""",
        (connector_id, state, min(max(int(priority), 1), 100), requested_by[:160], now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def mark_connector_health(conn: sqlite3.Connection, connector_id: int, *, healthy: bool,
                          error: str = "") -> None:
    initialize(conn)
    now = NOW()
    conn.execute(
        """update state_connectors set health_status=?,last_checked_at=?,last_success_at=?,
           last_error=?,updated_at=? where id=?""",
        ("Healthy" if healthy else "Error", now, now if healthy else "", "" if healthy else error[:500], now, connector_id),
    )
    conn.commit()


def control_tower_status(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    connectors = [dict(row) for row in conn.execute(
        """select c.id,c.connector_key,c.label,c.connector_type,c.states_json,c.refresh_hours,c.status,
           c.health_status,c.last_checked_at,c.last_success_at,c.last_error,s.name source_name,
           s.authorization_basis from state_connectors c join warehouse_sources s on s.id=c.source_id
           order by c.status='Ready' desc,c.label"""
    )]
    for item in connectors:
        item["states"] = json.loads(item.pop("states_json") or "[]")
    queue = [dict(row) for row in conn.execute(
        """select q.id,q.connector_id,c.label connector_label,q.state,q.status,q.priority,
           q.requested_by,q.import_job_id,q.attempts,q.error,q.created_at,q.started_at,q.finished_at
           from state_import_queue q join state_connectors c on c.id=q.connector_id
           order by case q.status when 'Running' then 0 when 'Queued' then 1 when 'Retry scheduled' then 2 else 3 end,
           q.priority desc,q.id desc limit 100"""
    )]
    summary = {
        "connectors": len(connectors),
        "ready": sum(1 for item in connectors if item["status"] == "Ready"),
        "healthy": sum(1 for item in connectors if item["health_status"] == "Healthy"),
        "queued": sum(1 for item in queue if item["status"] in {"Queued", "Retry scheduled"}),
        "running": sum(1 for item in queue if item["status"] == "Running"),
        "failed": sum(1 for item in queue if item["status"] == "Failed"),
    }
    return {"summary": summary, "connectors": connectors, "queue": queue}
