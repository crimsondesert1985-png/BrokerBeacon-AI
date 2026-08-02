"""Always-on, review-gated Ember queue worker for BrokerBeacon."""
from __future__ import annotations

import os
import sqlite3
import threading
import time

from ember_hunt import launch
from ember_jobs import claim_next, complete, fail, heartbeat, initialize
from national_scheduler import refill_national_queue

_started = False
_start_lock = threading.Lock()
WORKER_KEY = "always-on-web"


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _seed_if_idle(conn):
    """Maintain a bounded multi-state backlog instead of one generic job."""
    return refill_national_queue(conn)


def _process_one(app, db_path):
    with _connect(db_path) as conn:
        _seed_if_idle(conn)
        job = claim_next(conn, WORKER_KEY, lease_seconds=1200)
        if not job:
            heartbeat(conn, WORKER_KEY, status="Idle")
            return
        heartbeat(conn, WORKER_KEY, status="Running", current_job_id=job["id"])
        try:
            payload = job.get("payload") or {}
            result = launch(
                conn,
                state=str(payload.get("state") or job.get("state") or "").strip().upper(),
                company_limit=min(max(int(payload.get("company_limit", 8)), 1), 25),
                contact_limit=min(max(int(payload.get("contact_limit", 350)), 1), 1000),
            )
            complete(conn, int(job["id"]), WORKER_KEY, detail=result)
            refill_national_queue(conn)
            heartbeat(conn, WORKER_KEY, status="Idle", jobs_completed_today=1)
            app.logger.warning(
                "EMBER_QUEUE completed job_id=%s state=%s companies=%s contacts=%s",
                job["id"], result.get("state", ""), result.get("companies_seeded", 0),
                (result.get("enrichment") or {}).get("contacts_found", 0),
            )
        except Exception as exc:
            fail(conn, int(job["id"]), WORKER_KEY, str(exc), retry_delay_seconds=120)
            refill_national_queue(conn)
            heartbeat(conn, WORKER_KEY, status="Failed", current_job_id=None, last_error=str(exc))
            app.logger.exception("EMBER_QUEUE job failed safely")


def install_ember_worker(app, db_path):
    """Start one queue-backed daemon loop per Gunicorn worker process."""
    global _started
    enabled = os.getenv("EMBER_ALWAYS_ON", "1").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        app.logger.warning("EMBER_QUEUE worker disabled")
        return
    with _start_lock:
        if _started:
            return
        _started = True

    interval = max(int(os.getenv("EMBER_LOOP_SECONDS", "300")), 180)

    def loop():
        with _connect(db_path) as conn:
            initialize(conn)
            refill_national_queue(conn)
            heartbeat(conn, WORKER_KEY, status="Starting")
        app.logger.warning("EMBER_QUEUE worker started interval=%ss", interval)
        time.sleep(20)
        while True:
            try:
                _process_one(app, db_path)
            except Exception as exc:
                app.logger.exception("EMBER_QUEUE loop recovered from unexpected error")
                try:
                    with _connect(db_path) as conn:
                        refill_national_queue(conn)
                        heartbeat(conn, WORKER_KEY, status="Failed", last_error=str(exc))
                except Exception:
                    app.logger.exception("EMBER_QUEUE could not persist recovery state")
            time.sleep(interval)

    threading.Thread(target=loop, name="ember-queue-worker", daemon=True).start()
