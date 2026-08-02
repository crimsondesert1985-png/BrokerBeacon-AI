from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta

from ember_jobs import claim_next, complete, enqueue, fail, initialize, recover_stale_locks


class EmberJobQueueTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        initialize(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_claim_is_atomic_for_single_job(self):
        job_id = enqueue(self.conn, "discovery_cycle", state="NC")
        first = claim_next(self.conn, "worker-a")
        second = claim_next(self.conn, "worker-b")
        self.assertEqual(job_id, first["id"])
        self.assertIsNone(second)

    def test_complete_requires_claiming_worker(self):
        job_id = enqueue(self.conn, "discovery_cycle", state="NC")
        claim_next(self.conn, "worker-a")
        self.assertFalse(complete(self.conn, job_id, "worker-b"))
        self.assertTrue(complete(self.conn, job_id, "worker-a", {"contacts": 2}))
        status = self.conn.execute("select status from crawl_jobs where id=?", (job_id,)).fetchone()[0]
        self.assertEqual("Completed", status)

    def test_failure_requeues_until_attempt_limit(self):
        job_id = enqueue(self.conn, "discovery_cycle", max_attempts=2)
        claim_next(self.conn, "worker-a")
        self.assertEqual("Queued", fail(self.conn, job_id, "worker-a", "temporary", retry_delay_seconds=1))
        self.conn.execute("update crawl_jobs set available_at=? where id=?", (datetime.now().isoformat(timespec="seconds"), job_id))
        self.conn.commit()
        claim_next(self.conn, "worker-a")
        self.assertEqual("Failed", fail(self.conn, job_id, "worker-a", "permanent", retry_delay_seconds=1))

    def test_stale_lock_is_recovered(self):
        job_id = enqueue(self.conn, "discovery_cycle", max_attempts=3)
        claim_next(self.conn, "worker-a")
        expired = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
        self.conn.execute("update crawl_jobs set lock_expires_at=? where id=?", (expired, job_id))
        self.conn.commit()
        self.assertEqual(1, recover_stale_locks(self.conn))
        row = self.conn.execute("select status,claimed_by from crawl_jobs where id=?", (job_id,)).fetchone()
        self.assertEqual("Queued", row["status"])
        self.assertEqual("", row["claimed_by"])

    def test_activity_events_are_written(self):
        job_id = enqueue(self.conn, "discovery_cycle", state="VA")
        claim_next(self.conn, "worker-a")
        complete(self.conn, job_id, "worker-a")
        events = [row[0] for row in self.conn.execute("select event_type from activity_events order by id")]
        self.assertEqual(["JobQueued", "JobClaimed", "JobCompleted"], events)


if __name__ == "__main__":
    unittest.main()
