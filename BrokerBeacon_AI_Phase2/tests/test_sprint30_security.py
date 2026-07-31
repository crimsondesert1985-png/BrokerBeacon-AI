import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from data_durability import create_backup, verify_backup_restore
from saas import install_saas


class Sprint30SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "brokerbeacon.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""create table prospects(
                id integer primary key,nmls text,company text,city text,state text,
                source_name text,source_url text,verification_status text)""")
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sprint-30-test-secret")
        install_saas(self.app, self.db_path, "22.0")
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def register(self):
        return self.client.post("/register", data={
            "name": "Clay Carr", "company": "BrokerBeacon Founding",
            "email": "clay@example.com", "password": "OwnerPassword!30",
        })

    def email_token(self, subject):
        email = next(item for item in reversed(self.app.extensions["security_outbox"])
                     if item["subject"] == subject)
        return re.search(r"[?&]token=([^\s]+)", email["text"]).group(1)

    def verify_and_login(self):
        self.register()
        token = self.email_token("Verify your BrokerBeacon email")
        self.client.get("/verify-email", query_string={"token": token})
        self.client.post("/logout")
        response = self.client.post("/login", data={
            "email": "clay@example.com", "password": "OwnerPassword!30",
        })
        self.assertEqual(response.status_code, 302)

    def test_new_account_requires_email_verification_for_later_login(self):
        self.register()
        self.client.post("/logout")
        blocked = self.client.post("/login", data={
            "email": "clay@example.com", "password": "OwnerPassword!30",
        })
        self.assertIn(b"Verify your email", blocked.data)
        token = self.email_token("Verify your BrokerBeacon email")
        self.assertEqual(self.client.get("/verify-email", query_string={"token": token}).status_code, 302)
        allowed = self.client.post("/login", data={
            "email": "clay@example.com", "password": "OwnerPassword!30",
        })
        self.assertEqual(allowed.status_code, 302)

    def test_repeated_login_failures_are_rate_limited_and_audited(self):
        self.verify_and_login()
        self.client.post("/logout")
        for _ in range(5):
            self.client.post("/login", data={"email": "clay@example.com", "password": "wrong"})
        blocked = self.client.post("/login", data={"email": "clay@example.com", "password": "wrong"})
        self.assertEqual(blocked.status_code, 429)
        with sqlite3.connect(self.db_path) as conn:
            actions = {row[0] for row in conn.execute("select action from saas_audit_log")}
        self.assertIn("security.login_failed", actions)
        self.assertIn("security.login_blocked", actions)

    def test_password_reset_revokes_existing_sessions_and_is_one_time(self):
        self.verify_and_login()
        other = self.app.test_client()
        other.post("/login", data={"email": "clay@example.com", "password": "OwnerPassword!30"})
        self.client.post("/forgot-password", data={"email": "clay@example.com"})
        token = self.email_token("Reset your BrokerBeacon password")
        changed = self.client.post("/reset-password", data={
            "token": token, "password": "ReplacementPassword!30",
        })
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(other.get("/api/saas/context").status_code, 401)
        reused = self.client.post("/reset-password", data={
            "token": token, "password": "AnotherPassword!30",
        })
        self.assertIn(b"invalid or expired", reused.data)

    def test_backup_is_restored_and_verified_non_destructively(self):
        backup = create_backup(self.db_path, reason="sprint-30")
        result = verify_backup_restore(backup)
        self.assertTrue(result["ok"])
        self.assertGreater(result["tables"], 0)


if __name__ == "__main__":
    unittest.main()
