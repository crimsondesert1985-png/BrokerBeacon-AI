import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from postgres_migration import _validated_shadow_report, rehearsal_status


class Sprint34CutoverRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.report = self.root / "rehearsal.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_missing_or_malformed_report_never_opens_cutover_gate(self):
        self.assertEqual(rehearsal_status(self.report), {
            "completed": False, "valid": False, "cutover_ready": False
        })
        self.report.write_text("not-json", encoding="utf-8")
        self.assertFalse(rehearsal_status(self.report)["cutover_ready"])

    def test_valid_rehearsal_report_exposes_only_safe_summary(self):
        self.report.write_text(json.dumps({
            "valid": True, "restore_valid": True, "parity_valid": True,
            "cutover_ready": True, "created_at": "2026-07-31T19:00:00+00:00",
            "tables": 20, "rows": 4718, "checks": [{"secret": "not exposed"}],
        }), encoding="utf-8")
        status = rehearsal_status(self.report)
        self.assertTrue(status["completed"])
        self.assertTrue(status["restore_valid"])
        self.assertTrue(status["parity_valid"])
        self.assertEqual(status["rows"], 4718)
        self.assertNotIn("checks", status)

    def test_shadow_validation_must_be_successful(self):
        validation = self.root / "shadow.json"
        validation.write_text(json.dumps({"valid": False, "databases": []}), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "successful Sprint 33"):
            _validated_shadow_report(validation)

    def test_cutover_environment_never_changes_report_evidence(self):
        self.report.write_text(json.dumps({"valid": True, "restore_valid": True,
            "parity_valid": True, "cutover_ready": True}), encoding="utf-8")
        with patch.dict(os.environ, {"POSTGRES_CUTOVER_ENABLED": "true"}):
            status = rehearsal_status(self.report)
        self.assertTrue(status["cutover_ready"])


if __name__ == "__main__":
    unittest.main()
