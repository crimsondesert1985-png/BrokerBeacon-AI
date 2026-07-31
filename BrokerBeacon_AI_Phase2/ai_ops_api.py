"""Owner-only AI operations API for the unified Scout Control Tower."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from ai_orchestrator import dashboard as agent_dashboard, learn_from_approved_feedback
from autonomy_engine import dashboard as autonomy_dashboard, run_cycle, update_policy
from growth_mission import dashboard as growth_dashboard


def install_ai_ops(app, db_path):
    bp = Blueprint("ai_ops", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def is_owner():
        for user in (getattr(g, "saas_user", None), getattr(g, "current_user", None), getattr(g, "user", None)):
            if user is None:
                continue
            try:
                if bool(user["is_platform_owner"]):
                    return True
            except (KeyError, TypeError):
                if bool(getattr(user, "is_platform_owner", 0)):
                    return True
        return bool(session.get("is_platform_owner"))

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not is_owner():
                return jsonify(error="Platform owner access required", code="platform_owner_required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/ai-ops")
    @owner_required
    def status():
        with connect() as conn:
            return jsonify({
                "agents": agent_dashboard(conn),
                "autonomy": autonomy_dashboard(conn),
                "growth": growth_dashboard(conn),
                "briefing": _briefing(conn),
            })

    @bp.post("/api/platform/ai-ops/policy")
    @owner_required
    def policy_update():
        payload = request.get_json(silent=True) or {}
        with connect() as conn:
            policy = update_policy(conn, "default", payload)
        return jsonify(policy)

    @bp.post("/api/platform/ai-ops/run-cycle")
    @owner_required
    def execute_cycle():
        with connect() as conn:
            result = run_cycle(conn, "default")
        return jsonify(result), 201

    @bp.post("/api/platform/ai-ops/learn/<agent_key>")
    @owner_required
    def learn(agent_key):
        with connect() as conn:
            result = learn_from_approved_feedback(conn, agent_key, limit=250)
        return jsonify(result), 201

    app.register_blueprint(bp)
    return bp


def _briefing(conn: sqlite3.Connection) -> dict:
    warehouse = conn.execute("select count(*) from warehouse_companies").fetchone()[0]
    contacts = conn.execute("select count(*) from discovered_contacts").fetchone()[0]
    pending = conn.execute("select count(*) from discovered_contacts where review_status='Pending review'").fetchone()[0]
    high_value = conn.execute("select count(*) from ai_contact_insights where opportunity_score>=75").fetchone()[0]
    duplicates = conn.execute("select count(*) from warehouse_duplicate_candidates where status='Pending review'").fetchone()[0]
    last_run = conn.execute("select * from autonomy_runs order by id desc limit 1").fetchone()
    return {
        "headline": "AI growth team operating within owner guardrails",
        "warehouse_companies": int(warehouse or 0),
        "discovered_contacts": int(contacts or 0),
        "pending_review": int(pending or 0),
        "high_opportunity": int(high_value or 0),
        "pending_duplicates": int(duplicates or 0),
        "last_autonomy_run": dict(last_run) if last_run else None,
        "recommended_focus": "Review high-opportunity prospects and keep approved states supplied with search and enrichment capacity.",
    }
