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


def _now():
    return datetime.now().isoformat(timespec="seconds")


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
    conn.commit()


def _heartbeat(conn, status, message="", **fields):
    current = conn.execute(
        "select * from ember_worker_heartbeat where worker_key='always-on'"
    ).fetchone()
    values = dict(current) if current else {
        "last_cycle_started_at": "",
        "last_cycle_finished_at": "",
        "last_run_id": None,
        "last_state": "",
        "last_error": "",
    }
    values.update(fields)
    conn.execute("""insert into ember_worker_heartbeat(
        worker_key,status,message,last_seen_at,last_cycle_started_at,
        last_cycle_finished_at,last_run_id,last_state,last_error)
        values('always-on',?,?,?,?,?,?,?,?)
        on conflict(worker_key) do update set
          status=excluded.status,message=excluded.message,last_seen_at=excluded.last_seen_at,
          last_cycle_started_at=excluded.last_cycle_started_at,
          last_cycle_finished_at=excluded.last_cycle_finished_at,
          last_run_id=excluded.last_run_id,last_state=excluded.last_state,
          last_error=excluded.last_error
    """, (
        status, message, _now(), values.get("last_cycle_started_at", ""),
        values.get("last_cycle_finished_at", ""), values.get("last_run_id"),
        values.get("last_state", ""), values.get("last_error", ""),
    ))
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
            _heartbeat(conn, "Waiting", "Cooldown or another safe cycle is active")
            return
        started = _now()
        run_id = int(conn.execute(
            "insert into ember_automation_runs(state,status,created_at) values('AUTO','Running',?)",
            (started,),
        ).lastrowid)
        conn.commit()
        _heartbeat(
            conn, "Running", "Ember is scanning approved public company websites",
            last_cycle_started_at=started, last_run_id=run_id, last_error="",
        )
        try:
            result = launch(conn, state="", company_limit=6, contact_limit=250)
            finished = _now()
            conn.execute(
                "update ember_automation_runs set state=?,status='Completed',detail_json=?,finished_at=? where id=?",
                (result.get("state", ""), json.dumps(result, default=str), finished, run_id),
            )
            conn.commit()
            contacts = (result.get("enrichment") or {}).get("contacts_found", 0)
            _heartbeat(
                conn, "Healthy",
                f"Completed safe cycle: {result.get('companies_seeded', 0)} companies, {contacts} contacts",
                last_cycle_finished_at=finished, last_run_id=run_id,
                last_state=result.get("state", ""), last_error="",
            )
            app.logger.warning(
                "EMBER_HEARTBEAT completed run_id=%s state=%s companies=%s contacts=%s pending=%s",
                run_id, result.get("state", ""), result.get("companies_seeded", 0),
                contacts, result.get("pending_review", 0),
            )
        except Exception as exc:
            finished = _now()
            conn.execute(
                "update ember_automation_runs set status='Failed',detail_json=?,finished_at=? where id=?",
                (str(exc)[:1000], finished, run_id),
            )
            conn.commit()
            _heartbeat(
                conn, "Failed", "Cycle failed safely and will retry",
                last_cycle_finished_at=finished, last_run_id=run_id,
                last_error=str(exc)[:1000],
            )
            app.logger.exception("EMBER_HEARTBEAT cycle failed")


def install_ember_worker(app, db_path):
    """Start exactly one daemon loop per Gunicorn worker process."""
    global _started
    enabled = os.getenv("EMBER_ALWAYS_ON", "1").strip().lower() not in {"0", "false", "no"}
    if not enabled:
        app.logger.warning("EMBER_HEARTBEAT worker disabled")
        return
    with _start_lock:
        if _started:
            return
        _started = True

    interval = max(int(os.getenv("EMBER_LOOP_SECONDS", "300")), 180)

    def loop():
        with _connect(db_path) as conn:
            _ensure_schema(conn)
            _heartbeat(conn, "Starting", f"Worker booted; cycle interval {interval} seconds")
        app.logger.warning("EMBER_HEARTBEAT worker started interval=%ss", interval)
        time.sleep(20)
        while True:
            try:
                _run_cycle(app, db_path)
            except Exception as exc:
                app.logger.exception("EMBER_HEARTBEAT loop recovered from unexpected error")
                try:
                    with _connect(db_path) as conn:
                        _ensure_schema(conn)
                        _heartbeat(conn, "Failed", "Loop recovered and will retry", last_error=str(exc)[:1000])
                except Exception:
                    app.logger.exception("EMBER_HEARTBEAT could not persist recovery state")
            time.sleep(interval)

    threading.Thread(target=loop, name="ember-always-on", daemon=True).start()
