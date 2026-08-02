from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from founder_briefing import build_briefing, install_founder_briefing


class FounderBriefingTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_empty_database_returns_safe_decision(self):
        with self.connect() as conn:
            result = build_briefing(conn)
        self.assertEqual("Refill the national hunt queue", result["recommended_action"]["title"])
        self.assertEqual("Built with purpose. Dedicated to Aiden.", result["dedication"])
        self.assertFalse(result["outreach_enabled"])

    def test_priority_review_wins_over_generic_queue_activity(self):
        with self.connect() as conn:
            conn.executescript("""
                create table discovered_contacts(id integer primary key, review_status text, opportunity_score integer, created_at text);
                create table crawl_jobs(id integer primary key, status text);
            """)
            conn.execute("insert into discovered_contacts(review_status,opportunity_score,created_at) values('Pending review',91,datetime('now'))")
            conn.execute("insert into crawl_jobs(status) values('Running')")
            result = build_briefing(conn)
        self.assertEqual(1, result["high_priority"])
        self.assertEqual("priority", result["recommended_action"]["kind"])

    def test_decision_sized_review_batch(self):
        with self.connect() as conn:
            conn.execute("create table discovered_contacts(id integer primary key, review_status text)")
            conn.executemany("insert into discovered_contacts(review_status) values('Pending review')", [()] * 27)
            result = build_briefing(conn)
        self.assertIn("next 10", result["recommended_action"]["title"])
        self.assertEqual(27, result["pending_review"])

    def test_api_and_ui_are_platform_owner_only(self):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def owner_context():
            g.is_platform_owner = bool(app.config.get("OWNER"))

        @app.get("/platform/control-tower")
        def control_tower():
            return "<html><body><main>Control Tower</main></body></html>"

        install_founder_briefing(app, self.db_path)
        app.config["OWNER"] = False
        with app.test_client() as client:
            self.assertEqual(403, client.get("/api/platform/founder-briefing").status_code)
            self.assertNotIn("founder-briefing-shell", client.get("/platform/control-tower").get_data(as_text=True))
        app.config["OWNER"] = True
        with app.test_client() as client:
            self.assertEqual(200, client.get("/api/platform/founder-briefing").status_code)
            page = client.get("/platform/control-tower").get_data(as_text=True)
            self.assertIn("founder-briefing-shell", page)
            self.assertIn("Built with purpose. Dedicated to Aiden.", page)
            self.assertIn("Good to have you back, Clay.", page)


if __name__ == "__main__":
    unittest.main()
