"""Persistent SQLite placement, integrity checks, and rolling backups."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3


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


def create_backup(database_path, reason="manual", retention=BACKUP_RETENTION):
    """Create a transactionally consistent SQLite backup and prune old snapshots."""
    source = Path(database_path)
    if not source.exists():
        raise FileNotFoundError(source)
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason)[:32]
    destination = backup_dir / f"{source.stem}-{stamp}-{safe_reason}.db"
    with sqlite3.connect(source) as current, sqlite3.connect(destination) as backup:
        current.backup(backup)
    verify_database(destination)
    snapshots = sorted(backup_dir.glob(f"{source.stem}-*.db"), key=lambda item: item.stat().st_mtime)
    for stale in snapshots[:-max(1, int(retention))]:
        stale.unlink()
    return destination


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
            create_backup(database, reason="pre-deploy")
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
