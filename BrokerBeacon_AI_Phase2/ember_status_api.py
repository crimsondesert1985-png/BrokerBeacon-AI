"""Owner-visible health endpoint for Ember automation and discovery sources."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, session

from source_resilience import source_health


def install_ember_status_api(app, db_path):
    bp = Blueprint("ember_status", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout=30000")
        return conn

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner")):
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/ember-health")
    @owner_required
    def health():
        with connect() as conn:
            conn.execute("""create table if not exists ember_worker_heartbeat(
                worker_key text primary key,
                status text not null,
                message text not null default '',
                last_seen_at text not null,
                last_cycle_started_at text not null default '',
                last_cycle_finished_at text not null default '',
                last_run_id integer,
                last_state text not null default '',
                last_error text not null default ''
            )""")
            heartbeat = conn.execute(
                "select * from ember_worker_heartbeat where worker_key in ('always-on-web','always-on') order by last_seen_at desc limit 1"
            ).fetchone()
            latest = conn.execute(
                "select id,state,status,created_at,finished_at,detail_json from ember_automation_runs order by id desc limit 1"
            ).fetchone() if conn.execute(
                "select count(*) from sqlite_master where type='table' and name='ember_automation_runs'"
            ).fetchone()[0] else None
            sources = source_health(conn)

        heartbeat_dict = dict(heartbeat) if heartbeat else None
        latest_dict = dict(latest) if latest else None
        stale = True
        if heartbeat_dict:
            try:
                stale = (datetime.now() - datetime.fromisoformat(heartbeat_dict["last_seen_at"])).total_seconds() > 420
            except (ValueError, TypeError):
                stale = True
        worker_healthy = bool(heartbeat_dict and not stale and heartbeat_dict.get("status") != "Failed")
        return jsonify(
            worker=heartbeat_dict,
            latest_run=latest_dict,
            healthy=worker_healthy,
            stale=stale,
            sources=sources,
            discovery_ready=bool(worker_healthy and sources.get("search_ready")),
            outreach_enabled=False,
            crm_promotion_enabled=False,
        )

    app.register_blueprint(bp)
    return bp
