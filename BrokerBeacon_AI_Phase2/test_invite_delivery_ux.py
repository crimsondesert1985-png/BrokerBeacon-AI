import unittest
from pathlib import Path


ROOT = Path(__file__).parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SAAS = (ROOT / "saas.py").read_text(encoding="utf-8")
TEAM = (ROOT / "role_management.py").read_text(encoding="utf-8")


class InviteDeliveryUxTests(unittest.TestCase):
    def test_authorized_inviter_receives_a_non_cached_acceptance_link(self):
        self.assertIn('"accept_url": accept_url', SAAS)
        self.assertIn('result.headers["Cache-Control"] = "no-store"', SAAS)
        self.assertIn('"Invitation sent by email."', SAAS)

    def test_account_dialog_never_renders_an_undefined_link(self):
        self.assertIn("function showInviteResult(d)", APP)
        self.assertIn("if(!d.email_delivered&&d.accept_url)", APP)
        self.assertIn("Copy secure link", APP)
        self.assertNotIn("Invitation ready. <a", APP)

    def test_team_page_shows_a_fallback_when_email_is_unavailable(self):
        self.assertIn('id="invite-result"', TEAM)
        self.assertIn("function showInviteOutcome(d)", TEAM)
        self.assertIn("Share this seven-day link directly", TEAM)
        self.assertIn("Secure invitation link copied.", TEAM)


if __name__ == "__main__":
    unittest.main()
