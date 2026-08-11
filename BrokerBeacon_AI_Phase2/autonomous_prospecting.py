"""Promote only Mortgage Matchup-proven warehouse companies into CRM prospects."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from prospect_quality import is_publishable_prospect

NOW = lambda: datetime.now().isoformat(timespec="seconds")
MATCHUP_SOURCE = "Mortgage Matchup"
CRM_SOURCE = "Mortgage Matchup via Ember"
SCHEMA = """
create table if not exists autonomous_prospecting_runs(
 id integer primary key,state text default '',status text not null default 'Running',
 warehouse_examined integer not null default 0,prospects_created integer not null default 0,
 prospects_updated integer not null default 0,contacts_created integer not null default 0,
 duplicates_skipped integer not null default 0,rejected integer not null default 0,
 error text default '',started_at text not null,finished_at text default '');
create table if not exists autonomous_prospect_links(
 warehouse_company_id integer primary key,prospect_id integer not null,
 promotion_reason text not null default '',promoted_at text not null,updated_at text not null);
create index if not exists idx_autonomous_runs_state on autonomous_prospecting_runs(state,id desc);
create index if not exists idx_autonomous_links_prospect on autonomous_prospect_links(prospect_id);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _insert_dynamic(conn: sqlite3.Connection, table: str, values: dict) -> int:
    columns = _columns(conn, table)
    payload = {key: value for key, value in values.items() if key in columns}
    if not payload:
        raise RuntimeError(f"No compatible columns found for {table}")
    names = list(payload)
    cursor = conn.execute(
        f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})",
        tuple(payload[name] for name in names),
    )
    return int(cursor.lastrowid)


def _update_dynamic(conn: sqlite3.Connection, table: str, row_id: int, values: dict) -> None:
    columns = _columns(conn, table)
    payload = {key: value for key, value in values.items() if key in columns and key != "id"}
    if not payload:
        return
    names = list(payload)
    conn.execute(
        f"update {table} set " + ",".join(f"{name}=?" for name in names) + " where id=?",
        tuple(payload[name] for name in names) + (row_id,),
    )


def _find_prospect(conn: sqlite3.Connection, company: dict) -> sqlite3.Row | None:
    columns = _columns(conn, "prospects")
    nmls = _digits(str(company.get("nmls_id") or ""))
    if nmls and "nmls" in columns:
        row = conn.execute(
            "select * from prospects where replace(replace(coalesce(nmls,''),'-',''),' ','')=? order by id limit 1",
            (nmls,),
        ).fetchone()
        if row:
            return row
    normalized = _normalize(str(company.get("legal_name") or ""))
    state = str(company.get("state") or "").upper()
    rows = conn.execute(
        "select * from prospects where upper(coalesce(state,''))=?",
        (state,),
    ).fetchall() if "state" in columns else conn.execute("select * from prospects").fetchall()
    return next((row for row in rows if _normalize(str(row["company"] or "")) == normalized), None)


