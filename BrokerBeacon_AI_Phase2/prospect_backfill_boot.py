"""Maintain a clean BrokerBeacon prospect catalog with restart-safe daily imports."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from autonomous_prospecting import promote_warehouse_companies
from official_roster_import import import_missouri_broker_roster, promote_official_roster
from prospect_quality import is_publishable_prospect

_started = False
_lock = threading.Lock()
SCHEDULE_SCHEMA = """
create table if not exists prospect_import_schedule(
 id integer primary key check(id=1), status text not null default 'Never',
 started_at text default '', completed_at text default '', last_error text default '',
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


def _clean_catalog(conn: sqlite3.Connection) -> int:
    rows = conn.execute("select id,company,nmls,source_name from prospects").fetchall()
    bad = [int(r["id"]) for r in rows if not is_publishable_prospect(r["company"], r["nmls"], r["source_name"])]
    if not bad:
        return 0
    marks = ",".join("?" for _ in bad)
    conn.execute(f"delete from contacts where prospect_id in ({marks})", bad)
    conn.execute(f"delete from autonomous_prospect_links where prospect_id in ({marks})", bad)
    conn.execute(f"delete from prospects where id in ({marks})", bad)
    conn.commit()
    return len(bad)


def install_prospect_backfill_boot(app, db_path):
    global _started
    with _lock:
        if _started:
            return app
        _started = True

    def due(conn) -> bool:
        conn.executescript(SCHEDULE_SCHEMA)
        row = conn.execute("select * from prospect_import_schedule where id=1").fetchone()
        clean_total = sum(1 for r in conn.execute("select company,nmls,source_name from prospects") if is_publishable_prospect(r[0], r[1], r[2]))
        if clean_total < 500:
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
                removed_invalid = _clean_catalog(conn)
                matchup = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=85)
                roster = import_missouri_broker_roster(conn, target_minimum=650)
                official = promote_official_roster(conn, target_minimum=650, limit=10000)
                removed_after = _clean_catalog(conn)
                clean_rows = [r for r in conn.execute("select company,nmls,source_name,state from prospects") if is_publishable_prospect(r[0], r[1], r[2])]
                clean_total = len(clean_rows)
                state_rows = conn.execute("""select upper(state),count(*) from prospects
                    where length(trim(coalesce(state,'')))=2 group by upper(state) order by upper(state)""").fetchall()
                now = datetime.now().isoformat(timespec="seconds")
                conn.execute("""update prospect_import_schedule set status='Completed',completed_at=?,last_total=?,last_error='' where id=1""", (now, clean_total))
                conn.commit()
            app.logger.warning(
                "PROSPECT_DAILY completed removed_invalid=%s removed_after=%s matchup_created=%s roster_rows=%s official_created=%s official_updated=%s clean_total=%s states=%s",
                removed_invalid, removed_after, matchup.get("prospects_created", 0),
                roster.get("source_rows", 0), official.get("created", 0), official.get("updated", 0),
                clean_total, len(state_rows),
            )
        except Exception as exc:
            try:
                with closing(_connect(db_path)) as conn:
                    conn.executescript(SCHEDULE_SCHEMA)
                    conn.execute("update prospect_import_schedule set status='Failed',last_error=? where id=1", (str(exc)[:1000],))
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
    app.logger.warning("PROSPECT_AUTOMATION scheduled daily quality cleanup, import, enrichment, and promotion")
    return app


__all__ = ["install_prospect_backfill_boot"]
