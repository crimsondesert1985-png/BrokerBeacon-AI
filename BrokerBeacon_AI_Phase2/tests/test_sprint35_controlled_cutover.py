import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from postgres_migration import (
    create_sqlite_rollback_bundle,
    cutover_status,
    prepare_cutover,
)


class Sprint35ControlledCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.central = self.root / "brokerbeacon.db"
        self.workspace = self.root / "brokerbeacon.workspace-9.db"
        for path, company in ((self.central, "Founding"), (self.workspace, "Pilot")):
            with sqlite3.connect(path) as conn:
                conn.execute("create table prospects(id integer primary key, company text)")
                conn.execute("insert into prospects(company) values(?)", (company,))
        self.rehearsal = self.root / "rehearsal.json"
        self.preparation = self.root / "preparation.json"
        self.backups = self.root / "backups"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_rollback_bundle_copies_every_database_and_validates_it(self):
        result = create_sqlite_rollback_bundle(
            self.central, self.backups, run_id="sprint35"
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["source_databases"], 2)
        self.assertEqual(result["rows"], 2)
        manifest = Path(result["bundle_dir"]) / "manifest.json"
        self.assertTrue(manifest.exists())
        self.assertTrue(all(Path(item["backup"]).exists() for item in result["checks"]))

    def test_prepare_requires_a_successful_rehearsal(self):
        with self.assertRaisesRegex(RuntimeError, "valid Sprint 34"):
            prepare_cutover(
                self.central, self.rehearsal, self.backups, self.preparation
            )

    def test_preparation_builds_rollback_evidence_but_never_switches_traffic(self):
        self.rehearsal.write_text(json.dumps({
            "valid": True, "restore_valid": True, "parity_valid": True,
            "cutover_ready": True, "tables": 2, "rows": 2,
        }), encoding="utf-8")
        report = prepare_cutover(
            self.central, self.rehearsal, self.backups,
            self.preparation, run_id="ready35"
        )
        self.assertTrue(report["cutover_ready"])
        self.assertTrue(report["rollback_ready"])
        self.assertTrue(report["approval_required"])
        self.assertFalse(report["approval_granted"])
        self.assertFalse(report["production_traffic_enabled"])
        self.assertEqual(report["traffic_source"], "sqlite")

    def test_status_is_fail_closed_even_if_environment_flag_is_set(self):
        self.preparation.write_text(json.dumps({
            "cutover_ready": True, "rollback_ready": True,
            "rehearsal_valid": True, "restore_valid": True,
            "parity_valid": True, "source_databases": 2,
        }), encoding="utf-8")
        with patch.dict(os.environ, {"POSTGRES_CUTOVER_ENABLED": "true"}):
            status = cutover_status(self.preparation)
        self.assertTrue(status["environment_switch_requested"])
        self.assertFalse(status["approval_granted"])
        self.assertFalse(status["production_traffic_enabled"])
        self.assertEqual(status["traffic_source"], "sqlite")


if __name__ == "__main__":
    unittest.main()
