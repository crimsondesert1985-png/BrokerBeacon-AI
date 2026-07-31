"""National prospect warehouse foundation for Sprint 37.

This module keeps the nationwide discovery catalog separate from the active CRM.
It is intentionally source-aware, review-gated, and safe to run repeatedly.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from typing import Iterable, Mapping

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists warehouse_sources(
    id integer primary key,
    name text not null,
    source_type text not null,
    authorization_basis text not null default '',
    source_url text default '',
    active integer not null default 1,
    last_success_at text default '',
    created_at text not null,
    updated_at text not null,
    unique(name,source_type)
);
create table if not exists warehouse_import_jobs(
    id integer primary key,
    source_id integer,
    state text default '',
    status text not null default 'Queued',
    records_received integer not null default 0,
    companies_created integer not null default 0,
    companies_updated integer not null default 0,
    officers_created integer not null default 0,
    duplicate_candidates integer not null default 0,
    rejected_records integer not null default 0,
    error text default '',
    started_at text default '',
    finished_at text default '',
    created_at text not null,
    updated_at text not null,
    foreign key(source_id) references warehouse_sources(id)
);
create table if not exists warehouse_companies(
    id integer primary key,
    canonical_key text not null unique,
    legal_name text not null,
    normalized_name text not null,
    nmls_id text default '',
    website text default '',
    phone text default '',
    public_email text default '',
    city text default '',
    state text default '',
    postal_code text default '',
    verification_status text not null default 'Needs review',
    source_count integer not null default 0,
    first_seen_at text not null,
    last_seen_at text not null,
    created_at text not null,
    updated_at text not null
);
create table if not exists warehouse_branches(
    id integer primary key,
    company_id integer not null,
    branch_key text not null unique,
    branch_name text default '',
    nmls_id text default '',
    address1 text default '',
    city text default '',
    state text default '',
    postal_code text default '',
    phone text default '',
    created_at text not null,
    updated_at text not null,
    foreign key(company_id) references warehouse_companies(id) on delete cascade
);
create table if not exists warehouse_officers(
    id integer primary key,
    company_id integer not null,
    branch_id integer,
    canonical_key text not null unique,
    full_name text not null,
    normalized_name text not null,
    nmls_id text default '',
    title text default '',
    phone text default '',
    public_email text default '',
    city text default '',
    state text default '',
    verification_status text not null default 'Needs review',
    first_seen_at text not null,
    last_seen_at text not null,
    created_at text not null,
    updated_at text not null,
    foreign key(company_id) references warehouse_companies(id) on delete cascade,
    foreign key(branch_id) references warehouse_branches(id) on delete set null
);
create table if not exists warehouse_licenses(
    id integer primary key,
    entity_type text not null,
    entity_id integer not null,
    license_number text default '',
    state text not null,
    status text default '',
    expires_at text default '',
    source_id integer,
    verified_at text default '',
    created_at text not null,
    updated_at text not null,
    unique(entity_type,entity_id,state,license_number)
);
create table if not exists warehouse_duplicate_candidates(
    id integer primary key,
    entity_type text not null,
    left_id integer not null,
    right_id integer not null,
    confidence integer not null default 0,
    reason text not null,
    status text not null default 'Pending review',
    created_at text not null,
    reviewed_at text default '',
    unique(entity_type,left_id,right_id)
);
create table if not exists warehouse_ai_insights(
    id integer primary key,
    entity_type text not null,
    entity_id integer not null,
    opportunity_score integer not null default 0,
    territory_fit integer not null default 0,
    product_fit text default '',
    next_best_action text default '',
    reasons_json text not null default '[]',
    calculated_at text not null,
    unique(entity_type,entity_id)
);
create table if not exists warehouse_source_records(
    id integer primary key,
    source_id integer not null,
    import_job_id integer,
    entity_type text not null,
    entity_id integer not null,
    source_record_id text default '',
    payload_hash text not null,
    captured_at text not null,
    unique(source_id,entity_type,entity_id,payload_hash)
);
create index if not exists idx_wh_company_search on warehouse_companies(state,city,normalized_name);
create index if not exists idx_wh_company_nmls on warehouse_companies(nmls_id);
create index if not exists idx_wh_officer_search on warehouse_officers(state,city,normalized_name);
create index if not exists idx_wh_officer_nmls on warehouse_officers(nmls_id);
create index if not exists idx_wh_jobs_status on warehouse_import_jobs(status,id desc);
create index if not exists idx_wh_duplicates_status on warehouse_duplicate_candidates(status,confidence desc);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def canonical_company_key(record: Mapping[str, object]) -> str:
    nmls = digits(str(record.get("nmls_id") or record.get("nmls") or ""))
    if nmls:
        return f"nmls:{nmls}"
    basis = "|".join([
        normalize(str(record.get("legal_name") or record.get("company") or "")),
        normalize(str(record.get("city") or "")),
        normalize(str(record.get("state") or "")),
        digits(str(record.get("phone") or ""))[-10:],
    ])
    return "company:" + hashlib.sha256(basis.encode()).hexdigest()[:24]


def canonical_officer_key(record: Mapping[str, object], company_id: int) -> str:
    nmls = digits(str(record.get("nmls_id") or record.get("lo_nmls") or ""))
    if nmls:
        return f"nmls:{nmls}"
    basis = "|".join([
        str(company_id),
        normalize(str(record.get("full_name") or record.get("name") or "")),
        normalize(str(record.get("city") or "")),
        normalize(str(record.get("state") or "")),
    ])
    return "officer:" + hashlib.sha256(basis.encode()).hexdigest()[:24]


def create_source(conn: sqlite3.Connection, name: str, source_type: str,
                  authorization_basis: str = "", source_url: str = "") -> int:
    initialize(conn)
    now = NOW()
    conn.execute(
        """insert into warehouse_sources(name,source_type,authorization_basis,source_url,created_at,updated_at)
           values(?,?,?,?,?,?)
           on conflict(name,source_type) do update set
             authorization_basis=excluded.authorization_basis,
             source_url=excluded.source_url,updated_at=excluded.updated_at""",
        (name, source_type, authorization_basis, source_url, now, now),
    )
    row = conn.execute(
        "select id from warehouse_sources where name=? and source_type=?", (name, source_type)
    ).fetchone()
    conn.commit()
    return int(row[0])


def create_import_job(conn: sqlite3.Connection, source_id: int | None, state: str = "") -> int:
    initialize(conn)
    now = NOW()
    cur = conn.execute(
        "insert into warehouse_import_jobs(source_id,state,created_at,updated_at) values(?,?,?,?)",
        (source_id, (state or "").upper(), now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def _record_source(conn: sqlite3.Connection, source_id: int, job_id: int,
                   entity_type: str, entity_id: int, source_record_id: str,
                   record: Mapping[str, object]) -> None:
    payload = json.dumps(dict(record), sort_keys=True, default=str)
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    conn.execute(
        """insert or ignore into warehouse_source_records
           (source_id,import_job_id,entity_type,entity_id,source_record_id,payload_hash,captured_at)
           values(?,?,?,?,?,?,?)""",
        (source_id, job_id, entity_type, entity_id, source_record_id, payload_hash, NOW()),
    )


def ingest_companies(conn: sqlite3.Connection, job_id: int, source_id: int,
                     records: Iterable[Mapping[str, object]]) -> dict:
    initialize(conn)
    now = NOW()
    counts = {"received": 0, "created": 0, "updated": 0, "rejected": 0}
    conn.execute("update warehouse_import_jobs set status='Running',started_at=?,updated_at=? where id=?",
                 (now, now, job_id))
    for record in records:
        counts["received"] += 1
        name = str(record.get("legal_name") or record.get("company") or "").strip()
        if not name:
            counts["rejected"] += 1
            continue
        key = canonical_company_key(record)
        existing = conn.execute("select id from warehouse_companies where canonical_key=?", (key,)).fetchone()
        values = (
            name, normalize(name), digits(str(record.get("nmls_id") or record.get("nmls") or "")),
            str(record.get("website") or ""), digits(str(record.get("phone") or "")),
            str(record.get("public_email") or record.get("email") or ""),
            str(record.get("city") or ""), str(record.get("state") or "").upper(),
            str(record.get("postal_code") or record.get("zip") or ""), now, now,
        )
        if existing:
            company_id = int(existing[0])
            conn.execute(
                """update warehouse_companies set legal_name=?,normalized_name=?,nmls_id=?,website=?,phone=?,
                   public_email=?,city=?,state=?,postal_code=?,last_seen_at=?,updated_at=?,source_count=source_count+1
                   where id=?""", values + (company_id,))
            counts["updated"] += 1
        else:
            cur = conn.execute(
                """insert into warehouse_companies(canonical_key,legal_name,normalized_name,nmls_id,website,phone,
                   public_email,city,state,postal_code,source_count,first_seen_at,last_seen_at,created_at,updated_at)
                   values(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)""",
                (key,) + values[:9] + (now, now, now, now),
            )
            company_id = int(cur.lastrowid)
            counts["created"] += 1
        _record_source(conn, source_id, job_id, "company", company_id,
                       str(record.get("source_record_id") or ""), record)
    conn.execute(
        """update warehouse_import_jobs set status='Completed',records_received=?,companies_created=?,
           companies_updated=?,rejected_records=?,finished_at=?,updated_at=? where id=?""",
        (counts["received"], counts["created"], counts["updated"], counts["rejected"], now, now, job_id),
    )
    conn.execute("update warehouse_sources set last_success_at=?,updated_at=? where id=?", (now, now, source_id))
    conn.commit()
    return counts


def search(conn: sqlite3.Connection, query: str = "", state: str = "", limit: int = 50) -> dict:
    initialize(conn)
    q = f"%{normalize(query)}%"
    state = (state or "").upper()
    company_rows = conn.execute(
        """select id,legal_name,nmls_id,city,state,website,phone,public_email,verification_status
           from warehouse_companies
           where (?='' or state=?) and (?='%%' or normalized_name like ? or nmls_id like ?)
           order by legal_name limit ?""",
        (state, state, q, q, f"%{digits(query)}%", limit),
    ).fetchall()
    officer_rows = conn.execute(
        """select o.id,o.full_name,o.nmls_id,o.city,o.state,o.phone,o.public_email,c.legal_name
           from warehouse_officers o join warehouse_companies c on c.id=o.company_id
           where (?='' or o.state=?) and (?='%%' or o.normalized_name like ? or o.nmls_id like ?)
           order by o.full_name limit ?""",
        (state, state, q, q, f"%{digits(query)}%", limit),
    ).fetchall()
    return {
        "companies": [dict(zip(["id","legal_name","nmls_id","city","state","website","phone","public_email","verification_status"], r)) for r in company_rows],
        "officers": [dict(zip(["id","full_name","nmls_id","city","state","phone","public_email","company"], r)) for r in officer_rows],
    }


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    scalar = lambda sql: int(conn.execute(sql).fetchone()[0])
    coverage = [dict(zip(["state", "companies", "officers"], row)) for row in conn.execute(
        """select c.state,count(distinct c.id),count(distinct o.id)
           from warehouse_companies c left join warehouse_officers o on o.company_id=c.id
           group by c.state order by count(distinct c.id) desc,c.state""")]
    jobs = [dict(zip(["id","state","status","records_received","companies_created","companies_updated","rejected_records","created_at"], row))
            for row in conn.execute("""select id,state,status,records_received,companies_created,companies_updated,
                rejected_records,created_at from warehouse_import_jobs order by id desc limit 20""")]
    return {
        "companies": scalar("select count(*) from warehouse_companies"),
        "officers": scalar("select count(*) from warehouse_officers"),
        "branches": scalar("select count(*) from warehouse_branches"),
        "licenses": scalar("select count(*) from warehouse_licenses"),
        "pending_duplicates": scalar("select count(*) from warehouse_duplicate_candidates where status='Pending review'"),
        "coverage": coverage,
        "recent_jobs": jobs,
    }
