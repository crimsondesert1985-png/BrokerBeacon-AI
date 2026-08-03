import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from drip_campaigns import install_drip_campaigns


class DripCampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        app = Flask(__name__)
        app.secret_key = "test"

        @app.before_request
        def identity():
            g.user_id = 7
            g.workspace_id = 11

        install_drip_campaigns(app, self.db)
        self.client = app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_campaign_requires_steps(self):
        response = self.client.post("/api/drip-campaigns", json={"name": "Empty", "steps": []})
        self.assertEqual(response.status_code, 400)

    def test_create_approve_and_enroll_with_consent(self):
        created = self.client.post(
            "/api/drip-campaigns",
            json={
                "name": "Broker welcome",
                "steps": [
                    {"channel": "email", "delay_days": 0, "subject": "Hello", "body": "Welcome"},
                    {"channel": "sms", "delay_days": 3, "body": "Checking in"},
                ],
            },
        )
        self.assertEqual(created.status_code, 201)
        campaign_id = created.get_json()["campaign_id"]

        blocked = self.client.post(
            f"/api/drip-campaigns/{campaign_id}/enroll",
            json={"prospect_name": "Example Broker", "email": "broker@example.com", "email_consent": True},
        )
        self.assertEqual(blocked.status_code, 409)

        approved = self.client.post(f"/api/drip-campaigns/{campaign_id}/approve")
        self.assertEqual(approved.status_code, 200)

        no_consent = self.client.post(
            f"/api/drip-campaigns/{campaign_id}/enroll",
            json={"prospect_name": "Example Broker", "email": "broker@example.com"},
        )
        self.assertEqual(no_consent.status_code, 400)

        enrolled = self.client.post(
            f"/api/drip-campaigns/{campaign_id}/enroll",
            json={
                "prospect_name": "Example Broker",
                "prospect_key": "example-broker",
                "email": "broker@example.com",
                "email_consent": True,
            },
        )
        self.assertEqual(enrolled.status_code, 201)

        due = self.client.get("/api/drip-campaigns/due")
        payload = due.get_json()
        self.assertEqual(due.status_code, 200)
        self.assertFalse(payload["sending_enabled"])
        self.assertTrue(payload["approval_required"])
        self.assertEqual(len(payload["items"]), 1)

    def test_suppression_blocks_enrollment(self):
        created = self.client.post(
            "/api/drip-campaigns",
            json={"name": "Email", "steps": [{"channel": "email", "body": "Hi"}]},
        )
        campaign_id = created.get_json()["campaign_id"]
        self.client.post(f"/api/drip-campaigns/{campaign_id}/approve")
        self.client.post(
            "/api/drip-suppressions",
            json={"channel": "email", "destination": "stop@example.com", "reason": "unsubscribe"},
        )
        enrolled = self.client.post(
            f"/api/drip-campaigns/{campaign_id}/enroll",
            json={"prospect_name": "Stopped", "email": "stop@example.com", "email_consent": True},
        )
        self.assertEqual(enrolled.status_code, 409)


if __name__ == "__main__":
    unittest.main()
