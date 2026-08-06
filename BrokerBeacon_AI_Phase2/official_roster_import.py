"""Import and promote clean official public mortgage-broker roster records."""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import urllib.request
from datetime import datetime

from national_warehouse import create_import_job, create_source, ingest_companies
from prospect_quality import is_clean_company_name, valid_nmls, digits, norm

NOW = lambda: datetime.now().isoformat(timespec="seconds")
SOURCE_NAME = "Missouri Division of Finance Mortgage Broker Roster"
CRM_SOURCE = "Official regulator mortgage broker roster"
MO_EXPORT = "https://finance.mo.gov/bank-licensee-search/export?_format=csv&formpos_institutions_and_professional_registration_job_openings_and_job_information=&page="
UA = "BrokerBeacon-Ember/4.0 (+official public license roster import)"


def _fetch_csv(url: str = MO_EXPORT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,application/csv,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"Official roster returned HTTP {response.status}")
        raw = response.read(25_000_000)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "ignore")


def _field(row: dict, *names: str) -> str:
    lowered = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"pragma table_info({table})")}


def _normalize_state(value: str) -> str:
    value = (value or "").strip().upper()
    names = "ALABAMA AL ALASKA AK ARIZONA AZ ARKANSAS AR CALIFORNIA CA COLORADO CO CONNECTICUT CT DELAWARE DE FLORIDA FL GEORGIA GA HAWAII HI IDAHO ID ILLINOIS IL INDIANA IN IOWA IA KANSAS KS KENTUCKY KY LOUISIANA LA MAINE ME MARYLAND MD MASSACHUSETTS MA MICHIGAN MI MINNESOTA MN MISSISSIPPI MS MISSOURI MO MONTANA MT NEBRASKA NE NEVADA NV NEW_HAMPSHIRE NH NEW_JERSEY NJ NEW_MEXICO NM NEW_YORK NY NORTH_CAROLINA NC NORTH_DAKOTA ND OHIO OH OKLAHOMA OK OREGON OR PENNSYLVANIA PA RHODE_ISLAND RI SOUTH_CAROLINA SC SOUTH_DAKOTA SD TENNESSEE TN TEXAS TX UTAH UT VERMONT VT VIRGINIA VA WASHINGTON WA WEST_VIRGINIA WV WISCONSIN WI WYOMING WY"
    parts = names.split()
    aliases = {parts[i].replace("_", " "): parts[i + 1] for i in range(0, len(parts), 2)}
    return aliases.get(value, value if len(value) == 2 else "")


def import_missouri_broker_roster(conn: sqlite3.Connection, target_minimum: int = 500) -> dict:
    source_id = create_source(conn, SOURCE_NAME, "Official regulator CSV", "Public regulator license roster; verify current status before outreach", MO_EXPORT)
    job_id = create_import_job(conn, source_id, "")
    reader = csv.DictReader(io.StringIO(_fetch_csv()))
    records, seen = [], set()
    rejected = 0
    for row in reader:
        if _field(row, "Type", "License Type", "type_name").strip().lower() != "mortgage broker":
            continue
        name = _field(row, "Name", "Entity Name", "Company Name")
        license_no = _field(row, "License #", "License Number", "License", "Charter#")
        state = _normalize_state(_field(row, "State"))
        nmls = digits(license_no)
        if not state or not valid_nmls(nmls) or not is_clean_company_name(name, trusted_roster=True):
            rejected += 1
            continue
        key = (nmls, norm(name), state)
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "legal_name": name.strip(), "nmls_id": nmls,
            "city": _field(row, "City"), "state": state,
            "postal_code": _field(row, "Zip", "ZIP Code", "Postal Code"),
            "address1": _field(row, "Address", "Street Address"),
            "source_record_id": license_no, "source_url": MO_EXPORT,
            "verification_status": "Official regulator mortgage broker roster - verify current status in NMLS",
        })
    result = ingest_companies(conn, job_id, source_id, records)
    result.update({"source_rows": len(records), "filtered_out": rejected, "target_minimum": target_minimum, "source_id": source_id, "finished_at": NOW()})
    return result


