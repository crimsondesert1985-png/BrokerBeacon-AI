from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ember_worker
from ember_jobs import enqueue, initialize


class FakeLogger:
    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class FakeApp:
    logger = FakeLogger()


class ScoutQueueMigrationTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            initialize(conn)

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def rows(self, sql):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql).fetchall()

    def test_seed_if_idle_creates_bounded_national_backlog_once(self):
        with ember_worker._connect(self.db_path) as conn:
            first = ember_worker._seed_if_idle(conn)
            second = ember_worker._seed_if_idle(conn)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        active = self.rows("select state from crawl_jobs where status in ('Queued','Running') order by id")
        self.assertGreaterEqual(len(active), 1)
        self.assertLessEqual(len(active), 6)
        self.assertEqual(len(active), len({row["state"] for row in active}))

    def test_process_one_completes_explicit_job_and_refills_national_queue(self):
        result = {"state": "NC", "companies_seeded": 2, "enrichment": {"contacts_found": 4}}
        with ember_worker._connect(self.db_path) as conn:
            explicit_id = enqueue(
                conn,
                "discovery_cycle",
                state="NC",
                payload={"state": "NC", "company_limit": 2, "contact_limit": 25},
                priority=1,
            )
        with patch.object(ember_worker, "launch", return_value=result):
            ember_worker._process_one(FakeApp(), self.db_path)
        job = self.rows(f"select status from crawl_jobs where id={explicit_id}")[0]
        self.assertEqual("Completed", job["status"])
        events = [row[0] for row in self.rows(f"select event_type from activity_events where job_id={explicit_id} order by id")]
        self.assertEqual(["JobQueued", "JobClaimed", "JobCompleted"], events)
        active = self.rows("select state from crawl_jobs where status in ('Queued','Running')")
        self.assertGreaterEqual(len(active), 1)
        self.assertLessEqual(len(active), 6)


if __name__ == "__main__":
    unittest.main()
