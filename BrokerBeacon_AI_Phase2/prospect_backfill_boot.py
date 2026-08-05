"""Run an idempotent Mortgage Matchup warehouse-to-CRM backfill after startup."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

from autonomous_prospecting import purge_invalid_ember_prospects, promote_warehouse_companies

_started = False
_lock = threading.Lock()


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def install_prospect_backfill_boot(app, db_path):
    global _started
    with _lock:
        if _started:
            return app
        _started = True

    def run():
        time.sleep(12)
        try:
            with closing(_connect(db_path)) as conn:
                removed_before = purge_invalid_ember_prospects(conn)
                result = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=80)
                removed_after = purge_invalid_ember_prospects(conn)
                visible = int(conn.execute(
                    """select count(distinct p.id)
                       from prospects p
                       join autonomous_prospect_links l on l.prospect_id=p.id
                       join warehouse_source_records wr on wr.entity_type='company' and wr.entity_id=l.warehouse_company_id
                       join warehouse_sources s on s.id=wr.source_id
                       where s.name='Mortgage Matchup'"""
                ).fetchone()[0])
            app.logger.warning(
                "EMBER_PROSPECT_BACKFILL matchup_only removed_before=%s examined=%s created=%s updated=%s contacts=%s duplicates=%s rejected=%s removed_after=%s visible=%s",
                removed_before, result.get("warehouse_examined", 0), result.get("prospects_created", 0),
                result.get("prospects_updated", 0), result.get("contacts_created", 0),
                result.get("duplicates_skipped", 0), result.get("rejected", 0), removed_after, visible,
            )
        except Exception:
            app.logger.exception("EMBER_PROSPECT_BACKFILL matchup-only run failed")

    threading.Thread(target=run, name="ember-prospect-backfill", daemon=True).start()
    return app


__all__ = ["install_prospect_backfill_boot"]
