"""Workspace-isolated SQLite storage for BrokerBeacon operational data."""
from pathlib import Path
import sqlite3
import threading


_CREATE_LOCK = threading.Lock()
_SHARED_OR_TEMPLATE_PREFIXES = ("guideline_", "broker_index")
_SHARED_OR_TEMPLATE_TABLES = {
    "schema_migrations",
    "scoring_settings",
    "product_catalog",
    "revenue_settings",
    "message_templates",
    "sequences",
    "sequence_steps",
    "national_broker_index",
}


def _workspace_path(central_path, workspace_id):
    central = Path(central_path)
    return central.with_name(f"{central.stem}.workspace-{int(workspace_id)}{central.suffix}")


def _is_founding_workspace(central_path, workspace_id):
    with sqlite3.connect(central_path) as conn:
        row = conn.execute(
            "select is_founding from saas_workspaces where id=?", (int(workspace_id),)
        ).fetchone()
    return bool(row and row[0])


def _clear_private_data(conn):
    tables = [
        row[0]
        for row in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        )
    ]
    conn.execute("pragma foreign_keys=off")
    for table in tables:
        if table in _SHARED_OR_TEMPLATE_TABLES or table.startswith(_SHARED_OR_TEMPLATE_PREFIXES):
            continue
        # Names originate from sqlite_master, not request data.
        conn.execute(f'delete from "{table.replace(chr(34), chr(34) * 2)}"')
    conn.execute("pragma foreign_keys=on")


def ensure_workspace_database(central_path, workspace_id):
    """Return the private database path, creating a schema-only workspace copy once."""
    workspace_id = int(workspace_id)
    central = Path(central_path)
    if _is_founding_workspace(central, workspace_id):
        # The pre-SaaS database becomes the founding workspace, preserving Clay's records.
        return central

    target = _workspace_path(central, workspace_id)
    if target.exists():
        return target

    with _CREATE_LOCK:
        if target.exists():
            return target
        temporary = target.with_suffix(target.suffix + ".creating")
        if temporary.exists():
            temporary.unlink()
        with sqlite3.connect(central) as source, sqlite3.connect(temporary) as destination:
            source.backup(destination)
            _clear_private_data(destination)
        temporary.replace(target)
    return target
