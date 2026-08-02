import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