def promote_warehouse_companies(
    conn: sqlite3.Connection,
    *,
    state: str = "",
    limit: int = 100,
    minimum_score: int = 50,
) -> dict:
    initialize(conn)
    state = (state or "").upper()[:2]
    now = NOW()
    run_id = int(conn.execute(
        "insert into autonomous_prospecting_runs(state,started_at) values(?,?)",
        (state, now),
    ).lastrowid)
    counts = {
        "run_id": run_id,
        "warehouse_examined": 0,
        "prospects_created": 0,
        "prospects_updated": 0,
        "contacts_created": 0,
        "duplicates_skipped": 0,
        "rejected": 0,
    }
    try:
        companies = conn.execute(
            """select distinct company.*
               from warehouse_companies company
               join warehouse_source_records record
                 on record.entity_type='company' and record.entity_id=company.id
               join warehouse_sources source on source.id=record.source_id
               where source.name=? and (?='' or upper(company.state)=?)
               order by company.id desc limit ?""",
            (MATCHUP_SOURCE, state, state, max(1, min(int(limit), 1000))),
        ).fetchall()
        prospect_columns = _columns(conn, "prospects")
        contact_columns = _columns(conn, "contacts")
        for raw_company in companies:
            company = dict(raw_company)
            counts["warehouse_examined"] += 1
            company_name = str(company.get("legal_name") or "").strip()
            company_nmls = _digits(str(company.get("nmls_id") or ""))
            if not is_publishable_prospect(company_name, company_nmls, CRM_SOURCE):
                counts["rejected"] += 1
                continue
            score = 95 if company.get("phone") or company.get("public_email") else 90
            values = {
                "company": company_name,
                "nmls": company_nmls,
                "website": company.get("website", ""),
                "phone": company.get("phone", ""),
                "email": company.get("public_email", ""),
                "city": company.get("city", ""),
                "state": company.get("state", ""),
                "status": "New",
                "score": max(score, int(minimum_score)),
                "signal": "Verified public Mortgage Matchup brokerage listing",
                "source_name": CRM_SOURCE,
                "source_url": "https://mortgagematchup.com",
                "verification_status": "Verify current licensing in NMLS before outreach",
                "ai_summary": "Mortgage Matchup brokerage with company NMLS and linked public loan-originator profiles.",
                "next_best_action": "Review company and loan-officer contact details, then verify licensing before outreach.",
                "created_at": now,
                "updated_at": now,
            }
            existing = _find_prospect(conn, company)
            if existing:
                prospect_id = int(existing["id"])
                updates = {
                    key: value for key, value in values.items()
                    if key in prospect_columns and key != "created_at" and (
                        key in {"source_name", "source_url", "signal", "verification_status", "ai_summary", "next_best_action", "updated_at", "score"}
                        or not str(existing[key] or "").strip()
                    )
                }
                _update_dynamic(conn, "prospects", prospect_id, updates)
                counts["prospects_updated"] += 1
                counts["duplicates_skipped"] += 1
            else:
                prospect_id = _insert_dynamic(conn, "prospects", values)
                counts["prospects_created"] += 1

            reason = ["Mortgage Matchup company source record", "Company NMLS available", "Prospect quality gate passed"]
            conn.execute(
                """insert into autonomous_prospect_links(
                     warehouse_company_id,prospect_id,promotion_reason,promoted_at,updated_at)
                   values(?,?,?,?,?)
                   on conflict(warehouse_company_id) do update set
                     prospect_id=excluded.prospect_id,
                     promotion_reason=excluded.promotion_reason,
                     updated_at=excluded.updated_at""",
                (company["id"], prospect_id, json.dumps(reason), now, now),
            )

            officers = conn.execute(
                "select * from warehouse_officers where company_id=? order by id",
                (company["id"],),
            ).fetchall()
            for raw_officer in officers:
                officer = dict(raw_officer)
                name = str(officer.get("full_name") or "").strip()
                officer_nmls = _digits(str(officer.get("nmls_id") or ""))
                email = str(officer.get("public_email") or "").strip()
                phone = str(officer.get("phone") or "").strip()
                if not name or "prospect_id" not in contact_columns:
                    continue
                if not officer_nmls and not email and not phone:
                    continue
                if officer_nmls:
                    duplicate = conn.execute(
                        """select id from contacts where prospect_id=? and (
                             replace(replace(coalesce(nmls,''),'-',''),' ','')=?
                             or lower(trim(coalesce(name,'')))=lower(trim(?))) limit 1""",
                        (prospect_id, officer_nmls, name),
                    ).fetchone()
                else:
                    duplicate = conn.execute(
                        """select id from contacts where prospect_id=?
                           and lower(trim(coalesce(name,'')))=lower(trim(?)) limit 1""",
                        (prospect_id, name),
                    ).fetchone()
                title = officer.get("title") or "Mortgage Loan Originator"
                contact_values = {
                    "prospect_id": prospect_id,
                    "name": name,
                    "title": title,
                    "role": title,
                    "email": email,
                    "phone": phone,
                    "nmls": officer_nmls,
                    "city": officer.get("city", ""),
                    "state": officer.get("state", ""),
                    "roster_status": "Verify in NMLS",
                    "source_name": CRM_SOURCE,
                    "updated_at": now,
                }
                if duplicate:
                    _update_dynamic(conn, "contacts", int(duplicate[0]), contact_values)
                else:
                    contact_values["created_at"] = now
                    _insert_dynamic(conn, "contacts", contact_values)
                    counts["contacts_created"] += 1

        conn.execute(
            """update autonomous_prospecting_runs set status='Completed',warehouse_examined=?,
               prospects_created=?,prospects_updated=?,contacts_created=?,duplicates_skipped=?,
               rejected=?,finished_at=? where id=?""",
            (counts["warehouse_examined"], counts["prospects_created"], counts["prospects_updated"],
             counts["contacts_created"], counts["duplicates_skipped"], counts["rejected"], NOW(), run_id),
        )
        conn.commit()
        return counts
    except Exception as exc:
        conn.rollback()
        initialize(conn)
        conn.execute(
            "update autonomous_prospecting_runs set status='Failed',error=?,finished_at=? where id=?",
            (str(exc)[:1000], NOW(), run_id),
        )
        conn.commit()
        raise