import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from saas import install_saas


class Sprint32BillingTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "brokerbeacon.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""create table prospects(
                id integer primary key,nmls text,company text,city text,state text,
                source_name text,source_url text,verification_status text)""")
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sprint-32-test-secret")
        self.app.add_url_rule("/", "home", lambda: "BrokerBeacon")
        install_saas(self.app, self.db_path, "24.0")
        self.founding = self.app.test_client()
        self._register(self.founding, "owner@example.com", "BrokerBeacon Founding")
        self.customer = self.app.test_client()
        self._register(self.customer, "pilot@example.com", "Pilot Mortgage")
        self.customer.post("/onboarding", data={
            "primary_market": "North Carolina", "team_size": "2–5 people",
            "primary_goal": "Launch a paid pilot",
        })
        with sqlite3.connect(self.db_path) as conn:
            self.workspace_id = conn.execute(
                "select id from saas_workspaces where name='Pilot Mortgage'"
            ).fetchone()[0]
        self.webhook_secret = "whsec_sprint32"

    def tearDown(self):
        self.tempdir.cleanup()

    def _register(self, client, email, company):
        response = client.post("/register", data={
            "name": company + " Owner", "company": company, "email": email,
            "password": "CustomerPassword!32",
        })
        self.assertEqual(response.status_code, 302)

    def _webhook(self, event):
        payload = json.dumps(event, separators=(",", ":")).encode()
        timestamp = int(time.time())
        digest = hmac.new(
            self.webhook_secret.encode(), str(timestamp).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        with patch.dict(os.environ, {
            "STRIPE_WEBHOOK_SECRET": self.webhook_secret,
            "STRIPE_PRICE_ID": "price_starter",
        }, clear=False):
            return self.app.test_client().post(
                "/api/saas/billing/webhook", data=payload,
                headers={"Stripe-Signature": f"t={timestamp},v1={digest}",
                         "Content-Type": "application/json"},
            )

    def _activate_subscription(self):
        response = self._webhook({"type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": str(self.workspace_id), "customer": "cus_pilot",
            "subscription": "sub_pilot", "metadata": {"workspace_id": str(self.workspace_id)},
        }}})
        self.assertEqual(response.status_code, 200)

    def test_owner_can_launch_checkout_without_devtools(self):
        stripe_response = MagicMock()
        stripe_response.__enter__.return_value.read.return_value = json.dumps({
            "url": "https://checkout.stripe.test/session",
        }).encode()
        with patch.dict(os.environ, {
            "STRIPE_PRICE_ID": "price_starter", "STRIPE_SECRET_KEY": "sk_test_sprint32",
        }, clear=False), patch("saas.urlrequest.urlopen", return_value=stripe_response):
            response = self.customer.post("/api/saas/billing/checkout")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["url"], "https://checkout.stripe.test/session")

    def test_subscription_updates_and_invoices_track_payment_health(self):
        self._activate_subscription()
        updated = self._webhook({"type": "customer.subscription.updated", "data": {"object": {
            "id": "sub_pilot", "status": "past_due",
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }}})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.customer.get("/api/saas/billing").get_json()["subscription_status"],
                         "past_due")
        paid = self._webhook({"type": "invoice.paid", "data": {"object": {
            "subscription": "sub_pilot",
        }}})
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(self.customer.get("/api/saas/billing").get_json()["subscription_status"],
                         "active")

    def test_pause_and_cancel_are_distinct_and_do_not_touch_founding_workspace(self):
        self._activate_subscription()
        self._webhook({"type": "customer.subscription.paused", "data": {"object": {
            "id": "sub_pilot",
        }}})
        self.assertEqual(self.customer.get("/api/saas/billing").get_json()["subscription_status"],
                         "paused")
        self._webhook({"type": "customer.subscription.deleted", "data": {"object": {
            "id": "sub_pilot",
        }}})
        self.assertEqual(self.customer.get("/api/saas/billing").get_json()["subscription_status"],
                         "canceled")
        founding = self.founding.get("/api/saas/billing").get_json()
        self.assertEqual((founding["plan"], founding["subscription_status"]),
                         ("Founding", "active"))

    def test_invalid_webhook_signature_is_rejected(self):
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": self.webhook_secret}, clear=False):
            response = self.app.test_client().post(
                "/api/saas/billing/webhook", data=b"{}",
                headers={"Stripe-Signature": "t=1,v1=invalid",
                         "Content-Type": "application/json"},
            )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
