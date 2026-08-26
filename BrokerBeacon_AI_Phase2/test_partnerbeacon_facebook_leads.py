import os
import tempfile
import unittest

from flask import Flask, g

from partnerbeacon_facebook_leads import install_facebook_purchase_leads


class FacebookPurchaseLeadTests(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db.close()
        self.app = Flask(__name__)
        self.app.secret_key = "test"

        @self.app.before_request
        def attach_user():
            g.user_id = 1
            g.workspace_id = 1

        install_facebook_purchase_leads(self.app, self.db.name)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.db.name)

    def test_manual_lead_creates_task_and_drip(self):
        res = self.client.post(
            "/api/partnerbeacon/leads/manual",
            json={
                "first_name": "Ava",
                "last_name": "Cole",
                "email": "ava@example.com",
                "phone": "7045550100",
                "market": "Charlotte, NC",
                "timeframe": "0-3 months",
                "sms_consent": True,
                "email_consent": True,
            },
        )
        self.assertEqual(res.status_code, 201)
        lead_id = res.get_json()["lead_id"]
        detail = self.client.get(f"/api/partnerbeacon/leads/{lead_id}").get_json()
        self.assertEqual(detail["item"]["stage"], "New Lead")
        self.assertGreaterEqual(detail["item"]["score"], 60)
        self.assertTrue(detail["tasks"])
        self.assertTrue(detail["drips"])
        self.assertIn("home-purchase", detail["drafts"]["sms"])

    def test_duplicate_email_does_not_create_second_lead(self):
        payload = {"first_name": "Ava", "email": "ava@example.com", "sms_consent": True}
        first = self.client.post("/api/partnerbeacon/leads/manual", json=payload)
        second = self.client.post("/api/partnerbeacon/leads/manual", json=payload)
        self.assertTrue(first.get_json()["created"])
        self.assertFalse(second.get_json()["created"])

    def test_webhook_verify(self):
        os.environ["FACEBOOK_VERIFY_TOKEN"] = "secret-token"
        res = self.client.get(
            "/webhooks/facebook/leads",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "secret-token",
                "hub.challenge": "12345",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.decode(), "12345")

    def test_stage_change_stops_drip_when_dead(self):
        res = self.client.post(
            "/api/partnerbeacon/leads/manual",
            json={"full_name": "Pat Lee", "phone": "7045550199", "sms_consent": True},
        )
        lead_id = res.get_json()["lead_id"]
        self.client.post(f"/api/partnerbeacon/leads/{lead_id}/stage", json={"stage": "Dead"})
        detail = self.client.get(f"/api/partnerbeacon/leads/{lead_id}").get_json()
        self.assertEqual(detail["item"]["stage"], "Dead")
        self.assertTrue(all(row["status"] == "stopped" for row in detail["drips"]))


if __name__ == "__main__":
    unittest.main()
