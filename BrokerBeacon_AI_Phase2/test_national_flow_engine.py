import sqlite3
import unittest
from unittest.mock import patch

import ember_hunt
import ember_worker


class NationalFlowEngineTests(unittest.TestCase):
    def test_burst_stops_when_queue_is_empty(self):
        with patch.object(ember_worker, "_process_one", side_effect=[True, True, False]) as process:
            completed = ember_worker._run_burst(object(), "unused.db", 6, 0)
        self.assertEqual(completed, 2)
        self.assertEqual(process.call_count, 3)

    def test_burst_respects_configured_limit(self):
        with patch.object(ember_worker, "_process_one", return_value=True) as process:
            completed = ember_worker._run_burst(object(), "unused.db", 3, 0)
        self.assertEqual(completed, 3)
        self.assertEqual(process.call_count, 3)

    def test_burst_never_runs_zero_jobs(self):
        with patch.object(ember_worker, "_process_one", return_value=False) as process:
            completed = ember_worker._run_burst(object(), "unused.db", 0, 0)
        self.assertEqual(completed, 0)
        self.assertEqual(process.call_count, 1)

    def _seed_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            create table national_broker_index(
                id integer primary key,
                company text,
                state text,
                source_url text,
                city text,
                nmls text,
                source_name text
            );
            create table ember_company_history(
                state text,
                source_url text,
                next_crawl_at text
            );
            """
        )
        conn.executemany(
            "insert into national_broker_index(id,company,state,source_url) values(?,?,?,?)",
            [
                (1, "Cooling Mortgage", "VA", "https://cooling.example"),
                (2, "Fresh Mortgage", "VA", "https://fresh.example"),
                (3, "Wrapped Mortgage", "VA", "https://wrapped.example"),
            ],
        )
        conn.execute(
            "insert into ember_company_history(state,source_url,next_crawl_at) values(?,?,?)",
            ("VA", "https://cooling.example", "2999-01-01T00:00:00"),
        )
        return conn

    def test_seed_rows_skip_sources_still_on_cooldown(self):
        conn = self._seed_db()
        rows = ember_hunt._seed_rows(conn, "VA", 0, 10)
        self.assertEqual([row["company"] for row in rows], ["Fresh Mortgage", "Wrapped Mortgage"])

    def test_seed_rows_wrap_to_first_eligible_source(self):
        conn = self._seed_db()
        rows = ember_hunt._seed_rows(conn, "VA", 3, 10)
        self.assertEqual([row["company"] for row in rows], ["Fresh Mortgage", "Wrapped Mortgage"])


if __name__ == "__main__":
    unittest.main()
