"""Restore and expand BrokerBeacon's valid prospect catalog after startup."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

from autonomous_prospecting import purge_invalid_ember_prospects, promote_warehouse_companies
from official_roster_import import import_missouri_broker_roster, promote_official_roster

_started=False
_lock=threading.Lock()


def _connect(db_path):
    conn=sqlite3.connect(str(db_path),timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute('pragma foreign_keys=on')
    conn.execute('pragma busy_timeout=30000')
    return conn


def install_prospect_backfill_boot(app,db_path):
    global _started
    with _lock:
        if _started: return app
        _started=True

    def run():
        time.sleep(8)
        try:
            with closing(_connect(db_path)) as conn:
                removed=purge_invalid_ember_prospects(conn)
                matchup=promote_warehouse_companies(conn,state='',limit=1000,minimum_score=80)
                roster=import_missouri_broker_roster(conn,target_minimum=500)
                official=promote_official_roster(conn,target_minimum=500,limit=10000)
                state_rows=conn.execute("select upper(state),count(*) from prospects where length(trim(coalesce(state,'')))=2 group by upper(state) order by upper(state)").fetchall()
                total=int(conn.execute('select count(*) from prospects').fetchone()[0])
            app.logger.warning(
                'PROSPECT_EXPANSION completed removed_generic=%s matchup_created=%s roster_rows=%s roster_created=%s roster_updated=%s official_created=%s official_updated=%s visible_total=%s states=%s',
                removed,matchup.get('prospects_created',0),roster.get('source_rows',0),roster.get('created',0),roster.get('updated',0),
                official.get('created',0),official.get('updated',0),total,len(state_rows),
            )
            app.logger.warning('PROSPECT_EXPANSION state_breakdown=%s',[(str(r[0] or ''),int(r[1])) for r in state_rows])
        except Exception:
            app.logger.exception('PROSPECT_EXPANSION failed')

    threading.Thread(target=run,name='official-prospect-expansion',daemon=True).start()
    return app


__all__=['install_prospect_backfill_boot']
