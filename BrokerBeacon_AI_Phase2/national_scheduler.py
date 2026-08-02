"""National, review-gated queue scheduler for Ember."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from ember_jobs import emit_event, enqueue, initialize

ALL_STATES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
)


def approved_states() -> list[str]:
    raw = os.getenv("EMBER_APPROVED_STATES", "ALL").strip().upper()
    if raw in {"", "ALL", "50", "NATIONAL"}:
        return list(ALL_STATES)
    requested = []
    for value in raw.split(","):
        state = value.strip().upper()
        if state in ALL_STATES and state not in requested:
            requested.append(state)
    return requested or list(ALL_STATES)


def _state_rows(conn: sqlite3.Connection) -> dict[str, dict]:
    try:
        return {row["state"]: dict(row) for row in conn.execute("select * from ember_state_cursors")}
    except sqlite3.OperationalError:
        return {}


def ranked_states(conn: sqlite3.Connection) -> list[str]:
    """Prioritize never-run states, then the stalest and least-processed states."""
    rows = _state_rows(conn)
    return sorted(
        approved_states(),
        key=lambda state: (
            0 if not rows.get(state, {}).get("last_run_at") else 1,
            rows.get(state, {}).get("last_run_at", ""),
            int(rows.get(state, {}).get("companies_processed", 0) or 0),
            state,
        ),
    )


def refill_national_queue(
    conn: sqlite3.Connection,
    *,
    target_depth: int | None = None,
    company_limit: int | None = None,
    contact_limit: int | None = None,
) -> list[int]:
    """Keep a bounded national queue full without duplicating active state jobs."""
    initialize(conn)
    target = max(1, min(int(target_depth or os.getenv("EMBER_NATIONAL_QUEUE_DEPTH", "6")), 12))
    company_limit = max(1, min(int(company_limit or os.getenv("EMBER_COMPANY_LIMIT", "8")), 12))
    contact_limit = max(25, min(int(contact_limit or os.getenv("EMBER_CONTACT_LIMIT", "350")), 500))

    active_rows = conn.execute(
        "select state from crawl_jobs where job_type='discovery_cycle' and status in ('Queued','Running')"
    ).fetchall()
    active_states = {str(row["state"] or "").upper() for row in active_rows}
    needed = max(0, target - len(active_rows))
    created: list[int] = []
    for state in ranked_states(conn):
        if needed <= 0:
            break
        if state in active_states:
            continue
        job_id = enqueue(
            conn,
            "discovery_cycle",
            state=state,
            payload={"state": state, "company_limit": company_limit, "contact_limit": contact_limit},
            priority=100 + len(created),
            max_attempts=3,
        )
        created.append(job_id)
        active_states.add(state)
        needed -= 1
    if created:
        emit_event(
            conn,
            "NationalQueueRefilled",
            f"Ember prepared {len(created)} state hunts",
            detail={"jobs": created, "queue_target": target, "states": len(approved_states())},
        )
    return created


def national_summary(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    states = approved_states()
    rows = _state_rows(conn)
    active = conn.execute(
        "select count(*) from crawl_jobs where job_type='discovery_cycle' and status in ('Queued','Running')"
    ).fetchone()[0]
    covered = sum(1 for state in states if rows.get(state, {}).get("last_run_at"))
    stale_cutoff = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    stale = sum(1 for state in states if rows.get(state, {}).get("last_run_at") and rows[state]["last_run_at"] < stale_cutoff)
    return {
        "enabled_states": len(states),
        "covered_states": covered,
        "remaining_states": max(0, len(states) - covered),
        "coverage_percent": round((covered / len(states)) * 100, 1) if states else 0,
        "active_state_jobs": int(active or 0),
        "stale_states": stale,
        "next_states": ranked_states(conn)[:5],
        "outreach_enabled": False,
        "human_review_required": True,
    }
