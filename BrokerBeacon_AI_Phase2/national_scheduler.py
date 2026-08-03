"""National, review-gated queue scheduler for Ember."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from ember_jobs import emit_event, enqueue, initialize, now_iso

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


def _recent_job_states(conn: sqlite3.Connection, cooldown_hours: int) -> set[str]:
    cutoff = (datetime.now() - timedelta(hours=max(1, cooldown_hours))).isoformat(timespec="seconds")
    rows = conn.execute(
        """select distinct upper(coalesce(state,'')) state from crawl_jobs
           where job_type='discovery_cycle'
             and status in ('Queued','Running','Completed')
             and coalesce(completed_at,updated_at,created_at)>=?""",
        (cutoff,),
    ).fetchall()
    return {str(row["state"] or "").upper() for row in rows if row["state"]}


def ranked_states(conn: sqlite3.Connection, exclude_states: set[str] | None = None) -> list[str]:
    """Prioritize never-run states, then the stalest and least-processed states."""
    rows = _state_rows(conn)
    excluded = {str(state).upper() for state in (exclude_states or set())}
    return sorted(
        [state for state in approved_states() if state not in excluded],
        key=lambda state: (
            0 if not rows.get(state, {}).get("last_run_at") else 1,
            rows.get(state, {}).get("last_run_at", ""),
            int(rows.get(state, {}).get("companies_processed", 0) or 0),
            state,
        ),
    )


def _cancel_duplicate_queued_states(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """select id,state,status from crawl_jobs
           where job_type='discovery_cycle' and status in ('Queued','Running')
           order by case when status='Running' then 0 else 1 end,id"""
    ).fetchall()
    seen: set[str] = set()
    duplicate_ids: list[int] = []
    for row in rows:
        state = str(row["state"] or "").upper()
        if state in seen and row["status"] == "Queued":
            duplicate_ids.append(int(row["id"]))
        else:
            seen.add(state)
    if not duplicate_ids:
        return 0
    stamp = now_iso()
    placeholders = ",".join("?" for _ in duplicate_ids)
    conn.execute(
        f"""update crawl_jobs set status='Cancelled',completed_at=?,updated_at=?,
            last_error='Superseded duplicate national state job'
            where id in ({placeholders}) and status='Queued'""",
        (stamp, stamp, *duplicate_ids),
    )
    conn.commit()
    emit_event(conn, "NationalQueueDeduplicated", f"Retired {len(duplicate_ids)} duplicate state hunts", detail={"jobs": duplicate_ids})
    return len(duplicate_ids)


def refill_national_queue(
    conn: sqlite3.Connection,
    *,
    target_depth: int | None = None,
    company_limit: int | None = None,
    contact_limit: int | None = None,
) -> list[int]:
    """Keep a bounded national queue full without repeating recently processed states."""
    initialize(conn)
    _cancel_duplicate_queued_states(conn)
    target = max(1, min(int(target_depth or os.getenv("EMBER_NATIONAL_QUEUE_DEPTH", "6")), 12))
    company_limit = max(1, min(int(company_limit or os.getenv("EMBER_COMPANY_LIMIT", "12")), 20))
    contact_limit = max(25, min(int(contact_limit or os.getenv("EMBER_CONTACT_LIMIT", "500")), 750))
    cooldown_hours = max(1, min(int(os.getenv("EMBER_STATE_COOLDOWN_HOURS", "12")), 168))

    active_rows = conn.execute(
        "select state from crawl_jobs where job_type='discovery_cycle' and status in ('Queued','Running')"
    ).fetchall()
    active_states = {str(row["state"] or "").upper() for row in active_rows}
    recent_states = _recent_job_states(conn, cooldown_hours)
    excluded = active_states | recent_states
    needed = max(0, target - len(active_rows))
    created: list[int] = []
    candidates = ranked_states(conn, excluded)

    for state in candidates:
        if needed <= 0:
            break
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
            detail={"jobs": created, "queue_target": target, "states": len(approved_states()), "cooldown_hours": cooldown_hours},
        )
    elif needed > 0:
        emit_event(
            conn,
            "NationalQueuePaused",
            "Ember paused because every approved state is active or inside its cooldown window",
            detail={
                "queue_target": target,
                "active_states": sorted(active_states),
                "recent_states": sorted(recent_states),
                "cooldown_hours": cooldown_hours,
            },
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
