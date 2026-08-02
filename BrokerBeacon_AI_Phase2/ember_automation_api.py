"""Internal token-protected endpoint that queues Ember discovery work."""
from __future__ import annotations

import hmac
import os
import sqlite3

from flask import Blueprint, jsonify, request

from ember_jobs import enqueue, initialize


def install_ember_automation(app, db_path):
    bp = Blueprint("ember_automation", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    @bp.post("/api/internal/ember-cycle")
    def scheduled_cycle():
        expected = os.getenv("EMBER_AUTOMATION_TOKEN", "").strip()
        supplied = request.headers.get("X-Ember-Token", "").strip()
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            return jsonify(error="Unauthorized"), 401

        with connect() as conn:
            initialize(conn)
            active = conn.execute(
                "select id,status from crawl_jobs where job_type='discovery_cycle' and status in ('Queued','Running') order by id limit 1"
            ).fetchone()
            if active:
                return jsonify(status="Skipped", reason="A discovery job is already active", job_id=active["id"]), 202
            job_id = enqueue(
                conn,
                "discovery_cycle",
                payload={"state": "", "company_limit": 6, "contact_limit": 250},
                priority=100,
                max_attempts=3,
            )
        return jsonify(
            status="Queued",
            job_id=job_id,
            outreach_enabled=False,
            crm_promotion_enabled=False,
            human_review_required=True,
        ), 201

    app.register_blueprint(bp)
    return bp
