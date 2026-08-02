"""Internal scheduled Ember endpoint with always-on worker fallback."""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from ember_hunt import launch


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
        authorized = bool(expected and supplied and hmac.compare_digest(expected, supplied))
        if not authorized:
            always_on = os.getenv("EMBER_ALWAYS_ON", "1").strip().lower() not in {"0", "false", "no"}
            if always_on:
                return jsonify(
                    status="Skipped",
                    reason="Always-on Ember worker is the authoritative scheduler",
                    outreach_enabled=False,
                ), 202
            return jsonify(error="Unauthorized"), 401

        with connect() as conn:
            conn.execute("""create table if not exists ember_automation_runs(
                id integer primary key,
                state text not null,
                status text not null,
                detail_json text not null default '{}',
                created_at text not null,
                finished_at text default ''
            )""")
            recent = conn.execute(
                "select status,created_at,finished_at from ember_automation_runs order by id desc limit 1"
            ).fetchone()
            if recent:
                try:
                    stamp = recent["finished_at"] or recent["created_at"]
                    age = datetime.now() - datetime.fromisoformat(stamp)
                    if recent["status"] == "Running" and age < timedelta(minutes=20):
                        return jsonify(status="Skipped", reason="An Ember cycle is already running"), 202
                    if recent["status"] == "Completed" and age < timedelta(minutes=3):
                        return jsonify(status="Skipped", reason="Ember is in its respectful crawl cooldown"), 202
                except (ValueError, TypeError):
                    pass

            started = datetime.now().isoformat(timespec="seconds")
            run_id = int(conn.execute(
                "insert into ember_automation_runs(state,status,created_at) values('AUTO','Running',?)",
                (started,),
            ).lastrowid)
            conn.commit()
            try:
                result = launch(conn, state="", company_limit=6, contact_limit=250)
                finished = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    "update ember_automation_runs set state=?,status='Completed',detail_json=?,finished_at=? where id=?",
                    (result.get("state", ""), json.dumps(result, default=str), finished, run_id),
                )
                conn.commit()
                app.logger.warning(
                    "EMBER_CRON completed run_id=%s state=%s companies=%s contacts=%s pending=%s",
                    run_id, result.get("state", ""), result.get("companies_seeded", 0),
                    (result.get("enrichment") or {}).get("contacts_found", 0),
                    result.get("pending_review", 0),
                )
                return jsonify(status="Completed", run_id=run_id, result=result), 201
            except Exception as exc:
                finished = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    "update ember_automation_runs set status='Failed',detail_json=?,finished_at=? where id=?",
                    (str(exc)[:1000], finished, run_id),
                )
                conn.commit()
                app.logger.exception("EMBER_CRON cycle failed safely")
                return jsonify(error="Ember cycle failed safely", run_id=run_id), 500

    app.register_blueprint(bp)
    return bp
