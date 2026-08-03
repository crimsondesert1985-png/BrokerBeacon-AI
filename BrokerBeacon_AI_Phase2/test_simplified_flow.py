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


def test_authenticated_pages_receive_start_here_flow():
    response = make_app().test_client().get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Start here" in body
    assert "Find prospects" in body
    assert "Review matches" in body
    assert "Contact" in body
    assert "Follow up" in body
    assert "Manage access" in body


def test_flow_explains_or_activates_visible_controls():
    body = make_app().test_client().get("/").get_data(as_text=True)
    assert "explainButtons" in body
    assert "aria-disabled" in body
    assert "This tool is unavailable" in body


def test_navigation_uses_progressive_disclosure():
    body = make_app().test_client().get("/").get_data(as_text=True)
    assert "More tools" in body
    assert "bb-nav-more" in body
    assert "primaryTerms" in body


def test_public_auth_pages_are_not_modified():
    response = make_app().test_client().get("/login")
    assert "brokerbeacon-simple-flow" not in response.get_data(as_text=True)


def test_unauthenticated_pages_are_not_modified():
    response = make_app(authenticated=False).test_client().get("/")
    assert "brokerbeacon-simple-flow" not in response.get_data(as_text=True)
