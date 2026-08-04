import unittest

from flask import Flask

from help_layer import HELP_LAYER, install_help_layer


class HelpLayerTests(unittest.TestCase):
    def make_app(self):
        app = Flask(__name__)

        @app.get("/")
        def index():
            return "<html><body><button>Search prospects</button></body></html>"

        @app.get("/login")
        def login():
            return "<html><body>Login</body></html>"

        install_help_layer(app)
        return app

    def test_injects_sitewide_help(self):
        client = self.make_app().test_client()
        body = client.get("/").get_data(as_text=True)
        self.assertIn("brokerbeacon-help-layer", body)
        self.assertIn("bb-help-tooltip", body)
        self.assertIn("Tips: On", body)
        self.assertIn("bbTipsOn", body)

    def test_skips_public_login(self):
        client = self.make_app().test_client()
        body = client.get("/login").get_data(as_text=True)
        self.assertNotIn("brokerbeacon-help-layer", body)

    def test_contains_accessible_and_toggle_controls(self):
        self.assertIn('role="tooltip"', HELP_LAYER)
        self.assertIn('aria-live="polite"', HELP_LAYER)
        self.assertIn("Turn tips off", HELP_LAYER)
        self.assertIn("focusin", HELP_LAYER)

    def test_defers_to_the_main_site_tooltip_and_avoids_container_noise(self):
        self.assertIn("siteOwnsTooltips", HELP_LAYER)
        self.assertIn("typeof window.showSiteTooltip==='function'", HELP_LAYER)
        self.assertIn("closest('button,a,input,select,textarea')", HELP_LAYER)
        self.assertNotIn(".card,.panel,.metric,th,td", HELP_LAYER)


if __name__ == "__main__":
    unittest.main()
