import unittest
from pathlib import Path


APP = Path(__file__).with_name("app.py").read_text(encoding="utf-8")


class ContactScreenUxTests(unittest.TestCase):
    def test_contact_details_are_separated_and_wrap_safely(self):
        self.assertIn('class="contact-details"', APP)
        self.assertIn('class="contact-label">Phone', APP)
        self.assertIn('class="contact-label">Email', APP)
        self.assertIn("overflow-wrap:anywhere", APP)

    def test_contact_actions_use_plain_labels(self):
        start = APP.index("function contactButtons")
        end = APP.index("function showGuide", start)
        contact_buttons = APP[start:end]
        self.assertNotIn("☎", contact_buttons)
        self.assertNotIn("✉", contact_buttons)
        self.assertNotIn("↗", contact_buttons)
        self.assertIn(">Website</a>", contact_buttons)

    def test_prospect_table_reduces_columns_on_smaller_screens(self):
        self.assertIn('class="panel prospect-table-wrap"', APP)
        self.assertIn('class="prospect-table"', APP)
        self.assertIn("@media(max-width:1400px)", APP)
        self.assertIn(".prospect-table th:nth-child(7)", APP)
        self.assertIn(">Open</button>", APP)


if __name__ == "__main__":
    unittest.main()
