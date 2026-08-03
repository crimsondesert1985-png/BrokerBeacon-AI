from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from role_management import ROLE_CATALOG, install_role_management


SCHEMA = """
create table saas_users(
 id integer primary key,email text,full_name text,password_hash text default '',
 is_platform_owner integer not null default 0,is_active integer not null default 1,
 last_login_at text default '',created_at text default '',updated_at text default ''
);
create table saas_memberships(
 id integer primary key,workspace_id integer not null,user_id integer not null,
 role text not null,created_at text default ''
);
create table saas_audit_log(
 id integer primary key,workspace_id integer,user_id integer,action text,target_type text,
 target_id text,detail_json text,ip_address text,created_at text
);
"""


class RoleManagementTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                "insert into saas_users(id,email,full_name,is_platform_owner,is_active) values(?,?,?,?,1)",
                [
                    (1, "founder@example.com", "Founder", 1),
                    (2, "admin@example.com", "Admin", 0),
                    (3, "manager@example.com", "Manager", 0),
                    (4, "user@example.com", "User", 0),
                ],
            )
            conn.executemany(
                "insert into saas_memberships(id,workspace_id,user_id,role) values(?,?,?,?)",
                [
                    (1, 1, 1, "Owner"),
                    (2, 1, 2, "Owner"),
                    (3, 1, 3, "Manager"),
                    (4, 1, 4, "AE"),
                ],
            )
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test")
        install_role_management(self.app, self.db_path)
        self.context = {"user_id": 2, "workspace_id": 1, "role": "Owner", "platform": False}

        @self.app.before_request
        def auth_context():
            g.user_id = self.context["user_id"]
            g.workspace_id = self.context["workspace_id"]
            g.membership_role = self.context["role"]
            g.is_platform_owner = self.context["platform"]

        self.client = self.app.test_client()

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def test_role_catalog_uses_clear_labels(self):
        self.assertEqual("Workspace Admin", ROLE_CATALOG["Owner"]["label"])
        self.assertEqual("Manager", ROLE_CATALOG["Manager"]["label"])
        self.assertEqual("User", ROLE_CATALOG["AE"]["label"])
        self.assertEqual("Viewer", ROLE_CATALOG["Read Only"]["label"])

    def test_manager_can_only_assign_user_or_viewer(self):
        self.context.update(user_id=3, role="Manager")
        response = self.client.patch("/api/workspace/members/4/role", json={"role": "Read Only"})
        self.assertEqual(200, response.status_code)
        denied = self.client.patch("/api/workspace/members/4/role", json={"role": "Owner"})
        self.assertEqual(403, denied.status_code)

    def test_last_workspace_admin_is_protected(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("delete from saas_memberships where id=1")
            conn.commit()
        response = self.client.patch("/api/workspace/members/2/role", json={"role": "Manager"})
        self.assertEqual(409, response.status_code)
        self.assertIn("last admin", response.get_json()["error"].lower())

    def test_platform_owner_role_cannot_be_changed(self):
        response = self.client.patch("/api/workspace/members/1/role", json={"role": "AE"})
        self.assertEqual(403, response.status_code)
        self.assertIn("platform owner", response.get_json()["error"].lower())

    def test_team_page_has_guided_invitation_flow(self):
        response = self.client.get("/workspace/team")
        self.assertEqual(200, response.status_code)
        body = response.get_data(as_text=True)
        self.assertIn("Invite people. Keep control.", body)
        self.assertIn("Send secure invitation", body)
        self.assertIn("Pending invitations", body)
        self.assertIn("Passwords stay private", body)
        self.assertIn("/api/saas/invitations", body)
        self.assertIn("/api/saas/members/", body)

    def test_non_manager_cannot_open_team_page(self):
        self.context.update(user_id=4, role="AE")
        response = self.client.get("/workspace/team")
        self.assertEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()
