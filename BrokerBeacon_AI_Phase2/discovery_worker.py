"""Background worker for Sprint 37 discovery operations.

Designed for a Render background worker or cron job. It processes bounded,
resumable website-enrichment batches and records a heartbeat for the unified
Scout Control Tower. The worker never promotes records into outreach.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime

from app import DB
from public_search_connector import initialize as init_public
from website_enrichment import (
    dashboard,
    enqueue_search_results,
    initialize as init_enrichment,
    run_batch,
)

NOW = lambda: datetime.now().isoformat(timespec="seconds")
STOP_REQUESTED = False

WORKER_SCHEMA = """
create table if not exists discovery_worker_heartbeat(
    worker_name text primary key,
    status text not null default 'Starting',
    pid integer not null default 0,
    last_started_at text default '',
    last_heartbeat_at text default '',
    last_completed_at text default '',
    last_job_id integer,
    batches_completed integer not null default 0,
    records_processed integer not null default 0,
    contacts_found integer not null default 0,
    last_error text default ''
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    try:
        conn.execute("pragma journal_mode=wal")
    except sqlite3.DatabaseError:
        pass
    conn.executescript(WORKER_SCHEMA)
    init_public(conn)
    init_enrichment(conn)
    return conn


def update_heartbeat(conn: sqlite3.Connection, worker_name: str, **fields) -> None:
    defaults = {
        "status": "Running",
        "pid": os.getpid(),
        "last_started_at": NOW(),
        "last_heartbeat_at": NOW(),
        "last_completed_at": "",
        "last_job_id": None,
        "batches_completed": 0,
        "records_processed": 0,
        "contacts_found": 0,
        "last_error": "",
    }
    existing = conn.execute(
        "select * from discovery_worker_heartbeat where worker_name=?", (worker_name,)
    ).fetchone()
    values = dict(existing) if existing else defaults
    values.update(fields)
    values["worker_name"] = worker_name
    conn.execute(
        """insert into discovery_worker_heartbeat(
           worker_name,status,pid,last_started_at,last_heartbeat_at,last_completed_at,
           last_job_id,batches_completed,records_processed,contacts_found,last_error)
           values(:worker_name,:status,:pid,:last_started_at,:last_heartbeat_at,:last_completed_at,
                  :last_job_id,:batches_completed,:records_processed,:contacts_found,:last_error)
           on conflict(worker_name) do update set
             status=excluded.status,pid=excluded.pid,last_started_at=excluded.last_started_at,
             last_heartbeat_at=excluded.last_heartbeat_at,last_completed_at=excluded.last_completed_at,
             last_job_id=excluded.last_job_id,batches_completed=excluded.batches_completed,
             records_processed=excluded.records_processed,contacts_found=excluded.contacts_found,
             last_error=excluded.last_error""",
        values,
    )
    conn.commit()


def _signal_handler(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def process_once(conn: sqlite3.Connection, *, worker_name: str, state: str,
                 enqueue_limit: int, batch_size: int, per_domain_limit: int,
                 delay_seconds: float) -> dict:
    enqueued = enqueue_search_results(conn, state=state, limit=enqueue_limit)
    result = run_batch(
        conn,
        state=state,
        batch_size=batch_size,
        per_domain_limit=per_domain_limit,
        delay_seconds=delay_seconds,
    )
    row = conn.execute(
        "select * from discovery_worker_heartbeat where worker_name=?", (worker_name,)
    ).fetchone()
    update_heartbeat(
        conn,
        worker_name,
        status="Idle",
        last_heartbeat_at=NOW(),
        last_completed_at=NOW(),
        last_job_id=result.get("job_id"),
        batches_completed=int((row["batches_completed"] if row else 0) or 0) + 1,
        records_processed=int((row["records_processed"] if row else 0) or 0) + int(result.get("processed", 0)),
        contacts_found=int((row["contacts_found"] if row else 0) or 0) + int(result.get("contacts_found", 0)),
        last_error="",
    )
    return {"enqueued": enqueued, **result}


def run_loop(args) -> int:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    with connect() as conn:
        update_heartbeat(
            conn,
            args.worker_name,
            status="Running",
            pid=os.getpid(),
            last_started_at=NOW(),
            last_heartbeat_at=NOW(),
            last_error="",
        )
        while not STOP_REQUESTED:
            try:
                result = process_once(
                    conn,
                    worker_name=args.worker_name,
                    state=args.state,
                    enqueue_limit=args.enqueue_limit,
                    batch_size=args.batch_size,
                    per_domain_limit=args.per_domain_limit,
                    delay_seconds=args.delay_seconds,
                )
                print(json.dumps({"timestamp": NOW(), **result}), flush=True)
                update_heartbeat(conn, args.worker_name, status="Idle", last_heartbeat_at=NOW())
                if args.once:
                    return 0
                if int(result.get("claimed", 0)) == 0:
                    time.sleep(args.idle_seconds)
            except Exception as exc:
                update_heartbeat(
                    conn,
                    args.worker_name,
                    status="Error",
                    last_heartbeat_at=NOW(),
                    last_error=str(exc)[:500],
                )
                print(json.dumps({"timestamp": NOW(), "error": str(exc)}), file=sys.stderr, flush=True)
                if args.once:
                    return 1
                time.sleep(args.error_seconds)
        update_heartbeat(conn, args.worker_name, status="Stopped", last_heartbeat_at=NOW())
    return 0


def show_status() -> int:
    with connect() as conn:
        workers = [dict(row) for row in conn.execute(
            "select * from discovery_worker_heartbeat order by worker_name"
        )]
        print(json.dumps({"workers": workers, "enrichment": dashboard(conn)}, indent=2, default=str))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="BrokerBeacon discovery background worker")
    p.add_argument("command", choices=("run", "status"), nargs="?", default="run")
    p.add_argument("--worker-name", default=os.getenv("DISCOVERY_WORKER_NAME", "discovery-worker-1"))
    p.add_argument("--state", default=os.getenv("DISCOVERY_PILOT_STATE", ""))
    p.add_argument("--enqueue-limit", type=int, default=int(os.getenv("DISCOVERY_ENQUEUE_LIMIT", "5000")))
    p.add_argument("--batch-size", type=int, default=int(os.getenv("DISCOVERY_BATCH_SIZE", "100")))
    p.add_argument("--per-domain-limit", type=int, default=int(os.getenv("DISCOVERY_PER_DOMAIN_LIMIT", "3")))
    p.add_argument("--delay-seconds", type=float, default=float(os.getenv("DISCOVERY_DELAY_SECONDS", "0.4")))
    p.add_argument("--idle-seconds", type=float, default=float(os.getenv("DISCOVERY_IDLE_SECONDS", "30")))
    p.add_argument("--error-seconds", type=float, default=float(os.getenv("DISCOVERY_ERROR_SECONDS", "60")))
    p.add_argument("--once", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == "status":
        return show_status()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
