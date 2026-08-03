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

    def test_reset_cancels_legacy_autofill_backlog(self):
        with ember_worker._connect(self.db_path) as conn:
            enqueue(conn, "discovery_cycle", state="NC", payload={"state": "NC"})
            enqueue(conn, "discovery_cycle", state="SC", payload={"state": "SC"})
            cancelled = ember_worker._reset_stale_discovery_backlog(conn)
        self.assertEqual(2, cancelled)
        active = self.rows("select state from crawl_jobs where status in ('Queued','Running') order by id")
        self.assertEqual([], active)

    def test_process_one_completes_explicit_job_without_refilling_queue(self):
        result = {
            "state": "NC",
            "companies_seeded": 2,
            "enrichment": {"contacts_found": 4},
            "pending_review": 4,
        }
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
        self.assertEqual(["JobQueued", "JobClaimed", "JobCompleted", "PipelineAdvanced"], events)
        pipeline = self.rows(
            f"select detail_json from activity_events where job_id={explicit_id} and event_type='PipelineAdvanced'"
        )[0]
        self.assertIn('"next_stage": "Human review"', pipeline["detail_json"])
        active = self.rows("select state from crawl_jobs where status in ('Queued','Running')")
        self.assertEqual([], active)


if __name__ == "__main__":
    unittest.main()
