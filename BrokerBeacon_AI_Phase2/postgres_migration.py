"""Safe, validated SQLite-to-PostgreSQL shadow migration for BrokerBeacon.

The production application remains on SQLite until a shadow copy validates. Each SQLite
workspace becomes a separate PostgreSQL schema so tenant isolation is preserved during
the transition. This module never deletes or mutates a source database.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable


TYPE_MAP = {
    "INT": "BIGINT", "INTEGER": "BIGINT", "TINYINT": "SMALLINT",
    "SMALLINT": "SMALLINT", "BIGINT": "BIGINT", "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION", "DOUBLE": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC", "DECIMAL": "NUMERIC", "BOOLEAN": "BIGINT",
    "DATE": "TEXT", "DATETIME": "TEXT", "TIMESTAMP": "TEXT", "BLOB": "BYTEA",
}
WORKSPACE_PATTERN = re.compile(r"\.workspace-(\d+)\.db$")
SQLITE_FTS_SHADOW = re.compile(r"_fts_(?:config|content|data|docsize|idx)$")


@dataclass(frozen=True)
class TableSnapshot:
    name: str
    columns: tuple[tuple[str, str], ...]
    rows: int
    checksum: str


@dataclass(frozen=True)
class DatabaseSnapshot:
    source: str
    schema: str
    workspace_id: int | None
    tables: tuple[TableSnapshot, ...]

    @property
    def rows(self):
        return sum(table.rows for table in self.tables)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def postgres_type(sqlite_type: str) -> str:
    normalized = (sqlite_type or "TEXT").upper().split("(", 1)[0].strip()
    return TYPE_MAP.get(normalized, "TEXT")


def _normalized(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bytes):
        return "bytes:" + value.hex()
    if isinstance(value, memoryview):
        return "bytes:" + value.tobytes().hex()
    if isinstance(value, float):
        return format(value, ".17g")
    return str(value)


def rows_checksum(rows: Iterable[Iterable[Any]]) -> str:
    encoded = [json.dumps([_normalized(value) for value in row], separators=(",", ":"))
               for row in rows]
    digest = hashlib.sha256()
    for row in sorted(encoded):
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def discover_databases(central_path: Path) -> list[tuple[Path, int | None]]:
    central = Path(central_path).resolve()
    found = [(central, None)]
    pattern = central.with_name(f"{central.stem}.workspace-*{central.suffix}")
    for path in sorted(central.parent.glob(pattern.name)):
        match = WORKSPACE_PATTERN.search(path.name)
        if match:
            found.append((path.resolve(), int(match.group(1))))
    return found


def portable_table_names(conn: sqlite3.Connection) -> list[str]:
    """Return canonical tables, excluding SQLite virtual tables and their shadow indexes."""
    rows = conn.execute(
        "select name,coalesce(sql,'') from sqlite_master "
        "where type='table' and name not like 'sqlite_%' order by name"
    )
    return [name for name, sql in rows
            if "create virtual table" not in sql.lower() and not SQLITE_FTS_SHADOW.search(name)]


def snapshot_database(path: Path, schema: str, workspace_id: int | None = None,
                      include_rows: bool = True) -> DatabaseSnapshot:
    tables: list[TableSnapshot] = []
    uri = f"file:{Path(path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        names = portable_table_names(conn)
        for name in names:
            quoted = quote_identifier(name)
            columns = tuple((row[1], row[2] or "TEXT") for row in conn.execute(
                f"pragma table_info({quoted})"
            ))
            count = conn.execute(f"select count(*) from {quoted}").fetchone()[0] if include_rows else 0
            checksum = ""
            if include_rows:
                checksum = rows_checksum(conn.execute(f"select * from {quoted}"))
            tables.append(TableSnapshot(name, columns, count, checksum))
    return DatabaseSnapshot(str(Path(path).resolve()), schema, workspace_id, tuple(tables))


def build_migration_plan(central_path: Path, include_rows: bool = True,
                         run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    prefix = "bb_shadow_" + re.sub(r"[^a-zA-Z0-9_]", "", run_id).lower()
    snapshots = []
    for path, workspace_id in discover_databases(Path(central_path)):
        suffix = "core" if workspace_id is None else f"workspace_{workspace_id}"
        snapshots.append(snapshot_database(path, f"{prefix}_{suffix}", workspace_id, include_rows))
    return {
        "run_id": run_id,
        "mode": "shadow",
        "source_databases": len(snapshots),
        "tables": sum(len(item.tables) for item in snapshots),
        "rows": sum(item.rows for item in snapshots),
        "databases": [asdict(item) for item in snapshots],
    }


def migration_status(central_path: Path) -> dict[str, Any]:
    configured = bool(os.getenv("DATABASE_URL", "").strip())
    plan = build_migration_plan(central_path, include_rows=False)
    return {
        "configured": configured,
        "mode": os.getenv("POSTGRES_MIGRATION_MODE", "shadow"),
        "cutover_enabled": os.getenv("POSTGRES_CUTOVER_ENABLED", "").lower() == "true",
        "source_databases": plan["source_databases"],
        "tables": plan["tables"],
        "rows": plan["rows"],
        "ready_for_shadow_copy": configured and plan["source_databases"] > 0,
    }


def rehearsal_status(report_path: Path | None = None) -> dict[str, Any]:
    """Return a safe summary of the latest cutover rehearsal report."""
    path = Path(report_path or os.getenv(
        "POSTGRES_REHEARSAL_REPORT", "/var/data/postgres-cutover-rehearsal.json"
    ))
    if not path.exists():
        return {"completed": False, "valid": False, "cutover_ready": False}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"completed": False, "valid": False, "cutover_ready": False}
    return {
        "completed": True,
        "valid": bool(report.get("valid")),
        "restore_valid": bool(report.get("restore_valid")),
        "parity_valid": bool(report.get("parity_valid")),
        "cutover_ready": bool(report.get("cutover_ready")),
        "created_at": report.get("created_at", ""),
        "rows": int(report.get("rows") or 0),
        "tables": int(report.get("tables") or 0),
    }


def _load_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary] before running PostgreSQL migration") from exc
    return psycopg


def migrate_shadow(central_path: Path, database_url: str, run_id: str | None = None) -> dict[str, Any]:
    """Copy all sources into new run-specific schemas and validate every table."""
    if not database_url:
        raise ValueError("A PostgreSQL DATABASE_URL is required")
    plan = build_migration_plan(central_path, include_rows=True, run_id=run_id)
    psycopg = _load_psycopg()
    validation = []
    with psycopg.connect(database_url) as target:
        for database in plan["databases"]:
            schema = database["schema"]
            with target.cursor() as cursor:
                cursor.execute(f"create schema {quote_identifier(schema)}")
            source_uri = f"file:{database['source']}?mode=ro"
            with sqlite3.connect(source_uri, uri=True) as source:
                for table in database["tables"]:
                    column_sql = ",".join(
                        f"{quote_identifier(name)} {postgres_type(kind)}"
                        for name, kind in table["columns"]
                    )
                    qualified = f"{quote_identifier(schema)}.{quote_identifier(table['name'])}"
                    with target.cursor() as cursor:
                        cursor.execute(f"create table {qualified} ({column_sql})")
                    names = [column[0] for column in table["columns"]]
                    rows = list(source.execute(f"select * from {quote_identifier(table['name'])}"))
                    if rows:
                        placeholders = ",".join(["%s"] * len(names))
                        columns = ",".join(quote_identifier(name) for name in names)
                        with target.cursor() as cursor:
                            cursor.executemany(
                                f"insert into {qualified} ({columns}) values ({placeholders})", rows
                            )
                    with target.cursor() as cursor:
                        cursor.execute(f"select * from {qualified}")
                        copied = cursor.fetchall()
                    result = {
                        "schema": schema, "table": table["name"],
                        "source_rows": table["rows"], "target_rows": len(copied),
                        "source_checksum": table["checksum"],
                        "target_checksum": rows_checksum(copied),
                    }
                    result["valid"] = (result["source_rows"] == result["target_rows"] and
                                       result["source_checksum"] == result["target_checksum"])
                    validation.append(result)
                    if not result["valid"]:
                        raise RuntimeError(f"Validation failed for {schema}.{table['name']}")
        target.commit()
    plan["validation"] = validation
    plan["valid"] = all(item["valid"] for item in validation)
    return plan


def _validated_shadow_report(path: Path) -> dict[str, Any]:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if not report.get("valid") or not report.get("databases"):
        raise RuntimeError("A successful Sprint 33 shadow validation report is required")
    return report


def rehearse_cutover(central_path: Path, database_url: str, validation_path: Path,
                     run_id: str | None = None, keep_restore: bool = False) -> dict[str, Any]:
    """Restore the validated shadow copy into isolated schemas and compare live parity.

    The rehearsal runs in one PostgreSQL transaction. By default that transaction is rolled
    back after validation so no rehearsal schema is retained. SQLite remains authoritative.
    """
    if not database_url:
        raise ValueError("A PostgreSQL DATABASE_URL is required")
    shadow = _validated_shadow_report(validation_path)
    current = build_migration_plan(central_path, include_rows=True, run_id="parity")
    current_by_workspace = {item["workspace_id"]: item for item in current["databases"]}
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    restore_prefix = "bb_restore_" + re.sub(r"[^a-zA-Z0-9_]", "", run_id).lower()
    psycopg = _load_psycopg()
    checks: list[dict[str, Any]] = []
    with psycopg.connect(database_url) as target:
        try:
            for database in shadow["databases"]:
                workspace_id = database.get("workspace_id")
                live = current_by_workspace.get(workspace_id)
                if live is None:
                    raise RuntimeError(f"Workspace parity failed for {workspace_id}")
                live_tables = {table["name"]: table for table in live["tables"]}
                suffix = "core" if workspace_id is None else f"workspace_{workspace_id}"
                restore_schema = f"{restore_prefix}_{suffix}"
                source_schema = database["schema"]
                with target.cursor() as cursor:
                    cursor.execute(f"create schema {quote_identifier(restore_schema)}")
                for table in database["tables"]:
                    name = table["name"]
                    live_table = live_tables.get(name)
                    if live_table is None:
                        raise RuntimeError(f"Live parity table missing: {suffix}.{name}")
                    source = f"{quote_identifier(source_schema)}.{quote_identifier(name)}"
                    restored = f"{quote_identifier(restore_schema)}.{quote_identifier(name)}"
                    with target.cursor() as cursor:
                        cursor.execute(f"create table {restored} (like {source} including all)")
                        cursor.execute(f"insert into {restored} select * from {source}")
                        cursor.execute(f"select * from {restored}")
                        copied = cursor.fetchall()
                    target_checksum = rows_checksum(copied)
                    check = {
                        "workspace_id": workspace_id,
                        "table": name,
                        "source_schema": source_schema,
                        "restore_schema": restore_schema,
                        "rows": len(copied),
                        "restore_valid": (len(copied) == table["rows"] and
                                          target_checksum == table["checksum"]),
                        "parity_valid": (len(copied) == live_table["rows"] and
                                         target_checksum == live_table["checksum"]),
                    }
                    checks.append(check)
                    if not check["restore_valid"] or not check["parity_valid"]:
                        raise RuntimeError(f"Cutover rehearsal failed for {suffix}.{name}")
            if keep_restore:
                target.commit()
            else:
                target.rollback()
        except Exception:
            target.rollback()
            raise
    restore_valid = bool(checks) and all(item["restore_valid"] for item in checks)
    parity_valid = bool(checks) and all(item["parity_valid"] for item in checks)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "cutover_rehearsal",
        "source_run_id": shadow.get("run_id", ""),
        "rehearsal_run_id": run_id,
        "restore_retained": keep_restore,
        "restore_valid": restore_valid,
        "parity_valid": parity_valid,
        "valid": restore_valid and parity_valid,
        "cutover_ready": restore_valid and parity_valid,
        "cutover_enabled": os.getenv("POSTGRES_CUTOVER_ENABLED", "").lower() == "true",
        "approval_required": True,
        "tables": len(checks),
        "rows": sum(item["rows"] for item in checks),
        "checks": checks,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="BrokerBeacon PostgreSQL shadow migration")
    parser.add_argument("command", choices=("plan", "migrate", "rehearse"))
    parser.add_argument("--source", default=os.getenv("BROKERBEACON_DB", "brokerbeacon.db"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--output", default="")
    parser.add_argument("--validation", default="/var/data/postgres-shadow-validation.json")
    parser.add_argument("--keep-restore", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        result = build_migration_plan(Path(args.source))
    elif args.command == "migrate":
        result = migrate_shadow(Path(args.source), args.database_url)
    else:
        result = rehearse_cutover(Path(args.source), args.database_url,
                                  Path(args.validation), keep_restore=args.keep_restore)
    rendered = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
