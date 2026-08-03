import tempfile
import unittest
from pathlib import Path

from flask import Flask, g

from beaconmatch_foundation import DISCLAIMER, _score_program, install_beaconmatch_foundation


class BeaconMatchFoundationLogicTests(unittest.TestCase):
    def test_program_score_explains_fit(self):
        program = {
            "id": 1,
            "name": "FHA Core",
            "code": "FHA",
            "min_fico": 580,
            "max_fico": None,
            "min_down_payment_percent": 3.5,
            "states": ["NC", "SC"],
            "transactions": ["purchase"],
            "occupancies": ["primary"],
            "income_types": ["w2", "self_employed"],
            "guideline_state": "verified",
        }
        result = _score_program(program, {
            "fico": 620,
            "state": "NC",
            "transaction": "purchase",
            "occupancy": "primary",
            "income_type": "w2",
            "down_payment_percent": 5,
        })
        self.assertEqual(result["status"], "potential_fit")
        self.assertGreater(result["score"], 80)
        self.assertFalse(result["blockers"])
        self.assertTrue(result["reasons"])

    def test_program_score_blocks_out_of_state(self):
        program = {
            "id": 1,
            "name": "NC Only",
            "code": "NC",
            "min_fico": 580,
            "max_fico": None,
            "min_down_payment_percent": 3.5,
            "states": ["NC"],
            "transactions": ["purchase"],
            "occupancies": ["primary"],
            "income_types": ["w2"],
            "guideline_state": "verified",
        }
        result = _score_program(program, {"fico": 700, "state": "SC", "transaction": "purchase"})
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("SC" in item for item in result["blockers"]))


class BeaconMatchFoundationApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.workspace = 7
        self.app = Flask(__name__)
        self.app.secret_key = "test"

        @self.app.before_request
        def context():
            g.workspace_id = self.workspace
            g.user_id = 11

        install_beaconmatch_foundation(self.app, self.db)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_lender_before_program(self):
        response = self.client.post("/api/beaconmatch/programs", json={"name": "FHA"})
        self.assertEqual(response.status_code, 409)

    def test_lender_program_source_match_and_audit(self):
        lender = self.client.put("/api/beaconmatch/lender", json={"name": "Union Home Mortgage", "nmls_id": "2229"})
        self.assertEqual(lender.status_code, 200)

        source = self.client.post("/api/beaconmatch/guideline-sources", json={
            "title": "FHA Product Matrix",
            "verification_state": "verified",
            "effective_date": "2026-08-01",
        })
        self.assertEqual(source.status_code, 201)
        source_id = source.get_json()["id"]

        program = self.client.post("/api/beaconmatch/programs", json={
            "name": "FHA Core",
            "code": "FHA",
            "min_fico": 580,
            "min_down_payment_percent": 3.5,
            "states": ["NC", "SC"],
            "transactions": ["purchase", "refinance"],
            "occupancies": ["primary"],
            "income_types": ["w2", "self_employed"],
            "guideline_source_id": source_id,
        })
        self.assertEqual(program.status_code, 201)

        match = self.client.post("/api/beaconmatch/match", json={
            "scenario": "620 FICO, $325,000 purchase, 5% down, primary residence in NC, W2 salary"
        })
        self.assertEqual(match.status_code, 200)
        payload = match.get_json()
        self.assertEqual(payload["results"][0]["program_name"], "FHA Core")
        self.assertIn("Potential lender-fit guidance only", payload["disclaimer"])
        self.assertNotIn("approved", payload["disclaimer"].lower().split("only")[0])

        runs = self.client.get("/api/beaconmatch/match-runs").get_json()["items"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["results"][0]["program_name"], "FHA Core")

    def test_workspace_isolation(self):
        self.client.put("/api/beaconmatch/lender", json={"name": "Lender Seven"})
        self.workspace = 8
        status = self.client.get("/api/beaconmatch/foundation").get_json()
        self.assertIsNone(status["lender"])
        self.assertEqual(status["counts"]["programs"], 0)

    def test_sanitized_memory(self):
        self.client.put("/api/beaconmatch/lender", json={"name": "Lender Seven"})
        response = self.client.post("/api/beaconmatch/memories", json={
            "title": "Self-employed FHA save",
            "sanitized_summary": "Borrower profile was anonymized; file funded after income documentation review.",
            "outcome": "funded",
            "lesson": "Verify declining-income trend before submission.",
            "facts": {"fico_band": "620-639", "state": "NC"},
        })
        self.assertEqual(response.status_code, 201)
        items = self.client.get("/api/beaconmatch/memories").get_json()["items"]
        self.assertEqual(items[0]["outcome"], "funded")
        self.assertEqual(items[0]["facts"]["state"], "NC")

    def test_invalid_verification_and_memory_outcome_rejected(self):
        source = self.client.post("/api/beaconmatch/guideline-sources", json={
            "title": "Bad state", "verification_state": "guaranteed"
        })
        self.assertEqual(source.status_code, 400)
        memory = self.client.post("/api/beaconmatch/memories", json={
            "title": "Bad", "sanitized_summary": "Enough detail for a record", "outcome": "guaranteed"
        })
        self.assertEqual(memory.status_code, 400)


if __name__ == "__main__":
    unittest.main()
