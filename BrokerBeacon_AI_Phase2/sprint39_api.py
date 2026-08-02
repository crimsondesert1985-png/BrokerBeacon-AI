"""Owner-only operations API for Ember activity, health, progress, and priorities."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, session

from ai_intelligence import initialize as init_ai
from ember_activity import initialize as init_activity
from ember_jobs import initialize as init_jobs
from website_enrichment import initialize as init_enrichment


def install_sprint39_api(app, db_path):
    bp = Blueprint("sprint39", __name__)

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

    def count(conn, sql, args=()):
        try:
            row = conn.execute(sql, args).fetchone()
            return int((row[0] if row else 0) or 0)
        except sqlite3.OperationalError:
            return 0

    @bp.get("/api/platform/sprint39/overview")
    @owner_required
    def overview():
        with connect() as conn:
            init_activity(conn)
            init_enrichment(conn)
            init_ai(conn)
            init_jobs(conn)
            legacy = [dict(row) for row in conn.execute(
                "select id,title,detail,severity,company_name,created_at from ember_activity order by id desc limit 50"
            ).fetchall()]
            queue_events = []
            for row in conn.execute(
                "select id,event_type,message,state,created_at from activity_events order by id desc limit 80"
            ).fetchall():
                item = dict(row)
                item.update({
                    "title": item.pop("event_type"),
                    "detail": item.pop("message"),
                    "severity": "error" if item["title"] == "JobFailed" else "success" if item["title"] in {"JobCompleted", "JobRecovered"} else "",
                    "company_name": "",
                })
                queue_events.append(item)
            activity = sorted(legacy + queue_events, key=lambda x: x.get("created_at") or "", reverse=True)[:80]
            states = [dict(row) for row in conn.execute(
                "select * from ember_state_cursors order by coalesce(last_run_at,'') desc,state"
            ).fetchall()]
            priorities = [dict(row) for row in conn.execute("""
                select d.id,d.person_name,d.company_name,d.role,d.state,d.city,d.public_email,d.phone,
                       d.source_url,d.review_status,coalesce(a.opportunity_score,0) opportunity_score,
                       coalesce(a.next_best_action,'Review and verify this prospect.') next_best_action,
                       coalesce(a.reasons_json,'[]') reasons_json
                from discovered_contacts d
                left join ai_contact_insights a on a.discovered_contact_id=d.id
                where d.review_status='Pending review'
                order by opportunity_score desc,d.id desc limit 12
            """).fetchall()]
            queue = {row["status"]: int(row["n"]) for row in conn.execute(
                "select status,count(*) n from crawl_jobs group by status"
            ).fetchall()}
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
            completed = count(conn, "select count(*) from activity_events where event_type='JobCompleted' and created_at>=?", (cutoff,))
            failures = count(conn, "select count(*) from activity_events where event_type='JobFailed' and created_at>=?", (cutoff,))
            pending = count(conn, "select count(*) from discovered_contacts where review_status='Pending review'")
            high = count(conn, """select count(*) from discovered_contacts d join ai_contact_insights a
                                  on a.discovered_contact_id=d.id where d.review_status='Pending review'
                                  and a.opportunity_score>=75""")
            companies = count(conn, "select count(*) from ember_company_history")
            contacts = count(conn, "select count(*) from discovered_contacts")
            last_run = conn.execute(
                "select event_type title,message detail,created_at from activity_events order by id desc limit 1"
            ).fetchone()
            health_status = "Healthy" if failures == 0 else ("Degraded" if completed else "Needs attention")
            morning = {
                "headline": "Ember is actively building your prospect pipeline.",
                "summary": f"{contacts} contacts found across {companies} tracked companies; {pending} await review and {high} are high opportunity.",
                "recommended_action": "Review the highest-scoring pending prospects first.",
                "outreach_sent": 0,
            }
            return jsonify(
                activity=activity,
                states=states,
                priorities=priorities,
                health={
                    "status": health_status,
                    "completed_24h": completed,
                    "failures_24h": failures,
                    "queue": queue,
                    "last_activity": dict(last_run) if last_run else None,
                    "tracked_companies": companies,
                    "contacts": contacts,
                    "pending_review": pending,
                    "high_opportunity": high,
                },
                morning_brief=morning,
            )

    app.register_blueprint(bp)
    return bp
