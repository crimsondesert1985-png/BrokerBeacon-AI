"""Run an idempotent warehouse-to-CRM backfill after each production start."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

from autonomous_prospecting import promote_warehouse_companies

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
        time.sleep(8)
        totals = {
            "warehouse_examined": 0,
            "prospects_created": 0,
            "prospects_updated": 0,
            "contacts_created": 0,
            "duplicates_skipped": 0,
            "rejected": 0,
        }
        try:
            with closing(_connect(db_path)) as conn:
                for state in [""]:
                    result = promote_warehouse_companies(
                        conn,
                        state=state,
                        limit=500,
                        minimum_score=35,
                    )
                    for key in totals:
                        totals[key] += int(result.get(key, 0) or 0)
                visible = int(conn.execute("select count(*) from prospects").fetchone()[0])
                linked = int(conn.execute("select count(*) from autonomous_prospect_links").fetchone()[0])
            app.logger.warning(
                "EMBER_PROSPECT_BACKFILL completed examined=%s created=%s updated=%s contacts=%s duplicates=%s rejected=%s visible_prospects=%s linked=%s",
                totals["warehouse_examined"], totals["prospects_created"], totals["prospects_updated"],
                totals["contacts_created"], totals["duplicates_skipped"], totals["rejected"],
                visible, linked,
            )
        except Exception:
            app.logger.exception("EMBER_PROSPECT_BACKFILL failed")

    threading.Thread(target=run, name="ember-prospect-backfill", daemon=True).start()
    return app


__all__ = ["install_prospect_backfill_boot"]
