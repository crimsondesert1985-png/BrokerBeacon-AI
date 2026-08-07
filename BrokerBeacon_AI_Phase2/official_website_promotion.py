"""Safely link official-company-website contacts to existing CRM prospects."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime


NOW = lambda: datetime.now().isoformat(timespec="seconds")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1",
        (table,),
    ).fetchone()
    return bool(row)


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _insert_dynamic(conn: sqlite3.Connection, table: str, values: dict) -> int:
    columns = _columns(conn, table)
    payload = {key: value for key, value in values.items() if key in columns}
    names = list(payload)
    cursor = conn.execute(
        f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})",
        tuple(payload[name] for name in names),
    )
    return int(cursor.lastrowid)


def _update_dynamic(conn: sqlite3.Connection, table: str, row_id: int, values: dict) -> None:
    columns = _columns(conn, table)
    payload = {key: value for key, value in values.items() if key in columns and key != "id"}
    names = list(payload)
    if names:
        conn.execute(
            f"update {table} set " + ",".join(f"{name}=?" for name in names) + " where id=?",
            tuple(payload[name] for name in names) + (row_id,),
        )


def promote_official_website_contacts(conn: sqlite3.Connection, *, state: str = "", limit: int = 2000) -> dict:
    """Insert or update review-gated contacts; this function never deletes CRM data.

    Safely defers when the warehouse or CRM tables required for promotion are not
    present (e.g. minimal worker test databases).
    """
    state = (state or "").strip().upper()
    required_tables = (
        "contacts",
        "warehouse_officers",
        "warehouse_companies",
        "autonomous_prospect_links",
    )
    if not all(_table_exists(conn, name) for name in required_tables):
        return {"examined": 0, "created": 0, "updated": 0, "deferred": True}
    contact_columns = _columns(conn, "contacts")
    if "prospect_id" not in contact_columns:
        return {"examined": 0, "created": 0, "updated": 0, "deferred": True}
    try:
        rows = conn.execute(
            """select officer.*,company.website,link.prospect_id
               from warehouse_officers officer
               join warehouse_companies company on company.id=officer.company_id
               join autonomous_prospect_links link on link.warehouse_company_id=company.id
               where officer.verification_status like 'Public company website%'
                 and (?='' or upper(officer.state)=?)
               order by officer.id limit ?""",
            (state, state, max(1, min(int(limit), 10000))),
        ).fetchall()
    except sqlite3.Error:
        # Schema drift or incomplete warehouse: treat as deferred, never fail the job.
        return {"examined": 0, "created": 0, "updated": 0, "deferred": True}
    counts = {"examined": 0, "created": 0, "updated": 0}
    for raw in rows:
        officer = dict(raw)
        counts["examined"] += 1
        prospect_id = int(officer["prospect_id"])
        name = str(officer.get("full_name") or "").strip()
        if not name:
            continue
        nmls = _digits(str(officer.get("nmls_id") or ""))
        if nmls and "nmls" in contact_columns:
            existing = conn.execute(
                """select id from contacts where prospect_id=? and (
                   replace(replace(coalesce(nmls,''),'-',''),' ','')=?
                   or lower(trim(coalesce(name,'')))=lower(trim(?))) limit 1""",
                (prospect_id, nmls, name),
            ).fetchone()
        else:
            existing = conn.execute(
                """select id from contacts where prospect_id=?
                   and lower(trim(coalesce(name,'')))=lower(trim(?)) limit 1""",
                (prospect_id, name),
            ).fetchone()
        values = {
            "prospect_id": prospect_id,
            "name": name,
            "role": officer.get("title") or "Mortgage professional",
            "email": officer.get("public_email", ""),
            "phone": officer.get("phone", ""),
            "nmls": nmls,
            "city": officer.get("city", ""),
            "state": officer.get("state", ""),
            "roster_status": "Official website - verify in NMLS",
            "source_name": "Official company website via Ember",
            "source_url": officer.get("website", ""),
            "updated_at": NOW(),
        }
        if existing:
            _update_dynamic(conn, "contacts", int(existing[0]), values)
            counts["updated"] += 1
        else:
            values["created_at"] = NOW()
            _insert_dynamic(conn, "contacts", values)
            counts["created"] += 1
    conn.commit()
    return counts
