from __future__ import annotations

import unittest
from flask import Flask

from sprint41_drilldown_ux import install_sprint41_drilldown_ux


class Sprint41DrilldownUXTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = "test"

        @app.get("/platform/control-tower")
        def tower():
            return "<html><head></head><body><main>tower</main></body></html>"

        @app.get("/other")
        def other():
            return "<html><head></head><body>other</body></html>"

        install_sprint41_drilldown_ux(app)
        self.client = app.test_client()

    def test_injects_search_and_drawer_on_control_tower(self):
        body = self.client.get("/platform/control-tower").get_data(as_text=True)
        self.assertIn("s41GlobalSearch", body)
        self.assertIn("s41DrawerBackdrop", body)
        self.assertIn("openContact", body)
        self.assertIn("openCompany", body)
        self.assertIn("/api/platform/sprint38/contacts", body)

    def test_does_not_modify_other_pages(self):
        body = self.client.get("/other").get_data(as_text=True)
        self.assertNotIn("s41GlobalSearch", body)
        self.assertNotIn("s41DrawerBackdrop", body)


if __name__ == "__main__":
    unittest.main()
