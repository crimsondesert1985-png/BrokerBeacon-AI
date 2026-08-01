"""Always-on, review-gated Ember worker for BrokerBeacon's single Gunicorn instance."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from ember_hunt import launch

_started = False
_start_lock = threading.Lock()


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _ensure_schema(conn):
    conn.execute("""create table if not exists ember_automation_runs(
        id integer primary key,
        state text not null,
        status text not null,
        detail_json text not null default '{}',
        created_at text not null,
        finished_at text default ''
    )""")
    conn.commit()


def _cycle_allowed(conn):
    recent = conn.execute(
        "select status,created_at,finished_at from ember_automation_runs order by id desc limit 1"
    ).fetchone()
    if not recent:
        return True
    try:
        stamp = recent["finished_at"] or recent["created_at"]
        age = datetime.now() - datetime.fromisoformat(stamp)
        if recent["status"] == "Running" and age < timedelta(minutes=20):
            return False
        if recent["status"] == "Completed" and age < timedelta(minutes=3):
            return False
    except (ValueError, TypeError):
        pass
    return True


def _run_cycle(app, db_path):
    with _connect(db_path) as conn:
        _ensure_schema(conn)
        if not _cycle_allowed(conn):
            return
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
            app.logger.info(
                "Always-on Ember completed run_id=%s state=%s companies=%s contacts=%s pending=%s",
                run_id,
                result.get("state", ""),
                result.get("companies_seeded", 0),
                (result.get("enrichment") or {}).get("contacts_found", 0),
                result.get("pending_review", 0),
            )
        except Exception as exc:
            finished = datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "update ember_automation_runs set status='Failed',detail_json=?,finished_at=? where id=?",
                (str(exc)[:1000], finished, run_id),
            )
            conn.commit()
            app.logger.exception("Always-on Ember cycle failed")


def install_ember_worker(app, db_path):
    """Start exactly one daemon loop per Gunicorn worker process."""
    global _started
    enabled = os.getenv("EMBER_ALWAYS_ON", "1").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        app.logger.info("Always-on Ember worker is disabled")
        return
    with _start_lock:
        if _started:
            return
        _started = True

    interval = max(int(os.getenv("EMBER_LOOP_SECONDS", "300")), 180)

    def loop():
        app.logger.info("Always-on Ember worker started interval=%ss", interval)
        time.sleep(20)
        while True:
            try:
                _run_cycle(app, db_path)
            except Exception:
                app.logger.exception("Always-on Ember loop recovered from an unexpected error")
            time.sleep(interval)

    threading.Thread(target=loop, name="ember-always-on", daemon=True).start()
