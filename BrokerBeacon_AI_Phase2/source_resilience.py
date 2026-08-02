"""Provider health and zero-yield circuit breaking for Ember discovery."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from multi_search_provider import configured_providers

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists ember_source_state(
    state text primary key,
    zero_yield_streak integer not null default 0,
    paused_until text not null default '',
    last_provider_status text not null default '',
    last_companies integer not null default 0,
    last_contacts integer not null default 0,
    last_run_at text not null default '',
    updated_at text not null
);
create index if not exists idx_ember_source_state_pause on ember_source_state(paused_until,state);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def state_available(conn: sqlite3.Connection, state: str, *, now: str | None = None) -> bool:
    initialize(conn)
    row = conn.execute("select paused_until from ember_source_state where state=?", (state.upper(),)).fetchone()
    return not row or not str(row[0] or '') or str(row[0]) <= (now or NOW())


def record_yield(conn: sqlite3.Connection, state: str, *, companies: int, contacts: int,
                 provider_status: str = '', threshold: int = 3, pause_hours: int = 6) -> dict:
    initialize(conn)
    state = state.upper()
    prior = conn.execute("select zero_yield_streak from ember_source_state where state=?", (state,)).fetchone()
    productive = int(companies) > 0 or int(contacts) > 0
    streak = 0 if productive else int(prior[0] if prior else 0) + 1
    paused_until = ''
    if not productive and streak >= max(1, int(threshold)):
        paused_until = (datetime.now() + timedelta(hours=max(1, int(pause_hours)))).isoformat(timespec="seconds")
    now = NOW()
    conn.execute(
        """insert into ember_source_state(state,zero_yield_streak,paused_until,last_provider_status,
           last_companies,last_contacts,last_run_at,updated_at) values(?,?,?,?,?,?,?,?)
           on conflict(state) do update set zero_yield_streak=excluded.zero_yield_streak,
           paused_until=excluded.paused_until,last_provider_status=excluded.last_provider_status,
           last_companies=excluded.last_companies,last_contacts=excluded.last_contacts,
           last_run_at=excluded.last_run_at,updated_at=excluded.updated_at""",
        (state, streak, paused_until, provider_status[:100], int(companies), int(contacts), now, now),
    )
    conn.commit()
    return {"state": state, "zero_yield_streak": streak, "paused": bool(paused_until), "paused_until": paused_until}


def source_health(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    now = NOW()
    rows = [dict(row) for row in conn.execute(
        "select * from ember_source_state order by case when paused_until>? then 0 else 1 end,updated_at desc,state",
        (now,),
    ).fetchall()]
    providers = configured_providers()
    return {
        "configured_providers": providers,
        "provider_count": len(providers),
        "search_ready": bool(providers),
        "paused_states": [row for row in rows if str(row.get("paused_until") or '') > now],
        "states": rows,
    }
