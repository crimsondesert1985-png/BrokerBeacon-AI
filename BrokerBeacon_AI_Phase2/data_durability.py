"""Persistent SQLite placement, integrity checks, and rolling backups."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


DEFAULT_DATA_DIR = Path("/var/data")
BACKUP_RETENTION = 7


def _data_directory():
    configured = os.getenv("BROKERBEACON_DATA_DIR", "").strip()
    if configured:
        return Path(configured)
    if DEFAULT_DATA_DIR.is_dir():
        return DEFAULT_DATA_DIR
    return None


def verify_database(database_path):
    """Raise when SQLite cannot prove that the database is structurally sound."""
    with sqlite3.connect(database_path) as conn:
        result = conn.execute("pragma quick_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")
    return True


def _prune_backups(backup_dir, source_stem, keep):
    """Prune oldest snapshots first so there is room to create the next backup."""
    snapshots = sorted(
        backup_dir.glob(f"{source_stem}-*.db"),
        key=lambda item: item.stat().st_mtime,
    )
    keep = max(0, int(keep))
    stale = snapshots[:-keep] if keep else snapshots
    for item in stale:
        item.unlink(missing_ok=True)


def create_backup(database_path, reason="manual", retention=BACKUP_RETENTION):
    """Create a transactionally consistent SQLite backup and prune old snapshots."""
    source = Path(database_path)
    if not source.exists():
        raise FileNotFoundError(source)
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Prune before writing the next snapshot. Waiting until after the backup can
    # deadlock deployment when the persistent disk is already at capacity.
    retention = max(1, int(retention))
    _prune_backups(backup_dir, source.stem, retention - 1)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason)[:32]
    destination = backup_dir / f"{source.stem}-{stamp}-{safe_reason}.db"
    try:
        with sqlite3.connect(source) as current, sqlite3.connect(destination) as backup:
            current.backup(backup)
        verify_database(destination)
    except sqlite3.OperationalError as exc:
        destination.unlink(missing_ok=True)
        if "database or disk is full" not in str(exc).lower():
            raise
        # Free one more retained snapshot and retry once. This preserves the
        # newest available backups while allowing the application to boot.
        _prune_backups(backup_dir, source.stem, max(0, retention - 2))
        with sqlite3.connect(source) as current, sqlite3.connect(destination) as backup:
            current.backup(backup)
        verify_database(destination)

    _prune_backups(backup_dir, source.stem, retention)
    return destination


def verify_backup_restore(backup_path):
    """Restore a backup into an isolated temporary database and verify its schema."""
    source = Path(backup_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="brokerbeacon-restore-check-") as directory:
        restored = Path(directory) / "restored.db"
        with sqlite3.connect(source) as backup, sqlite3.connect(restored) as target:
            backup.backup(target)
        verify_database(restored)
        with sqlite3.connect(restored) as conn:
            tables = conn.execute(
                "select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchone()[0]
            migrations = 0
            if conn.execute(
                "select 1 from sqlite_master where type='table' and name='schema_migrations'"
            ).fetchone():
                migrations = conn.execute("select count(*) from schema_migrations").fetchone()[0]
        if not tables:
            raise RuntimeError("Restored backup contains no application tables")
    return {"ok": True, "backup": source.name, "tables": tables, "migrations": migrations}


def verify_latest_backup(database_path):
    """Run a non-destructive restore drill against the newest retained backup."""
    path = Path(database_path)
    backups = sorted(
        (path.parent / "backups").glob(f"{path.stem}-*.db"),
        key=lambda item: item.stat().st_mtime,
    )
    if not backups:
        raise FileNotFoundError("No backup is available for a recovery check")
    return verify_backup_restore(backups[-1])


def prepare_database(seed_path):
    """Place the central database on durable storage, preserving an existing copy."""
    seed = Path(seed_path)
    explicit = os.getenv("BROKERBEACON_DB_PATH", "").strip()
    if explicit:
        target = Path(explicit)
    else:
        data_dir = _data_directory()
        if data_dir is None:
            verify_database(seed)
            return seed
        data_dir.mkdir(parents=True, exist_ok=True)
        target = data_dir / seed.name

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        if explicit:
            # Explicit paths are used by tests and operators who want a fresh database.
            with sqlite3.connect(target):
                pass
        else:
            temporary = target.with_suffix(target.suffix + ".seeding")
            shutil.copy2(seed, temporary)
            verify_database(temporary)
            temporary.replace(target)
    else:
        verify_database(target)
        databases = [target, *target.parent.glob(f"{target.stem}.workspace-*{target.suffix}")]
        for database in databases:
            backup = create_backup(database, reason="pre-deploy")
            verify_backup_restore(backup)
    return target


def storage_status(database_path):
    path = Path(database_path)
    backups = sorted((path.parent / "backups").glob(f"{path.stem}-*.db"))
    return {
        "database_path": str(path),
        "persistent": path.parent == DEFAULT_DATA_DIR or bool(os.getenv("BROKERBEACON_DATA_DIR")),
        "database_bytes": path.stat().st_size if path.exists() else 0,
        "integrity": "ok" if verify_database(path) else "error",
        "backup_count": len(backups),
        "latest_backup": backups[-1].name if backups else "",
        "retention": BACKUP_RETENTION,
    }
