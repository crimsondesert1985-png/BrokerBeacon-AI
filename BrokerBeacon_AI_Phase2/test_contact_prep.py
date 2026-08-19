import unittest
from pathlib import Path


ROOT = Path(__file__).parent
CONTACT_PREP = (ROOT / "contact_prep.py").read_text(encoding="utf-8")
WSGI = (ROOT / "wsgi.py").read_text(encoding="utf-8")


class ContactPrepTests(unittest.TestCase):
    def test_dedicated_contact_prep_route_exists(self):
        self.assertIn('@app.get("/prospects/<int:prospect_id>/contact-prep")', CONTACT_PREP)

    def test_contact_prep_shows_clickable_contact_methods(self):
        self.assertIn('href="tel:', CONTACT_PREP)
        self.assertIn('href="mailto:', CONTACT_PREP)
        self.assertIn('Loan Officers & Contacts', CONTACT_PREP)

    def test_contact_prep_keeps_core_tools_accessible(self):
        for label in ("Intelligence", "Notes", "Marketing", "Sales Coach", "Opportunities", "BeaconMatch"):
            self.assertIn(label, CONTACT_PREP)

    def test_intelligence_page_gets_prominent_contact_prep_button(self):
        self.assertIn("brokerbeacon-contact-prep-button", CONTACT_PREP)
        self.assertIn("bb-contact-prep-primary", CONTACT_PREP)
        self.assertIn("/contact-prep", CONTACT_PREP)

    def test_wsgi_registers_contact_prep(self):
        self.assertIn("from contact_prep import install_contact_prep", WSGI)
        self.assertIn("install_contact_prep(app, DB)", WSGI)


if __name__ == "__main__":
    unittest.main()
