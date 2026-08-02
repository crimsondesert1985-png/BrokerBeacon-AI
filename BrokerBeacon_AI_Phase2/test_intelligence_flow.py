from __future__ import annotations

import sqlite3
import unittest

from intelligence_flow import advance_intelligence


class IntelligenceFlowTests(unittest.TestCase):
    def test_missing_discovery_tables_defer_without_crashing_worker(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = advance_intelligence(conn, state="NC")
        self.assertEqual("Deferred", result["status"])
        self.assertEqual("NC", result["state"])
        self.assertEqual(0, result["company_nodes"])

    def test_limits_are_bounded(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = advance_intelligence(conn, state="TX", limit=999999)
        self.assertEqual("Deferred", result["status"])
        self.assertEqual("TX", result["state"])


if __name__ == "__main__":
    unittest.main()
