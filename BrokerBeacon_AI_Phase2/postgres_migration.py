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


def snapshot_database(path: Path, schema: str, workspace_id: int | None = None,
                      include_rows: bool = True) -> DatabaseSnapshot:
    tables: list[TableSnapshot] = []
    uri = f"file:{Path(path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        names = [row[0] for row in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
        )]
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


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="BrokerBeacon PostgreSQL shadow migration")
    parser.add_argument("command", choices=("plan", "migrate"))
    parser.add_argument("--source", default=os.getenv("BROKERBEACON_DB", "brokerbeacon.db"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = (build_migration_plan(Path(args.source)) if args.command == "plan" else
              migrate_shadow(Path(args.source), args.database_url))
    rendered = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
