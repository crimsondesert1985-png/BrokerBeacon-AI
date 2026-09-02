import os
from pathlib import Path
import sqlite3
import shutil
import tempfile
import unittest
from unittest.mock import patch

from data_durability import prepare_database


class StartupBackupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tempdir.name)
        self.seed = self.root / "seed.db"
        self.durable = self.root / "durable"
        with sqlite3.connect(self.seed) as conn:
            conn.execute("create table records(id integer primary key, value text)")
            conn.execute("insert into records(value) values('preserved')")
        self.durable.mkdir()
        shutil.copy2(self.seed, self.durable / self.seed.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_disk_full_backup_does_not_prevent_restart(self):
        environment = {
            "BROKERBEACON_DATA_DIR": str(self.durable),
            "BROKERBEACON_DB_PATH": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            target = self.durable / self.seed.name
            with patch(
                "data_durability.create_backup",
                side_effect=sqlite3.OperationalError("database or disk is full"),
            ):
                restarted = prepare_database(self.seed)

        self.assertEqual(restarted, target)
        with sqlite3.connect(restarted) as conn:
            self.assertEqual(conn.execute("select value from records").fetchone()[0], "preserved")

    def test_unrelated_backup_errors_remain_fatal(self):
        environment = {
            "BROKERBEACON_DATA_DIR": str(self.durable),
            "BROKERBEACON_DB_PATH": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            with patch(
                "data_durability.create_backup",
                side_effect=sqlite3.OperationalError("database is locked"),
            ):
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    prepare_database(self.seed)


if __name__ == "__main__":
    unittest.main()

