from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from prospect_flow import install_prospect_flow


class ProspectFlowTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")

        @self.app.before_request
        def identity():
            g.user_id = 7
            g.workspace_id = 11

        @self.app.get("/")
        def home():
            return """<!doctype html><html><body><main><table><tbody>
            <tr><td>Carolina Home Loans</td><td>owner@example.com</td><td>Score: 92</td></tr>
            </tbody></table><div class='toast'></div></main></body></html>"""

        install_prospect_flow(self.app, self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def test_authenticated_html_receives_one_click_workflow(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("One-click prospect workflow", body)
        self.assertIn("Why this prospect matters", body)
        self.assertIn("Recommended next action", body)
        self.assertIn("Follow up in 3 days", body)
        self.assertIn("Quietly dedicated to Aiden", body)

    def test_contact_action_logs_and_advances_stage(self):
        response = self.client.post(
            "/api/prospect-flow/action",
            json={
                "prospect_name": "Carolina Home Loans",
                "action": "contact",
                "channel": "email",
                "outcome": "Contact initiated",
                "note": "Owner email verified",
            },
        )
        self.assertEqual(201, response.status_code)
        payload = response.get_json()
        self.assertEqual("Contacted", payload["stage"])
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "select stage,channel,outcome,note from prospect_workflow_events"
            ).fetchone()
        self.assertEqual(("Contacted", "email", "Contact initiated", "Owner email verified"), row)

    def test_follow_up_creates_date_and_status_endpoint_returns_latest(self):
        created = self.client.post(
            "/api/prospect-flow/action",
            json={"prospect_name": "Carolina Home Loans", "action": "follow_up", "days": 3},
        ).get_json()
        self.assertTrue(created["follow_up_at"])
        status = self.client.get("/api/prospect-flow/status/" + created["prospect_key"])
        self.assertEqual(200, status.status_code)
        self.assertEqual("Follow Up", status.get_json()["item"]["stage"])

    def test_invalid_action_is_rejected(self):
        response = self.client.post(
            "/api/prospect-flow/action",
            json={"prospect_name": "Carolina Home Loans", "action": "delete"},
        )
        self.assertEqual(400, response.status_code)


if __name__ == "__main__":
    unittest.main()
