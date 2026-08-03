"""Always-on, review-gated Ember queue worker for BrokerBeacon."""
from __future__ import annotations

import gc
import os
import sqlite3
import threading
import time
from contextlib import closing

from ember_pipeline import launch
from ember_jobs import claim_next, complete, emit_event, fail, heartbeat, initialize, now_iso
from intelligence_flow import advance_intelligence
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


def _reset_stale_discovery_backlog(conn):
    """Cancel queued discovery jobs left by older scheduler versions and rebuild fairly."""
    initialize(conn)
    stamp = now_iso()
    rows = conn.execute(
        "select id,state from crawl_jobs where job_type='discovery_cycle' and status='Queued' order by id"
    ).fetchall()
    if not rows:
        return 0
    conn.execute(
        """update crawl_jobs set status='Cancelled',completed_at=?,updated_at=?,
           last_error='Superseded by national queue reset' where job_type='discovery_cycle' and status='Queued'""",
        (stamp, stamp),
    )
    conn.commit()
    emit_event(
        conn,
        "NationalQueueReset",
        f"Ember cleared {len(rows)} stale discovery jobs before rebuilding national coverage",
        worker_key=WORKER_KEY,
        detail={"cancelled_jobs": len(rows), "states": sorted({str(row['state'] or '') for row in rows})},
    )
    return len(rows)


def _ensure_national_queue(conn) -> int:
    """Keep Ember moving automatically whenever the queue is low or empty."""
    created = refill_national_queue(conn)
    if created:
        emit_event(
            conn,
            "AutomaticHuntsQueued",
            f"Ember automatically queued {len(created)} mortgage-broker state hunts",
            worker_key=WORKER_KEY,
            detail={"jobs": created},
        )
    return len(created)


def _process_one(app, db_path):
    with closing(_connect(db_path)) as conn:
        _ensure_national_queue(conn)
        job = claim_next(conn, WORKER_KEY, lease_seconds=1200)
        if not job:
            heartbeat(conn, WORKER_KEY, status="Idle")
            return False
        heartbeat(conn, WORKER_KEY, status="Running", current_job_id=job["id"])
        try:
            payload = job.get("payload") or {}
            result = launch(
                conn,
                state=str(payload.get("state") or job.get("state") or "").strip().upper(),
                company_limit=min(max(int(payload.get("company_limit", 50)), 50), 100),
                contact_limit=min(max(int(payload.get("contact_limit", 1000)), 500), 2000),
            )
            complete(conn, int(job["id"]), WORKER_KEY, detail=result)
            graph = advance_intelligence(conn, state=result.get("state", ""))
            public_search = result.get("public_search") or {}
            company_crawl = result.get("company_crawl") or {}
            emit_event(
                conn,
                "PipelineAdvanced",
                f"{result.get('state', '')} flowed from mortgage-broker discovery through company crawling, intelligence, and review",
                worker_key=WORKER_KEY,
                job_id=int(job["id"]),
                state=result.get("state", ""),
                detail={
                    "companies": result.get("companies_seeded", 0),
                    "companies_crawled": company_crawl.get("completed", 0),
                    "warehouse_created": (company_crawl.get("warehouse") or {}).get("created", 0),
                    "warehouse_updated": (company_crawl.get("warehouse") or {}).get("updated", 0),
                    "pages_fetched": company_crawl.get("pages_fetched", 0),
                    "contacts": result.get("new_contacts", 0),
                    "pending_review": result.get("pending_review", 0),
                    "public_search_status": public_search.get("status", "Not needed"),
                    "public_search_indexed": public_search.get("indexed", 0),
                    "public_search_reason": public_search.get("reason", ""),
                    "company_nodes": graph.get("company_nodes", 0),
                    "person_nodes": graph.get("person_nodes", 0),
                    "relationships": graph.get("relationships", 0),
                    "graph_status": graph.get("status", "Deferred"),
                    "next_stage": "Human review",
                },
            )
            heartbeat(conn, WORKER_KEY, status="Idle", jobs_completed_today=1)
            _ensure_national_queue(conn)
            app.logger.warning(
                "EMBER_QUEUE completed job_id=%s state=%s seeded=%s crawled=%s warehouse_created=%s contacts=%s search=%s indexed=%s graph=%s",
                job["id"], result.get("state", ""), result.get("companies_seeded", 0),
                company_crawl.get("completed", 0), (company_crawl.get("warehouse") or {}).get("created", 0),
                (result.get("enrichment") or {}).get("contacts_found", 0),
                public_search.get("status", "Not needed"), public_search.get("indexed", 0),
                graph.get("status", "Deferred"),
            )
            return True
        except Exception as exc:
            fail(conn, int(job["id"]), WORKER_KEY, str(exc), retry_delay_seconds=120)
            heartbeat(conn, WORKER_KEY, status="Failed", current_job_id=None, last_error=str(exc))
            app.logger.exception("EMBER_QUEUE job failed safely")
            return False


def _run_burst(app, db_path, max_jobs: int, between_jobs: int) -> int:
    """Process a bounded burst so the queue flows without blocking forever."""
    completed = 0
    try:
        for index in range(max(1, max_jobs)):
            if not _process_one(app, db_path):
                break
            completed += 1
            if index + 1 < max_jobs and between_jobs:
                time.sleep(between_jobs)
        return completed
    finally:
        gc.collect()


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

    idle_interval = max(int(os.getenv("EMBER_IDLE_SECONDS", "30")), 15)
    startup_delay = max(int(os.getenv("EMBER_STARTUP_DELAY_SECONDS", "0")), 0)
    burst_jobs = max(1, min(int(os.getenv("EMBER_BURST_JOBS", "2")), 6))
    between_jobs = max(0, min(int(os.getenv("EMBER_BETWEEN_JOBS_SECONDS", "3")), 30))

    def loop():
        with closing(_connect(db_path)) as conn:
            initialize(conn)
            cancelled = _reset_stale_discovery_backlog(conn)
            queued = _ensure_national_queue(conn)
            heartbeat(conn, WORKER_KEY, status="Starting")
        app.logger.warning(
            "EMBER_QUEUE worker started idle=%ss burst=%s between=%ss reset=%s auto_queued=%s queue_mode=automatic-national",
            idle_interval, burst_jobs, between_jobs, cancelled, queued,
        )
        time.sleep(startup_delay)
        while True:
            try:
                completed = _run_burst(app, db_path, burst_jobs, between_jobs)
                if completed:
                    app.logger.warning("EMBER_QUEUE burst completed jobs=%s", completed)
            except Exception as exc:
                app.logger.exception("EMBER_QUEUE loop recovered from unexpected error")
                try:
                    with closing(_connect(db_path)) as conn:
                        heartbeat(conn, WORKER_KEY, status="Failed", last_error=str(exc))
                except Exception:
                    app.logger.exception("EMBER_QUEUE could not persist recovery state")
            time.sleep(idle_interval)

    threading.Thread(target=loop, name="ember-queue-worker", daemon=True).start()
