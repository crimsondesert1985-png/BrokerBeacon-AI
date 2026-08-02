from __future__ import annotations

import unittest

from flask import Flask

from sprint41_ux import install_sprint41_ux


class Sprint41UxTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        @self.app.get('/platform/control-tower')
        def control_tower():
            return '<html><head></head><body><main><p>Existing tower</p></main></body></html>'

        @self.app.get('/other')
        def other():
            return '<html><head></head><body><main>Other page</main></body></html>'

        install_sprint41_ux(self.app)
        self.client = self.app.test_client()

    def test_command_center_is_injected_on_control_tower(self):
        response = self.client.get('/platform/control-tower')
        body = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn('s41-command-center', body)
        self.assertIn('Ember Command Center', body)
        self.assertIn('Queue Next Hunt', body)
        self.assertIn('/api/platform/ember-queue/discovery', body)
        self.assertIn('setInterval(loadS41,15000)', body)
        self.assertIn('Existing tower', body)

    def test_other_pages_are_unchanged(self):
        response = self.client.get('/other')
        body = response.get_data(as_text=True)
        self.assertNotIn('s41-command-center', body)
        self.assertIn('Other page', body)


if __name__ == '__main__':
    unittest.main()
