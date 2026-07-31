import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from postgres_migration import (
    build_migration_plan,
    discover_databases,
    migration_status,
    postgres_type,
    quote_identifier,
    rows_checksum,
)


class Sprint33PostgresReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.central = self.root / "brokerbeacon.db"
        self.workspace = self.root / "brokerbeacon.workspace-7.db"
        for path, company in ((self.central, "BrokerBeacon"), (self.workspace, "Pilot Mortgage")):
            with sqlite3.connect(path) as conn:
                conn.execute("create table prospects(id integer primary key,company text,score real)")
                conn.execute("insert into prospects(company,score) values(?,?)", (company, 91.5))
                conn.execute("create table audit_log(id integer,event text,payload blob)")
                conn.execute("insert into audit_log values(?,?,?)", (1, "created", b"safe"))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_plan_preserves_workspace_boundaries_and_validates_every_row(self):
        plan = build_migration_plan(self.central, run_id="test33")
        self.assertEqual(plan["mode"], "shadow")
        self.assertEqual(plan["source_databases"], 2)
        self.assertEqual(plan["tables"], 4)
        self.assertEqual(plan["rows"], 4)
        schemas = {item["schema"] for item in plan["databases"]}
        self.assertEqual(schemas, {"bb_shadow_test33_core", "bb_shadow_test33_workspace_7"})
        self.assertTrue(all(table["checksum"] for db in plan["databases"] for table in db["tables"]))

    def test_source_discovery_is_deterministic_and_read_only(self):
        before = self.central.read_bytes()
        found = discover_databases(self.central)
        self.assertEqual(found, [(self.central.resolve(), None), (self.workspace.resolve(), 7)])
        build_migration_plan(self.central, run_id="readonly")
        self.assertEqual(self.central.read_bytes(), before)

    def test_postgres_translation_and_checksums_are_stable(self):
        self.assertEqual(postgres_type("INTEGER"), "BIGINT")
        self.assertEqual(postgres_type("varchar(255)"), "TEXT")
        self.assertEqual(postgres_type("BLOB"), "BYTEA")
        self.assertEqual(quote_identifier('odd"name'), '"odd""name"')
        self.assertEqual(rows_checksum([(2, "b"), (1, "a")]), rows_checksum([(1, "a"), (2, "b")]))

    def test_cutover_is_off_by_default_and_requires_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            status = migration_status(self.central)
        self.assertFalse(status["configured"])
        self.assertFalse(status["cutover_enabled"])
        self.assertFalse(status["ready_for_shadow_copy"])


if __name__ == "__main__":
    unittest.main()
