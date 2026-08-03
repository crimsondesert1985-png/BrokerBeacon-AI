import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from scenario_rescue_engine import build_analysis, extract_facts, install_scenario_rescue


class ScenarioRescueLogicTests(unittest.TestCase):
    def test_extracts_core_facts(self):
        facts = extract_facts("612 FICO, self-employed for 3 years, $325,000 purchase, 5% down, primary residence in NC")
        self.assertEqual(facts["fico"], 612)
        self.assertEqual(facts["purchase_price"], 325000)
        self.assertEqual(facts["down_payment_percent"], 5)
        self.assertEqual(facts["state"], "NC")
        self.assertEqual(facts["income_type"], "self_employed")
        self.assertEqual(facts["occupancy"], "primary")
        self.assertEqual(facts["employment_years"], 3)

    def test_analysis_is_not_approval(self):
        analysis = build_analysis("612 FICO, self-employed, recent mortgage late, $325,000 purchase, 5% down, primary residence in NC")
        self.assertTrue(analysis["paths"])
        self.assertIn("Potential paths only", analysis["disclaimer"])
        self.assertNotIn("approved", analysis["responses"]["email"].lower())
        self.assertTrue(analysis["missing"])

    def test_recent_late_reduces_confidence(self):
        clean = build_analysis("700 FICO, $325,000 purchase, 5% down, primary residence in NC, W2 salary")
        late = build_analysis("700 FICO, recent mortgage late, $325,000 purchase, 5% down, primary residence in NC, W2 salary")
        self.assertLess(late["paths"][0]["confidence"], clean["paths"][0]["confidence"])

    def test_punctuation_is_not_parsed_as_money(self):
        facts = extract_facts("Purchase, primary residence in NC with 700 FICO")
        self.assertNotIn("purchase_price", facts)


class ScenarioRescueApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.app = Flask(__name__)
        self.app.secret_key = "test"

        @self.app.before_request
        def context():
            g.workspace_id = 7
            g.user_id = 11

        install_scenario_rescue(self.app, self.db)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyze_requires_detail(self):
        response = self.client.post("/api/scenario-rescue/analyze", json={"scenario": "too short"})
        self.assertEqual(response.status_code, 400)

    def test_save_list_and_outcome(self):
        scenario = "612 FICO, self-employed for 3 years, $325,000 purchase, 5% down, primary residence in NC"
        saved = self.client.post("/api/scenario-rescue/cases", json={"title": "Hard file", "scenario": scenario})
        self.assertEqual(saved.status_code, 201)
        case_id = saved.get_json()["id"]
        listed = self.client.get("/api/scenario-rescue/cases").get_json()["items"]
        self.assertEqual(len(listed), 1)
        changed = self.client.post(f"/api/scenario-rescue/cases/{case_id}/outcome", json={"outcome": "funded"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.get_json()["outcome"], "funded")

    def test_invalid_outcome_rejected(self):
        response = self.client.post("/api/scenario-rescue/cases/1/outcome", json={"outcome": "guaranteed"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
