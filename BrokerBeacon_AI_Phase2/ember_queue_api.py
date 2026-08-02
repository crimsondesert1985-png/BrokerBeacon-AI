"""Owner-only queue, worker, and activity APIs for Sprint 41."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from ember_jobs import enqueue, initialize


def install_ember_queue_api(app, db_path):
    bp = Blueprint("ember_queue", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        initialize(conn)

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner")):
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/ember-queue")
    @owner_required
    def queue_status():
        limit = min(max(int(request.args.get("limit") or 50), 1), 200)
        with connect() as conn:
            summary = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "select status,count(*) count from crawl_jobs group by status"
                ).fetchall()
            }
            jobs = [
                dict(row)
                for row in conn.execute(
                    """select id,job_type,state,company_id,priority,status,attempts,max_attempts,
                              available_at,claimed_by,claimed_at,lock_expires_at,completed_at,
                              last_error,created_at,updated_at
                       from crawl_jobs order by id desc limit ?""",
                    (limit,),
                ).fetchall()
            ]
        return jsonify(summary=summary, items=jobs, count=len(jobs))

    @bp.get("/api/platform/ember-workers")
    @owner_required
    def workers():
        with connect() as conn:
            rows = [dict(row) for row in conn.execute(
                "select * from worker_status order by last_heartbeat_at desc"
            ).fetchall()]
        now = datetime.now()
        for row in rows:
            try:
                row["stale"] = (now - datetime.fromisoformat(row["last_heartbeat_at"])).total_seconds() > 90
            except (ValueError, TypeError):
                row["stale"] = True
        return jsonify(items=rows, count=len(rows))

    @bp.get("/api/platform/ember-activity")
    @owner_required
    def activity():
        limit = min(max(int(request.args.get("limit") or 100), 1), 500)
        with connect() as conn:
            rows = [dict(row) for row in conn.execute(
                """select id,event_type,worker_key,job_id,company_id,contact_id,state,
                          message,detail_json,created_at
                   from activity_events order by id desc limit ?""",
                (limit,),
            ).fetchall()]
        return jsonify(items=rows, count=len(rows))

    @bp.post("/api/platform/ember-queue/discovery")
    @owner_required
    def enqueue_discovery():
        payload = request.get_json(silent=True) or {}
        state = str(payload.get("state") or "").strip().upper()
        if state and (len(state) != 2 or not state.isalpha()):
            return jsonify(error="State must be a two-letter code"), 400
        with connect() as conn:
            job_id = enqueue(
                conn,
                "discovery_cycle",
                state=state,
                payload={
                    "state": state,
                    "company_limit": min(max(int(payload.get("company_limit") or 6), 1), 25),
                    "contact_limit": min(max(int(payload.get("contact_limit") or 250), 1), 1000),
                },
                priority=min(max(int(payload.get("priority") or 100), 1), 1000),
                max_attempts=min(max(int(payload.get("max_attempts") or 3), 1), 10),
            )
        return jsonify(
            id=job_id,
            status="Queued",
            outreach_enabled=False,
            crm_promotion_enabled=False,
            human_review_required=True,
        ), 201

    app.register_blueprint(bp)
    return bp
