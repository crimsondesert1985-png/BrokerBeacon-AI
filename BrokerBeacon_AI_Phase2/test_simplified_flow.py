import unittest

from flask import Flask, g

from simplified_flow import install_simplified_flow


def make_app(authenticated=True):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test")

    @app.before_request
    def identity():
        g.user_id = 1 if authenticated else None

    @app.get("/")
    def home():
        return '''<!doctype html><html><body><aside><nav>
        <button>Home</button><button>Today</button><button>Prospect Watchtower</button>
        <button>Pipeline</button><button>Call Prep</button><button>Analytics</button>
        <button>Integrations</button><button>Settings</button><button>Billing</button>
        </nav></aside><main><h1>Dashboard</h1></main></body></html>'''

    @app.get("/login")
    def login():
        return "<html><body>Login</body></html>"

    install_simplified_flow(app)
    return app


class SimplifiedFlowTests(unittest.TestCase):
    def test_authenticated_pages_receive_start_here_flow(self):
        response = make_app().test_client().get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        for phrase in ("Start here", "Find prospects", "Review matches", "Contact", "Follow up", "Manage access"):
            self.assertIn(phrase, body)

    def test_flow_explains_or_activates_visible_controls(self):
        body = make_app().test_client().get("/").get_data(as_text=True)
        self.assertIn("explainButtons", body)
        self.assertIn("aria-disabled", body)
        self.assertIn("This tool is unavailable", body)

    def test_navigation_uses_progressive_disclosure(self):
        body = make_app().test_client().get("/").get_data(as_text=True)
        self.assertIn("More tools", body)
        self.assertIn("bb-nav-more", body)
        self.assertIn("primaryTerms", body)

    def test_public_auth_pages_are_not_modified(self):
        response = make_app().test_client().get("/login")
        self.assertNotIn("brokerbeacon-simple-flow", response.get_data(as_text=True))

    def test_unauthenticated_pages_are_not_modified(self):
        response = make_app(authenticated=False).test_client().get("/")
        self.assertNotIn("brokerbeacon-simple-flow", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
