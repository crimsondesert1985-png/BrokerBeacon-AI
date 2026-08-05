"""Maintain BrokerBeacon's prospect catalog with restart-safe daily imports."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from autonomous_prospecting import purge_invalid_ember_prospects, promote_warehouse_companies
from official_roster_import import import_missouri_broker_roster, promote_official_roster

_started = False
_lock = threading.Lock()
SCHEDULE_SCHEMA = """
create table if not exists prospect_import_schedule(
 id integer primary key check(id=1),
 status text not null default 'Never',
 started_at text default '',
 completed_at text default '',
 last_error text default '',
 last_total integer not null default 0
);
insert or ignore into prospect_import_schedule(id,status) values(1,'Never');
"""


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _parse(value: str):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def install_prospect_backfill_boot(app, db_path):
    global _started
    with _lock:
        if _started:
            return app
        _started = True

    def due(conn) -> bool:
        conn.executescript(SCHEDULE_SCHEMA)
        row = conn.execute("select * from prospect_import_schedule where id=1").fetchone()
        total = int(conn.execute("select count(*) from prospects").fetchone()[0])
        if total < 500:
            return True
        completed = _parse(str(row["completed_at"] or ""))
        started = _parse(str(row["started_at"] or ""))
        if row["status"] == "Running" and started and datetime.now() - started < timedelta(hours=2):
            return False
        return not completed or datetime.now() - completed >= timedelta(hours=20)

    def claim(conn) -> bool:
        if not due(conn):
            return False
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("update prospect_import_schedule set status='Running',started_at=?,last_error='' where id=1", (now,))
        conn.commit()
        return True

    def run_once():
        try:
            with closing(_connect(db_path)) as conn:
                if not claim(conn):
                    total = int(conn.execute("select count(*) from prospects").fetchone()[0])
                    app.logger.warning("PROSPECT_DAILY skipped not_due total=%s", total)
                    return
                removed = purge_invalid_ember_prospects(conn)
                matchup = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=80)
                roster = import_missouri_broker_roster(conn, target_minimum=500)
                official = promote_official_roster(conn, target_minimum=500, limit=10000)
                state_rows = conn.execute(
                    """select upper(state),count(*) from prospects
                       where length(trim(coalesce(state,'')))=2
                       group by upper(state) order by upper(state)"""
                ).fetchall()
                total = int(conn.execute("select count(*) from prospects where trim(coalesce(company,''))<>''").fetchone()[0])
                now = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    """update prospect_import_schedule set status='Completed',completed_at=?,last_total=?,last_error='' where id=1""",
                    (now, total),
                )
                conn.commit()
            app.logger.warning(
                "PROSPECT_DAILY completed removed_generic=%s matchup_created=%s roster_rows=%s roster_created=%s roster_updated=%s official_created=%s official_updated=%s visible_total=%s states=%s",
                removed, matchup.get("prospects_created", 0), roster.get("source_rows", 0),
                roster.get("created", 0), roster.get("updated", 0), official.get("created", 0),
                official.get("updated", 0), total, len(state_rows),
            )
            app.logger.warning("PROSPECT_DAILY state_breakdown=%s", [(str(r[0] or ""), int(r[1])) for r in state_rows])
        except Exception as exc:
            try:
                with closing(_connect(db_path)) as conn:
                    conn.executescript(SCHEDULE_SCHEMA)
                    conn.execute(
                        "update prospect_import_schedule set status='Failed',last_error=? where id=1",
                        (str(exc)[:1000],),
                    )
                    conn.commit()
            except Exception:
                pass
            app.logger.exception("PROSPECT_DAILY failed")

    def loop():
        time.sleep(5)
        while True:
            run_once()
            time.sleep(3600)

    threading.Thread(target=loop, name="daily-prospect-import", daemon=True).start()
    return app


__all__ = ["install_prospect_backfill_boot"]