def _find_existing(conn: sqlite3.Connection, company: dict):
    nmls = digits(company.get("nmls_id"))
    if nmls:
        row = conn.execute("select * from prospects where replace(replace(coalesce(nmls,''),'-',''),' ','')=? order by id limit 1", (nmls,)).fetchone()
        if row:
            return row
    state = str(company.get("state") or "").upper()
    name = norm(company.get("legal_name"))
    return next((r for r in conn.execute("select * from prospects where upper(coalesce(state,''))=?", (state,)).fetchall() if norm(r["company"]) == name), None)


def _insert_dynamic(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = _cols(conn, table)
    payload = {k: v for k, v in values.items() if k in cols}
    names = list(payload)
    cur = conn.execute(f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})", tuple(payload[n] for n in names))
    return int(cur.lastrowid)


def _update_dynamic(conn: sqlite3.Connection, table: str, row_id: int, values: dict) -> None:
    cols = _cols(conn, table)
    payload = {k: v for k, v in values.items() if k in cols and k != "id"}
    if payload:
        conn.execute(f"update {table} set " + ",".join(f"{k}=?" for k in payload) + " where id=?", tuple(payload[k] for k in payload) + (row_id,))


def promote_official_roster(conn: sqlite3.Connection, target_minimum: int = 500, limit: int = 5000) -> dict:
    now = NOW()
    counts = {"examined": 0, "created": 0, "updated": 0, "linked": 0, "rejected": 0}
    rows = conn.execute("""select distinct c.* from warehouse_companies c
      join warehouse_source_records wr on wr.entity_type='company' and wr.entity_id=c.id
      join warehouse_sources s on s.id=wr.source_id
      where s.name=? and c.nmls_id<>'' and length(trim(c.state))=2
      order by c.state,c.legal_name limit ?""", (SOURCE_NAME, max(1, min(int(limit), 10000)))).fetchall()
    existing_total = int(conn.execute("select count(*) from prospects").fetchone()[0])
    for raw in rows:
        if existing_total + counts["created"] >= target_minimum:
            break
        company = dict(raw)
        counts["examined"] += 1
        name, nmls, state = str(company.get("legal_name") or "").strip(), digits(company.get("nmls_id")), str(company.get("state") or "").upper()
        if not is_clean_company_name(name, trusted_roster=True) or not valid_nmls(nmls) or len(state) != 2:
            counts["rejected"] += 1
            continue
        values = {
            "company": name, "nmls": nmls, "website": company.get("website", ""),
            "phone": company.get("phone", ""), "email": company.get("public_email", ""),
            "city": company.get("city", ""), "state": state, "status": "New", "score": 82,
            "signal": "Official public regulator mortgage broker roster", "source_name": CRM_SOURCE,
            "source_url": MO_EXPORT,
            "verification_status": "Listed as Mortgage Broker by a public regulator; verify current NMLS status before outreach",
            "ai_summary": "Licensed mortgage broker company imported from an official public regulator roster.",
            "next_best_action": "Verify NMLS status and research the owner or production manager before outreach.",
            "created_at": now, "updated_at": now,
        }
        existing = _find_existing(conn, company)
        if existing:
            _update_dynamic(conn, "prospects", int(existing["id"]), {k: v for k, v in values.items() if k != "created_at" and (k in {"signal", "source_name", "source_url", "verification_status", "ai_summary", "next_best_action", "updated_at"} or not str(existing[k] or "").strip())})
            pid = int(existing["id"])
            counts["updated"] += 1
        else:
            pid = _insert_dynamic(conn, "prospects", values)
            counts["created"] += 1
        conn.execute("""insert into autonomous_prospect_links(warehouse_company_id,prospect_id,promotion_reason,promoted_at,updated_at)
          values(?,?,?,?,?) on conflict(warehouse_company_id) do update set prospect_id=excluded.prospect_id,promotion_reason=excluded.promotion_reason,updated_at=excluded.updated_at""",
          (company["id"], pid, json.dumps(["Official mortgage broker roster", "Valid license identifier"]), now, now))
        counts["linked"] += 1
    conn.commit()
    counts["visible_total"] = int(conn.execute("select count(*) from prospects").fetchone()[0])
    return counts


__all__ = ["import_missouri_broker_roster", "promote_official_roster"]
