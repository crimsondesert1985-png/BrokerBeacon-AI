from flask import Flask, g

from customer_ready_ux import COPY_RULES, HUMAN_MESSAGES, install_customer_ready_ux


def build_app(owner=False):
    app = Flask(__name__)
    app.secret_key = "test"

    @app.before_request
    def set_context():
        g.is_platform_owner = owner

    @app.get("/")
    def home():
        return """<!doctype html><html><body><main>
        <h1>Agent status</h1>
        <form><textarea placeholder='Enter command payload'></textarea><button>Execute</button></form>
        <pre>{\"technical\": \"details that should be hidden from customers\"}</pre>
        </main></body></html>"""

    install_customer_ready_ux(app)
    return app


def test_copy_rules_are_plain_english():
    assert COPY_RULES["Execute"] == "Continue"
    assert COPY_RULES["Payload"] == "Details"
    assert "working" in HUMAN_MESSAGES["loading"].lower()


def test_customer_page_gets_human_experience_layer():
    client = build_app(owner=False).test_client()
    response = client.get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "brokerbeacon-customer-ready" in body
    assert "Tell BrokerBeacon what you need in your own words" in body
    assert "bb-human-status" in body


def test_owner_context_is_preserved():
    client = build_app(owner=True).test_client()
    body = client.get("/").get_data(as_text=True)
    assert "brokerbeacon-customer-ready" in body
    assert "const rules=" in body


def test_experience_endpoint_explains_product_rules():
    client = build_app().test_client()
    payload = client.get("/api/customer-ready/experience").get_json()
    assert "Use plain English" in payload["principles"]
    assert "Show one obvious next step" in payload["principles"]
    assert payload["messages"]["success"]
