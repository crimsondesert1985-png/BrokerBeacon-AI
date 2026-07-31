"""AI intelligence layer for Sprint 37.

Uses OpenAI Responses API when configured, with deterministic fallbacks when it
is not. AI outputs are stored separately from source facts and remain reviewable.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists ai_enrichment_jobs(
    id integer primary key,
    status text not null default 'Queued',
    model text default '',
    requested_count integer not null default 0,
    processed_count integer not null default 0,
    failed_count integer not null default 0,
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    error text default ''
);
create table if not exists ai_contact_insights(
    id integer primary key,
    discovered_contact_id integer not null unique,
    canonical_company_name text default '',
    canonical_person_name text default '',
    entity_type text not null default 'Unknown',
    confidence integer not null default 0,
    opportunity_score integer not null default 0,
    territory_fit integer not null default 0,
    product_fit text default '',
    next_best_action text default '',
    duplicate_group_key text default '',
    reasons_json text not null default '[]',
    model text default '',
    ai_status text not null default 'Pending',
    reviewed_status text not null default 'Pending review',
    created_at text not null,
    updated_at text not null,
    foreign key(discovered_contact_id) references discovered_contacts(id)
);
create index if not exists idx_ai_contact_review on ai_contact_insights(reviewed_status,opportunity_score desc);
create index if not exists idx_ai_duplicate_key on ai_contact_insights(duplicate_group_key);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _fallback(contact: dict) -> dict:
    has_email = bool(contact.get("public_email"))
    has_phone = bool(contact.get("phone"))
    has_nmls = bool(contact.get("nmls_id"))
    has_person = bool(contact.get("person_name"))
    confidence = min(95, 40 + 15 * has_email + 15 * has_phone + 20 * has_nmls + 10 * has_person)
    opportunity = min(100, 25 + 20 * has_email + 20 * has_phone + 20 * has_nmls + 10 * has_person)
    company = (contact.get("company_name") or "").strip()
    person = (contact.get("person_name") or "").strip()
    duplicate_key = "|".join([
        _normalize(company),
        str(contact.get("nmls_id") or ""),
        _normalize(person),
        str(contact.get("state") or ""),
    ])
    return {
        "canonical_company_name": company,
        "canonical_person_name": person,
        "entity_type": "Loan officer" if person else "Company",
        "confidence": confidence,
        "opportunity_score": opportunity,
        "territory_fit": 50,
        "product_fit": "Needs human review",
        "next_best_action": "Verify the public contact details and approve or reject the record.",
        "duplicate_group_key": duplicate_key,
        "reasons": [
            reason for condition, reason in (
                (has_email, "Public business email found"),
                (has_phone, "Public business phone found"),
                (has_nmls, "NMLS identifier found"),
                (has_person, "Named mortgage professional found"),
            ) if condition
        ],
    }


def _extract_output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    return ""


def _openai(contact: dict) -> dict:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    model = os.getenv("OPENAI_PROSPECT_MODEL", "gpt-5-mini").strip()
    instructions = (
        "You classify mortgage-industry public business contacts. Never invent facts. "
        "Use only the supplied fields. Return one JSON object with keys: "
        "canonical_company_name, canonical_person_name, entity_type, confidence, "
        "opportunity_score, territory_fit, product_fit, next_best_action, "
        "duplicate_group_key, reasons. Scores are integers 0-100. reasons is an array. "
        "If evidence is weak, lower confidence and explicitly say human verification is needed."
    )
    body = {
        "model": model,
        "store": False,
        "instructions": instructions,
        "input": json.dumps(contact, ensure_ascii=True),
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = _extract_output_text(payload).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    result = json.loads(text)
    result["model"] = model
    return result


def enrich_contact(contact: dict) -> dict:
    fallback = _fallback(contact)
    try:
        result = _openai(contact)
        merged = {**fallback, **result}
        merged["ai_status"] = "Completed"
        return merged
    except Exception as exc:
        fallback["model"] = "deterministic-fallback"
        fallback["ai_status"] = "Fallback"
        fallback["reasons"] = list(fallback.get("reasons") or []) + [f"AI unavailable: {str(exc)[:120]}"]
        return fallback


def process_batch(conn: sqlite3.Connection, limit: int = 100) -> dict:
    initialize(conn)
    limit = min(max(int(limit), 1), 1000)
    rows = conn.execute(
        """select d.* from discovered_contacts d
           left join ai_contact_insights a on a.discovered_contact_id=d.id
           where a.id is null order by d.id limit ?""",
        (limit,),
    ).fetchall()
    now = NOW()
    model = os.getenv("OPENAI_PROSPECT_MODEL", "gpt-5-mini") if os.getenv("OPENAI_API_KEY") else "deterministic-fallback"
    job_id = int(conn.execute(
        "insert into ai_enrichment_jobs(status,model,requested_count,created_at,started_at) values('Running',?,?,?,?)",
        (model, len(rows), now, now),
    ).lastrowid)
    processed = failed = 0
    for row in rows:
        try:
            contact = dict(row)
            insight = enrich_contact(contact)
            conn.execute(
                """insert into ai_contact_insights(
                   discovered_contact_id,canonical_company_name,canonical_person_name,entity_type,
                   confidence,opportunity_score,territory_fit,product_fit,next_best_action,
                   duplicate_group_key,reasons_json,model,ai_status,created_at,updated_at)
                   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["id"], insight.get("canonical_company_name", ""), insight.get("canonical_person_name", ""),
                    insight.get("entity_type", "Unknown"), int(insight.get("confidence", 0)),
                    int(insight.get("opportunity_score", 0)), int(insight.get("territory_fit", 0)),
                    str(insight.get("product_fit", "")), str(insight.get("next_best_action", "")),
                    str(insight.get("duplicate_group_key", "")), json.dumps(insight.get("reasons") or []),
                    str(insight.get("model", model)), str(insight.get("ai_status", "Completed")), now, NOW(),
                ),
            )
            processed += 1
        except Exception:
            failed += 1
        conn.commit()
    finished = NOW()
    conn.execute(
        "update ai_enrichment_jobs set status='Completed',processed_count=?,failed_count=?,finished_at=? where id=?",
        (processed, failed, finished, job_id),
    )
    conn.commit()
    return {"job_id": job_id, "requested": len(rows), "processed": processed, "failed": failed, "model": model}


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    totals = conn.execute(
        """select count(*),sum(case when ai_status='Completed' then 1 else 0 end),
           sum(case when ai_status='Fallback' then 1 else 0 end),
           sum(case when opportunity_score>=75 then 1 else 0 end),avg(opportunity_score)
           from ai_contact_insights"""
    ).fetchone()
    jobs = [dict(row) for row in conn.execute("select * from ai_enrichment_jobs order by id desc limit 20")]
    return {
        "total": int(totals[0] or 0),
        "ai_completed": int(totals[1] or 0),
        "fallback_completed": int(totals[2] or 0),
        "high_opportunity": int(totals[3] or 0),
        "average_opportunity_score": round(float(totals[4] or 0), 1),
        "recent_jobs": jobs,
    }
