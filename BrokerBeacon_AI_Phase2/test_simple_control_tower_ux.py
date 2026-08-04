import unittest

from flask import Flask

from sprint39_ux import install_sprint39_ux


class SimpleControlTowerUxTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        @self.app.get("/platform/control-tower")
        def control_tower():
            return """<html><head><style></style></head><body>
            <div id="error" class="error"></div>
            <button data-tab="operations">Discovery</button>
            <section id="operations" class="tab"></section>
            </body></html>"""

        install_sprint39_ux(self.app)

    def test_activity_is_short_and_human_readable(self):
        body = self.app.test_client().get("/platform/control-tower").get_data(as_text=True)
        self.assertIn("function s39event", body)
        self.assertIn("slice(0,12)", body)
        self.assertIn("Ember will retry automatically", body)
        self.assertIn("Public website ready for review", body)
        self.assertNotIn("JSON.stringify(h.queue", body)

    def test_raw_provider_errors_are_replaced_with_one_short_message(self):
        body = self.app.test_client().get("/platform/control-tower").get_data(as_text=True)
        self.assertIn("Some search sources are temporarily unavailable", body)
        self.assertIn("setTimeout(()=>x.style.display='none',8000)", body)
        self.assertIn("max-height:90px", body)


if __name__ == "__main__":
    unittest.main()
