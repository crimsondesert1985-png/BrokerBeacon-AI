import unittest

from ember_status_api import SETUP_HTML, build_guidance


class Sprint49GuidedFlowTests(unittest.TestCase):
    def test_missing_provider_gives_one_clear_connect_action(self):
        guidance = build_guidance(
            worker_healthy=True,
            stale=False,
            sources={"configured_providers": [], "paused_states": []},
        )
        self.assertEqual(guidance["stage"], "connect")
        self.assertIn("one search provider", guidance["message"])
        self.assertIn("Render", guidance["action"])

    def test_unhealthy_worker_prioritizes_restore(self):
        guidance = build_guidance(
            worker_healthy=False,
            stale=True,
            sources={"configured_providers": ["brave"], "paused_states": []},
        )
        self.assertEqual(guidance["stage"], "restore")
        self.assertIn("heartbeat is stale", guidance["message"])
        self.assertIn("worker logs", guidance["action"])

    def test_paused_states_explain_self_protection(self):
        guidance = build_guidance(
            worker_healthy=True,
            stale=False,
            sources={
                "configured_providers": ["tavily"],
                "paused_states": [{"state": "NC"}, {"state": "SC"}],
            },
        )
        self.assertEqual(guidance["stage"], "monitor")
        self.assertIn("2 states are", guidance["message"])
        self.assertIn("return automatically", guidance["action"])

    def test_ready_state_directs_owner_to_review_before_promotion(self):
        guidance = build_guidance(
            worker_healthy=True,
            stale=False,
            sources={"configured_providers": ["brave"], "paused_states": []},
        )
        self.assertEqual(guidance["stage"], "discover")
        self.assertIn("brave", guidance["message"])
        self.assertIn("verified prospects", guidance["action"])

    def test_setup_page_follows_product_standard_and_has_no_dead_information(self):
        for word in ("Intuitive", "Flashy", "Informative", "Simple"):
            self.assertIn(word, SETUP_HTML)
        for variable in (
            "BRAVE_SEARCH_API_KEY",
            "TAVILY_API_KEY",
            "FIRECRAWL_API_KEY",
            "SERPAPI_API_KEY",
            "GOOGLE_CSE_API_KEY",
            "GOOGLE_CSE_ID",
        ):
            self.assertIn(variable, SETUP_HTML)
        self.assertIn("Automatic outreach", SETUP_HTML)
        self.assertIn("Automatic CRM promotion", SETUP_HTML)
        self.assertIn("Human verification", SETUP_HTML)
        self.assertIn("Refresh status", SETUP_HTML)


if __name__ == "__main__":
    unittest.main()
