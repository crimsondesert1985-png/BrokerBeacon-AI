"""Standalone Ember queue worker entry point.

Run separately from Flask/Gunicorn:
    python ember_worker_service.py
"""
from __future__ import annotations

import os
import socket
import sqlite3
import time
from datetime import date
from typing import Any, Callable

from ember_hunt import launch
from ember_jobs import claim_next, complete, fail, heartbeat, initialize


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def handle_discovery_cycle(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    state = (payload.get("state") or job.get("state") or "").strip().upper()
    return launch(
        conn,
        state=state,
        company_limit=min(max(int(payload.get("company_limit", 6)), 1), 25),
        contact_limit=min(max(int(payload.get("contact_limit", 250)), 1), 1000),
    )


HANDLERS: dict[str, Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]]] = {
    "discovery_cycle": handle_discovery_cycle,
}


def run_forever(db_path: str, *, worker_key: str | None = None, poll_seconds: int = 5) -> None:
    worker_key = worker_key or f"ember-{socket.gethostname()}-{os.getpid()}"
    completed_today = 0
    completed_date = date.today()
    with connect(db_path) as conn:
        initialize(conn)
        heartbeat(conn, worker_key, status="Idle")

    while True:
        if completed_date != date.today():
            completed_date = date.today()
            completed_today = 0
        try:
            with connect(db_path) as conn:
                job = claim_next(conn, worker_key)
                if not job:
                    heartbeat(conn, worker_key, status="Idle", jobs_completed_today=completed_today)
                    time.sleep(max(1, poll_seconds))
                    continue

                heartbeat(
                    conn,
                    worker_key,
                    status="Running",
                    current_job_id=int(job["id"]),
                    jobs_completed_today=completed_today,
                )
                handler = HANDLERS.get(str(job["job_type"]))
                if handler is None:
                    raise ValueError(f"Unsupported Ember job type: {job['job_type']}")
                result = handler(conn, job)
                if not complete(conn, int(job["id"]), worker_key, detail=result):
                    raise RuntimeError(f"Could not complete claimed job #{job['id']}")
                completed_today += 1
                heartbeat(conn, worker_key, status="Idle", jobs_completed_today=completed_today)
        except KeyboardInterrupt:
            with connect(db_path) as conn:
                heartbeat(conn, worker_key, status="Stopped", jobs_completed_today=completed_today)
            return
        except Exception as exc:
            try:
                with connect(db_path) as conn:
                    if "job" in locals() and job:
                        fail(
                            conn,
                            int(job["id"]),
                            worker_key,
                            str(exc),
                            retry_delay_seconds=min(1800, 60 * (2 ** max(int(job.get("attempts", 1)) - 1, 0))),
                        )
                    heartbeat(
                        conn,
                        worker_key,
                        status="Failed",
                        jobs_completed_today=completed_today,
                        last_error=str(exc),
                    )
            finally:
                time.sleep(max(2, poll_seconds))


def main() -> None:
    db_path = os.getenv("BROKERBEACON_DB", "brokerbeacon.db")
    poll_seconds = max(1, int(os.getenv("EMBER_WORKER_POLL_SECONDS", "5")))
    run_forever(db_path, poll_seconds=poll_seconds)


if __name__ == "__main__":
    main()
