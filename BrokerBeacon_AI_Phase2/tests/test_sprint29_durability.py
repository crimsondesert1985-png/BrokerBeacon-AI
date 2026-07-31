import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from data_durability import create_backup, prepare_database, storage_status, verify_database


class Sprint29DataDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.seed = self.root / "seed" / "brokerbeacon.db"
        self.seed.parent.mkdir()
        with sqlite3.connect(self.seed) as conn:
            conn.execute("create table records(id integer primary key, value text)")
            conn.execute("insert into records(value) values('founding-data')")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_empty_durable_directory_is_seeded_atomically(self):
        durable = self.root / "durable"
        with patch.dict(os.environ, {"BROKERBEACON_DATA_DIR": str(durable),
                                     "BROKERBEACON_DB_PATH": ""}, clear=False):
            target = prepare_database(self.seed)
        self.assertEqual(target, durable / "brokerbeacon.db")
        self.assertTrue(verify_database(target))
        with sqlite3.connect(target) as conn:
            self.assertEqual(conn.execute("select value from records").fetchone()[0], "founding-data")

    def test_existing_durable_database_survives_restart(self):
        durable = self.root / "durable"
        with patch.dict(os.environ, {"BROKERBEACON_DATA_DIR": str(durable),
                                     "BROKERBEACON_DB_PATH": ""}, clear=False):
            target = prepare_database(self.seed)
            with sqlite3.connect(target) as conn:
                conn.execute("insert into records(value) values('account-created-after-deploy')")
            restarted = prepare_database(self.seed)
        with sqlite3.connect(restarted) as conn:
            values = [row[0] for row in conn.execute("select value from records order by id")]
        self.assertEqual(values, ["founding-data", "account-created-after-deploy"])

    def test_backups_are_valid_and_retention_is_enforced(self):
        for index in range(5):
            create_backup(self.seed, reason=f"test-{index}", retention=3)
            time.sleep(1.01)
        backups = list((self.seed.parent / "backups").glob("*.db"))
        self.assertLessEqual(len(backups), 3)
        self.assertTrue(all(verify_database(item) for item in backups))

    def test_storage_status_reports_durable_health(self):
        durable = self.root / "durable"
        with patch.dict(os.environ, {"BROKERBEACON_DATA_DIR": str(durable),
                                     "BROKERBEACON_DB_PATH": ""}, clear=False):
            target = prepare_database(self.seed)
            status = storage_status(target)
        self.assertTrue(status["persistent"])
        self.assertEqual(status["integrity"], "ok")
        self.assertGreater(status["database_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
