"""Owner-only national Ember autopilot controls and summary."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, session

from national_scheduler import national_summary, refill_national_queue


def install_national_autopilot_api(app, db_path):
    bp = Blueprint("national_autopilot", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner")):
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/national-autopilot")
    @owner_required
    def status():
        with connect() as conn:
            summary = national_summary(conn)
            review = conn.execute("""
                select d.id,d.person_name,d.company_name,d.state,d.role,
                       coalesce(a.opportunity_score,0) opportunity_score,
                       coalesce(a.next_best_action,'Review and verify this prospect.') next_best_action
                from discovered_contacts d
                left join ai_contact_insights a on a.discovered_contact_id=d.id
                where d.review_status='Pending review'
                order by opportunity_score desc,d.confidence desc,d.id desc limit 5
            """).fetchall()
            recent_states = conn.execute("""
                select state,companies_processed,contacts_found,last_run_at
                from ember_state_cursors order by coalesce(last_run_at,'') desc limit 8
            """).fetchall()
        return jsonify(summary=summary, priorities=[dict(row) for row in review], recent_states=[dict(row) for row in recent_states])

    @bp.post("/api/platform/national-autopilot/refill")
    @owner_required
    def refill():
        with connect() as conn:
            jobs = refill_national_queue(conn)
            summary = national_summary(conn)
        return jsonify(status="Ready", jobs_created=jobs, summary=summary, outreach_enabled=False), 201

    app.register_blueprint(bp)
    return bp
