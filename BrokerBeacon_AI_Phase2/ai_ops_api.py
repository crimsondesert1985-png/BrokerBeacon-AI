"""Owner-only AI operations API for the unified Scout Control Tower."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from ai_intelligence import initialize as initialize_ai_intelligence
from ai_orchestrator import dashboard as agent_dashboard, learn_from_approved_feedback
from autonomy_engine import dashboard as autonomy_dashboard, update_policy
from ember_pipeline import launch as launch_ember_hunt
from growth_mission import dashboard as growth_dashboard


def install_ai_ops(app, db_path):
    bp = Blueprint("ai_ops", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    # Ensure every table used by the briefing exists before the first request.
    with connect() as conn:
        initialize_ai_intelligence(conn)
        agent_dashboard(conn)
        autonomy_dashboard(conn)
        growth_dashboard(conn)

    def is_owner():
        if bool(getattr(g, "is_platform_owner", False)):
            return True
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
            initialize_ai_intelligence(conn)
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
        """Launch one bounded Ember crawl; never promote to CRM or initiate outreach."""
        payload = request.get_json(silent=True) or {}
        state = str(payload.get("state") or "NC").strip().upper()
        company_limit = min(max(int(payload.get("company_limit") or 10), 1), 25)
        contact_limit = min(max(int(payload.get("contact_limit") or 200), 1), 500)
        with connect() as conn:
            initialize_ai_intelligence(conn)
            # Force review-gated guardrails before discovery and crawling begins.
            update_policy(conn, "default", {
                "enabled": True,
                "approved_states": [state],
                "require_human_review": True,
                "allow_crm_promotion": False,
                "allow_outreach": False,
                "allow_permission_changes": False,
            })
            result = launch_ember_hunt(
                conn,
                state=state,
                company_limit=company_limit,
                contact_limit=contact_limit,
            )
        return jsonify(result), 201

    @bp.post("/api/platform/ai-ops/learn/<agent_key>")
    @owner_required
    def learn(agent_key):
        with connect() as conn:
            result = learn_from_approved_feedback(conn, agent_key, limit=250)
        return jsonify(result), 201

    app.register_blueprint(bp)
    return bp


def _count(conn: sqlite3.Connection, sql: str) -> int:
    try:
        row = conn.execute(sql).fetchone()
        return int((row[0] if row else 0) or 0)
    except sqlite3.OperationalError:
        return 0


def _briefing(conn: sqlite3.Connection) -> dict:
    initialize_ai_intelligence(conn)
    warehouse = _count(conn, "select count(*) from warehouse_companies")
    contacts = _count(conn, "select count(*) from discovered_contacts")
    pending = _count(conn, "select count(*) from discovered_contacts where review_status='Pending review'")
    high_value = _count(conn, "select count(*) from ai_contact_insights where opportunity_score>=75")
    duplicates = _count(conn, "select count(*) from warehouse_duplicate_candidates where status='Pending review'")
    try:
        last_run = conn.execute("select * from autonomy_runs order by id desc limit 1").fetchone()
    except sqlite3.OperationalError:
        last_run = None
    return {
        "headline": "AI growth team operating within owner guardrails",
        "warehouse_companies": warehouse,
        "discovered_contacts": contacts,
        "pending_review": pending,
        "high_opportunity": high_value,
        "pending_duplicates": duplicates,
        "last_autonomy_run": dict(last_run) if last_run else None,
        "recommended_focus": "Let Ember build the state-by-state company warehouse, then review discovered contacts before any CRM promotion or outreach.",
    }
