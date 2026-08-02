import os
import sqlite3
import unittest
from unittest.mock import patch

import ember_hunt
import public_search_connector
from source_resilience import record_yield, source_health, state_available


class SourceResilienceTests(unittest.TestCase):
    def connect(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def test_zero_yield_pauses_state_after_three_runs(self):
        conn = self.connect()
        self.assertFalse(record_yield(conn, "NC", companies=0, contacts=0)["paused"])
        self.assertFalse(record_yield(conn, "NC", companies=0, contacts=0)["paused"])
        result = record_yield(conn, "NC", companies=0, contacts=0)
        self.assertTrue(result["paused"])
        self.assertFalse(state_available(conn, "NC"))

    def test_productive_run_resets_zero_yield_streak(self):
        conn = self.connect()
        record_yield(conn, "SC", companies=0, contacts=0)
        result = record_yield(conn, "SC", companies=2, contacts=0)
        self.assertEqual(result["zero_yield_streak"], 0)
        self.assertFalse(result["paused"])
        self.assertTrue(state_available(conn, "SC"))

    def test_source_health_lists_configured_provider_without_secrets(self):
        conn = self.connect()
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "secret"}, clear=True):
            health = source_health(conn)
        self.assertEqual(health["configured_providers"], ["brave"])
        self.assertTrue(health["search_ready"])
        self.assertNotIn("secret", str(health))

    def test_search_uses_all_configured_providers_and_keeps_provenance(self):
        response = {
            "results": [{"title": "Example Mortgage", "description": "NMLS 12345", "url": "https://example.com/", "providers": [{"provider": "brave", "rank": 1}]}],
            "provider_stats": {"brave": {"status": "Completed", "results": 1}},
        }
        with patch.object(public_search_connector, "configured_providers", return_value=["brave"]), \
             patch.object(public_search_connector, "search_all", return_value=response) as search:
            result = public_search_connector.search_provider("mortgage broker NC", count=5)
        self.assertEqual(result["results"][0]["providers"][0]["provider"], "brave")
        search.assert_called_once_with("mortgage broker NC", limit_per_provider=5, providers=["brave"])

    def test_choose_state_skips_paused_state(self):
        conn = self.connect()
        conn.execute("create table ember_state_cursors(state text primary key,last_run_at text,companies_processed integer)")
        record_yield(conn, "AL", companies=0, contacts=0, threshold=1)
        with patch.object(ember_hunt, "approved_states", return_value=["AL", "AK"]):
            self.assertEqual(ember_hunt.choose_state(conn), "AK")


if __name__ == "__main__":
    unittest.main()
