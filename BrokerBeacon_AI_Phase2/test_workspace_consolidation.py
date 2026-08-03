import unittest

from flask import Flask

from workspace_consolidation import WORKSPACES, install_workspace_consolidation


class WorkspaceConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        @self.app.get("/")
        def index():
            return "<html><body><aside><nav><button>Prospect Watchtower</button><button>Call Prep</button></nav></aside><main>App</main></body></html>"

        @self.app.get("/login")
        def login():
            return "<html><body>Login</body></html>"

        install_workspace_consolidation(self.app)
        self.client = self.app.test_client()

    def test_five_core_workspaces_are_defined(self):
        self.assertEqual([w["id"] for w in WORKSPACES], ["home", "prospects", "outreach", "intelligence", "settings"])

    def test_authenticated_html_gets_consolidation_ui(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("brokerbeacon-workspace-consolidation", body)
        self.assertIn("More tools", body)
        self.assertIn("Core workspaces", body)

    def test_public_auth_pages_are_untouched(self):
        body = self.client.get("/login").get_data(as_text=True)
        self.assertNotIn("brokerbeacon-workspace-consolidation", body)


if __name__ == "__main__":
    unittest.main()
