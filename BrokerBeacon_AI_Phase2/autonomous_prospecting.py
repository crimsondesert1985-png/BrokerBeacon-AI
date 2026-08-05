"""Autonomous, idempotent promotion of qualified Ember discoveries into CRM prospects.

This module intentionally creates research-ready prospects and contacts only. It does
not send outreach, enroll campaigns, or bypass human review for communication.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists autonomous_prospecting_runs(
    id integer primary key,
    state text default '',
    status text not null default 'Running',
    warehouse_examined integer not null default 0,
    prospects_created integer not null default 0,
    prospects_updated integer not null default 0,
    contacts_created integer not null default 0,
    duplicates_skipped integer not null default 0,
    rejected integer not null default 0,
    error text default '',
    started_at text not null,
    finished_at text default ''
);
create table if not exists autonomous_prospect_links(
    warehouse_company_id integer primary key,
    prospect_id integer not null,
    promotion_reason text not null default '',
    promoted_at text not null,
    updated_at text not null
);
create index if not exists idx_autonomous_runs_state on autonomous_prospecting_runs(state,id desc);
create index if not exists idx_autonomous_links_prospect on autonomous_prospect_links(prospect_id);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _insert_dynamic(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = _columns(conn, table)
    payload = {k: v for k, v in values.items() if k in cols}
    if not payload:
        raise RuntimeError(f"No compatible columns found for {table}")
    names = list(payload)
    marks = ",".join("?" for _ in names)
    cur = conn.execute(
        f"insert into {table}({','.join(names)}) values({marks})",
        tuple(payload[name] for name in names),
    )
    return int(cur.lastrowid)


def _update_dynamic(conn: sqlite3.Connection, table: str, row_id: int, values: dict) -> None:
    cols = _columns(conn, table)
    payload = {k: v for k, v in values.items() if k in cols and k != "id"}
    if not payload:
        return
    names = list(payload)
    conn.execute(
        f"update {table} set " + ",".join(f"{name}=?" for name in names) + " where id=?",
        tuple(payload[name] for name in names) + (row_id,),
    )


def _find_prospect(conn: sqlite3.Connection, company: dict) -> sqlite3.Row | None:
    cols = _columns(conn, "prospects")
    nmls = _digits(str(company.get("nmls_id") or ""))
    if nmls and "nmls" in cols:
        row = conn.execute("select * from prospects where replace(replace(coalesce(nmls,''),'-',''),' ','')=? order by id limit 1", (nmls,)).fetchone()
        if row:
            return row
    website = str(company.get("website") or "").strip().lower().rstrip("/")
    if website and "website" in cols:
        row = conn.execute("select * from prospects where lower(rtrim(coalesce(website,''),'/'))=? order by id limit 1", (website,)).fetchone()
        if row:
            return row
    name = _norm(str(company.get("legal_name") or ""))
    state = str(company.get("state") or "").strip().upper()
    if name:
        rows = conn.execute("select * from prospects where upper(coalesce(state,''))=?", (state,)).fetchall() if "state" in cols else conn.execute("select * from prospects").fetchall()
        for row in rows:
            if _norm(str(row["company"] if "company" in row.keys() else "")) == name:
                return row
    return None


def _quality(company: dict) -> tuple[int, list[str]]:
    score = 35
    reasons = ["Discovered by Ember and persisted in the national warehouse"]
    status = str(company.get("verification_status") or "").lower()
    if company.get("nmls_id"):
        score += 25
        reasons.append("NMLS identifier available")
    if company.get("website"):
        score += 15
        reasons.append("Public company website available")
    if company.get("public_email") or company.get("phone"):
        score += 15
        reasons.append("Public contact channel available")
    if "verified" in status and "needs" not in status:
        score += 10
        reasons.append("Warehouse record is verified")
    return min(score, 100), reasons


def promote_warehouse_companies(conn: sqlite3.Connection, *, state: str = "", limit: int = 100,
                                minimum_score: int = 50) -> dict:
    initialize(conn)
    state = (state or "").strip().upper()[:2]
    now = NOW()
    run_id = int(conn.execute(
        "insert into autonomous_prospecting_runs(state,started_at) values(?,?)", (state, now)
    ).lastrowid)
    counts = {
        "run_id": run_id, "warehouse_examined": 0, "prospects_created": 0,
        "prospects_updated": 0, "contacts_created": 0, "duplicates_skipped": 0,
        "rejected": 0,
    }
    try:
        rows = conn.execute(
            """select * from warehouse_companies
               where (?='' or upper(state)=?)
               order by case when trim(coalesce(nmls_id,''))<>'' then 0 else 1 end,
                        case when trim(coalesce(public_email,''))<>'' or trim(coalesce(phone,''))<>'' then 0 else 1 end,
                        id desc limit ?""",
            (state, state, max(1, min(int(limit), 500))),
        ).fetchall()
        prospect_cols = _columns(conn, "prospects")
        contact_cols = _columns(conn, "contacts")
        for raw in rows:
            company = dict(raw)
            counts["warehouse_examined"] += 1
            score, reasons = _quality(company)
            if score < int(minimum_score) or not str(company.get("legal_name") or "").strip():
                counts["rejected"] += 1
                continue
            existing = _find_prospect(conn, company)
            values = {
                "company": company["legal_name"],
                "nmls": company.get("nmls_id", ""),
                "website": company.get("website", ""),
                "phone": company.get("phone", ""),
                "email": company.get("public_email", ""),
                "city": company.get("city", ""),
                "state": company.get("state", ""),
                "status": "New",
                "score": score,
                "signal": "Autonomously discovered by Ember",
                "source_name": "Ember autonomous prospecting",
                "source_url": company.get("website", ""),
                "verification_status": company.get("verification_status", "Needs review"),
                "ai_summary": "; ".join(reasons),
                "next_best_action": "Verify licensing and decision-maker details before outreach.",
                "created_at": now,
                "updated_at": now,
            }
            if existing:
                prospect_id = int(existing["id"])
                improvements = {}
                for key in ("nmls", "website", "phone", "email", "city", "state", "source_name", "source_url", "verification_status", "ai_summary", "next_best_action"):
                    if key in prospect_cols and not str(existing[key] or "").strip() and str(values.get(key) or "").strip():
                        improvements[key] = values[key]
                if "score" in prospect_cols and int(existing["score"] or 0) < score:
                    improvements["score"] = score
                improvements["updated_at"] = now
                _update_dynamic(conn, "prospects", prospect_id, improvements)
                counts["prospects_updated"] += int(bool(improvements))
                counts["duplicates_skipped"] += 1
            else:
                prospect_id = _insert_dynamic(conn, "prospects", values)
                counts["prospects_created"] += 1
            conn.execute(
                """insert into autonomous_prospect_links(warehouse_company_id,prospect_id,promotion_reason,promoted_at,updated_at)
                   values(?,?,?,?,?) on conflict(warehouse_company_id) do update set
                   prospect_id=excluded.prospect_id,promotion_reason=excluded.promotion_reason,updated_at=excluded.updated_at""",
                (company["id"], prospect_id, json.dumps(reasons), now, now),
            )
            if "prospect_id" in contact_cols:
                officers = conn.execute(
                    "select * from warehouse_officers where company_id=? order by id desc limit 50",
                    (company["id"],),
                ).fetchall()
                for officer_raw in officers:
                    officer = dict(officer_raw)
                    name = str(officer.get("full_name") or "").strip()
                    if not name:
                        continue
                    duplicate = conn.execute(
                        "select id from contacts where prospect_id=? and lower(trim(coalesce(name,'')))=lower(trim(?)) limit 1",
                        (prospect_id, name),
                    ).fetchone() if "name" in contact_cols else None
                    if duplicate:
                        continue
                    contact_values = {
                        "prospect_id": prospect_id,
                        "name": name,
                        "title": officer.get("title", "Loan Officer"),
                        "email": officer.get("public_email", ""),
                        "phone": officer.get("phone", ""),
                        "nmls": officer.get("nmls_id", ""),
                        "city": officer.get("city", ""),
                        "state": officer.get("state", ""),
                        "roster_status": "Needs review",
                        "source_name": "Ember warehouse officer",
                        "created_at": now,
                        "updated_at": now,
                    }
                    _insert_dynamic(conn, "contacts", contact_values)
                    counts["contacts_created"] += 1
        conn.execute(
            """update autonomous_prospecting_runs set status='Completed',warehouse_examined=?,prospects_created=?,
               prospects_updated=?,contacts_created=?,duplicates_skipped=?,rejected=?,finished_at=? where id=?""",
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
