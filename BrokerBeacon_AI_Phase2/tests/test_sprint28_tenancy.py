import importlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


class Sprint28TenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tempdir.name) / "brokerbeacon.db"
        os.environ["BROKERBEACON_DB_PATH"] = str(cls.db_path)
        os.environ["SECRET_KEY"] = "sprint-28-test-secret"
        os.environ["ENABLE_SCOUT_AUTOPILOT_WORKER"] = "0"
        phase2 = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(phase2))
        cls.module = importlib.import_module("app")
        cls.module.app.config.update(TESTING=True)

        with sqlite3.connect(cls.db_path) as conn:
            conn.execute("""insert into prospects(company,owner,city,state,signal,team,score,
                email,phone,status,source,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("Founding Broker", "Clay", "Charlotte", "NC", "Manual", 1, 80,
                 "founding@example.com", "", "New", "Pre-SaaS", cls.module.NOW(), cls.module.NOW()))

        cls.founding = cls.module.app.test_client()
        response = cls.founding.post("/register", data={
            "name": "Clay Carr", "company": "BrokerBeacon Founding",
            "email": "clay@example.com", "password": "FoundingPassword!28",
        })
        assert response.status_code == 302

        cls.customer = cls.module.app.test_client()
        response = cls.customer.post("/register", data={
            "name": "Customer Owner", "company": "Customer Workspace",
            "email": "customer@example.com", "password": "CustomerPassword!28",
        })
        assert response.status_code == 302

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_founding_records_are_preserved_but_hidden_from_customer(self):
        founding = self.founding.get("/api/prospects").get_json()
        customer = self.customer.get("/api/prospects").get_json()
        self.assertEqual([row["company"] for row in founding], ["Founding Broker"])
        self.assertNotIn("Founding Broker", [row["company"] for row in customer])

    def test_customer_writes_cannot_be_read_by_founding_workspace(self):
        response = self.customer.post("/api/prospects", json={
            "company": "Private Customer Broker", "state": "SC", "authorized_use": True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Private Customer Broker", [row["company"] for row in self.customer.get("/api/prospects").get_json()])
        self.assertNotIn("Private Customer Broker", [row["company"] for row in self.founding.get("/api/prospects").get_json()])

    def test_non_members_cannot_switch_workspaces(self):
        context = self.founding.get("/api/saas/context").get_json()
        founding_workspace = context["workspace_id"]
        response = self.customer.post("/api/saas/workspace/switch", json={"workspace_id": founding_workspace})
        self.assertEqual(response.status_code, 403)

    def test_invitation_acceptance_adds_only_the_invited_workspace(self):
        invitation = self.founding.post("/api/saas/invitations", json={
            "email": "ae@example.com", "role": "AE",
        })
        self.assertEqual(invitation.status_code, 201)
        token = invitation.get_json()["invitation_token"]
        invitee = self.module.app.test_client()
        accepted = invitee.post(f"/invite/{token}", data={
            "name": "Invited AE", "password": "InvitedPassword!28",
        })
        self.assertEqual(accepted.status_code, 302)
        context = invitee.get("/api/saas/context").get_json()
        self.assertEqual(context["role"], "AE")
        self.assertEqual(len(context["workspaces"]), 1)
        self.assertEqual([row["company"] for row in invitee.get("/api/prospects").get_json()],
                         ["Founding Broker"])
        user_id = context["user"]["id"]
        changed = self.founding.put(f"/api/saas/members/{user_id}", json={"role": "Manager"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(invitee.get("/api/saas/context").get_json()["role"], "Manager")
        removed = self.founding.delete(f"/api/saas/members/{user_id}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(invitee.get("/api/prospects").status_code, 403)


if __name__ == "__main__":
    unittest.main()
