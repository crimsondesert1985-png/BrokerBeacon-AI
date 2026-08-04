import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from flask import Flask

from saas import install_saas


class Sprint31OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "brokerbeacon.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""create table prospects(
                id integer primary key,nmls text,company text,city text,state text,
                source_name text,source_url text,verification_status text)""")
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sprint-31-test-secret")
        self.app.add_url_rule("/", "home", lambda: "BrokerBeacon")
        install_saas(self.app, self.db_path, "23.0")
        self.founding = self.app.test_client()
        self._register(self.founding, "clay@example.com", "BrokerBeacon Founding")
        self.customer = self.app.test_client()
        self._register(self.customer, "pilot@example.com", "Pilot Mortgage")

    def tearDown(self):
        self.tempdir.cleanup()

    def _register(self, client, email, company):
        response = client.post("/register", data={
            "name": company+" Owner", "company": company, "email": email,
            "password": "CustomerPassword!31",
        })
        self.assertEqual(response.status_code, 302)

    def test_customer_is_guided_through_onboarding_without_affecting_founding_owner(self):
        self.assertEqual(self.customer.get("/").status_code, 302)
        self.assertIn("/onboarding", self.customer.get("/").location)
        completed = self.customer.post("/onboarding", data={
            "primary_market": "North Carolina", "team_size": "2–5 people",
            "primary_goal": "Prioritize broker relationships",
        })
        self.assertEqual(completed.status_code, 302)
        self.assertEqual(self.customer.get("/").status_code, 200)
        self.assertEqual(self.founding.get("/").status_code, 200)

    def test_billing_status_exposes_trial_seats_and_usage_limits(self):
        status = self.customer.get("/api/saas/billing").get_json()
        self.assertEqual(status["plan"], "Trial")
        self.assertEqual(status["subscription_status"], "trialing")
        self.assertEqual(status["seat_limit"], 5)
        self.assertEqual(status["ai_actions_limit"], 500)
        self.assertFalse(status["stripe_configured"])

    def test_workspace_invitation_is_delivered_by_email(self):
        self.customer.post("/onboarding", data={
            "primary_market": "North Carolina", "team_size": "2–5 people",
            "primary_goal": "Invite the pilot team",
        })
        invited = self.customer.post("/api/saas/invitations", json={
            "email": "teammate@example.com", "role": "AE",
        })
        self.assertEqual(invited.status_code, 201)
        self.assertTrue(invited.get_json()["email_delivered"])
        self.assertIn("/invite/", invited.get_json()["accept_url"])
        self.assertEqual(invited.headers["Cache-Control"], "no-store")
        email = self.app.extensions["security_outbox"][-1]
        self.assertEqual(email["to"], "teammate@example.com")
        self.assertIn("/invite/", email["text"])

    def test_verified_stripe_webhook_activates_only_target_customer(self):
        with sqlite3.connect(self.db_path) as conn:
            customer_id = conn.execute("select id from saas_workspaces where name='Pilot Mortgage'").fetchone()[0]
            founding_id = conn.execute("select id from saas_workspaces where is_founding=1").fetchone()[0]
        event = {"type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": str(customer_id), "customer": "cus_test",
            "subscription": "sub_test", "metadata": {"workspace_id": str(customer_id)},
        }}}
        payload = json.dumps(event, separators=(",", ":")).encode()
        timestamp = int(time.time())
        secret = "whsec_sprint31"
        digest = hmac.new(secret.encode(), str(timestamp).encode()+b"."+payload,
                          hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": secret,
                                     "STRIPE_PRICE_ID": "price_starter"}, clear=False):
            response = self.app.test_client().post("/api/saas/billing/webhook", data=payload,
                headers={"Stripe-Signature": f"t={timestamp},v1={digest}",
                         "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        with sqlite3.connect(self.db_path) as conn:
            customer = conn.execute("select plan,subscription_status from saas_workspaces where id=?",
                                    (customer_id,)).fetchone()
            founding = conn.execute("select plan,subscription_status from saas_workspaces where id=?",
                                    (founding_id,)).fetchone()
        self.assertEqual(customer, ("Starter", "active"))
        self.assertEqual(founding, ("Founding", "active"))


if __name__ == "__main__":
    unittest.main()
