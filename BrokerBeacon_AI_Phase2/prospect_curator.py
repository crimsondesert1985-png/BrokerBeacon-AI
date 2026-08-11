"""Continuous Ember prospect quality agent.

Prospect Curator is a policy-driven Ember specialist that keeps CRM prospect
records clean. It quarantines high-confidence website/page-title false positives,
records an audit trail, and can be invoked after every promotion cycle as well as
periodically while Ember is idle.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ai_orchestrator import initialize as initialize_ai
from prospect_quality import is_publishable_prospect, norm, valid_nmls

NOW = lambda: datetime.now().isoformat(timespec="seconds")
AGENT_KEY = "curator"

SCHEMA = """
create table if not exists prospect_quarantine(
    id integer primary key,
    prospect_id integer,
    company text default '',
    nmls text default '',
    state text default '',
    website text default '',
    source_name text default '',
    source_url text default '',
    reason text not null,
    evidence_json text not null default '{}',
    quarantined_at text not null,
    unique(prospect_id, reason)
);
create index if not exists idx_prospect_quarantine_company on prospect_quarantine(company,state);
create table if not exists prospect_curator_runs(
    id integer primary key,
    examined integer not null default 0,
    quarantined integer not null default 0,
    retained integer not null default 0,
    started_at text not null,
    finished_at text default '',
    status text not null default 'Running',
    error text default ''
);
"""

EXTRA_BAD_EXACT = {
    "privacy policy", "terms of use", "terms and conditions", "careers", "blog",
    "news", "resources", "login", "sign in", "apply", "apply online", "contact us",
    "about us", "our company", "branch locations", "locations", "licensing",
    "licenses", "state licensing", "loan officer search", "find an originator",
    "find a mortgage professional", "mortgage calculator", "calculators",
}

EXTRA_BAD_CONTAINS = (
    "privacy policy", "terms of use", "terms and conditions", "cookie policy",
    "find a loan officer", "find an originator", "loan officer search",
    "meet the team", "our loan officers", "state licensing", "license disclosures",
    "mortgage calculator", "apply for a loan", "start your application",
    "best mortgage", "top mortgage", "mortgage brokers near", "directory",
    "annual report", "consumer access", "department of", "division of",
)


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    initialize_ai(conn)
    now = NOW()
    conn.execute(
        """insert into ai_agents(agent_key,display_name,role,personality,system_prompt,preferred_model,created_at,updated_at)
           values(?,?,?,?,?,?,?,?)
           on conflict(agent_key) do update set
             display_name=excluded.display_name,role=excluded.role,personality=excluded.personality,
             system_prompt=excluded.system_prompt,updated_at=excluded.updated_at""",
        (
            AGENT_KEY,
            "Prospect Curator",
            "Prospect quality and false-positive prevention",
            "Skeptical, conservative, evidence-first, protective of CRM quality",
            "Keep only real mortgage-company prospects. Quarantine navigation labels, article titles, directories, people mistaken for companies, malformed NMLS records, and generic web results. Never invent facts and never remove a borderline company without high-confidence evidence.",
            "policy-engine",
            now,
            now,
        ),
    )
    conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _value(row: sqlite3.Row, key: str) -> str:
    return str(row[key] or "") if key in row.keys() else ""


def classify(row: sqlite3.Row) -> tuple[bool, list[str]]:
    company = _value(row, "company").strip()
    nmls = _value(row, "nmls").strip()
    source = _value(row, "source_name").strip()
    website = _value(row, "website").strip()
    source_url = _value(row, "source_url").strip()
    normalized = norm(company)
    reasons: list[str] = []

    if not is_publishable_prospect(company, nmls, source):
        reasons.append("failed shared publishable-prospect quality gate")
    if normalized in EXTRA_BAD_EXACT:
        reasons.append("generic website/navigation title")
    if any(token in normalized for token in EXTRA_BAD_CONTAINS):
        reasons.append("page-title or directory language")
    if company.count("::") or " | " in company or " - home" in company.lower():
        reasons.append("composite webpage title")
    if ".com" in company.lower() or ".net" in company.lower() or ".org" in company.lower():
        if not any(word in normalized for word in ("mortgage", "financial", "finance", "lending", "funding", "capital")):
            reasons.append("domain name promoted as company")
    if not valid_nmls(nmls):
        reasons.append("missing or malformed NMLS")
    if source_url and any(fragment in source_url.lower() for fragment in ("/blog/", "/news/", "/article/", "/resources/", "/privacy", "/terms")):
        reasons.append("non-company source page")
    if website and any(fragment in website.lower() for fragment in ("/blog/", "/news/", "/article/", "/privacy", "/terms")):
        reasons.append("non-company website URL")

    # Only quarantine high-confidence failures. Borderline records remain visible
    # and can be enriched/reviewed rather than silently discarded.
    return bool(reasons), sorted(set(reasons))


def curate_prospects(conn: sqlite3.Connection, *, limit: int = 10000) -> dict:
    initialize(conn)
    start = NOW()
    run_id = int(conn.execute("insert into prospect_curator_runs(started_at) values(?)", (start,)).lastrowid)
    examined = quarantined = retained = 0
    try:
        columns = _columns(conn, "prospects")
        wanted = [c for c in ("id", "company", "nmls", "state", "website", "source_name", "source_url") if c in columns]
        if "id" not in wanted:
            raise RuntimeError("Prospects table is missing id")
        rows = conn.execute(
            f"select {','.join(wanted)} from prospects order by id desc limit ?",
            (max(1, min(int(limit), 50000)),),
        ).fetchall()
        for row in rows:
            examined += 1
            reject, reasons = classify(row)
            if not reject:
                retained += 1
                continue
            prospect_id = int(row["id"])
            evidence = {
                "company": _value(row, "company"),
                "nmls": _value(row, "nmls"),
                "state": _value(row, "state"),
                "website": _value(row, "website"),
                "source_name": _value(row, "source_name"),
                "source_url": _value(row, "source_url"),
                "reasons": reasons,
            }
            conn.execute(
                """insert or ignore into prospect_quarantine(
                   prospect_id,company,nmls,state,website,source_name,source_url,reason,evidence_json,quarantined_at
                   ) values(?,?,?,?,?,?,?,?,?,?)""",
                (
                    prospect_id,
                    evidence["company"], evidence["nmls"], evidence["state"], evidence["website"],
                    evidence["source_name"], evidence["source_url"], "; ".join(reasons),
                    json.dumps(evidence, sort_keys=True), NOW(),
                ),
            )
            if "contacts" in {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}:
                contact_cols = _columns(conn, "contacts")
                if "prospect_id" in contact_cols:
                    conn.execute("delete from contacts where prospect_id=?", (prospect_id,))
            if "autonomous_prospect_links" in {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}:
                conn.execute("delete from autonomous_prospect_links where prospect_id=?", (prospect_id,))
            conn.execute("delete from prospects where id=?", (prospect_id,))
            quarantined += 1

        finished = NOW()
        conn.execute(
            "update prospect_curator_runs set examined=?,quarantined=?,retained=?,status='Completed',finished_at=? where id=?",
            (examined, quarantined, retained, finished, run_id),
        )
        agent = conn.execute("select id from ai_agents where agent_key=?", (AGENT_KEY,)).fetchone()
        if agent:
            conn.execute(
                """insert into ai_tasks(agent_id,task_type,entity_type,priority,status,input_json,output_json,model,attempts,created_at,started_at,finished_at)
                   values(?, 'prospect_quality_sweep', 'prospect_catalog', 95, 'Completed', '{}', ?, 'policy-engine', 1, ?, ?, ?)""",
                (agent[0], json.dumps({"examined": examined, "quarantined": quarantined, "retained": retained}), start, start, finished),
            )
        conn.commit()
        return {"run_id": run_id, "examined": examined, "quarantined": quarantined, "retained": retained}
    except Exception as exc:
        conn.rollback()
        initialize(conn)
        conn.execute(
            "update prospect_curator_runs set status='Failed',error=?,finished_at=? where id=?",
            (str(exc)[:1000], NOW(), run_id),
        )
        conn.commit()
        raise


__all__ = ["AGENT_KEY", "initialize", "classify", "curate_prospects"]
