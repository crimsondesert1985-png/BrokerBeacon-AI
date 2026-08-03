"""Full Ember discovery pipeline: hunt, crawl, warehouse, review."""
from __future__ import annotations

import re
import urllib.parse

from broker_company_contacts import is_excluded_retail_lender, sync_company_contacts
from ember_company_crawler import crawl_and_ingest
from ember_hunt import launch as launch_hunt
from national_warehouse import create_import_job, create_source, ingest_companies


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _company_from_row(row: dict) -> str:
    value = str(row.get("company_name") or row.get("company") or "").strip()
    if value:
        return value
    title = str(row.get("title") or row.get("person_name") or "").strip()
    title = re.sub(r"\s*[-|·].*$", "", title).strip()
    return title or _domain(str(row.get("source_url") or "")).split(".")[0].replace("-", " ").title()


def _blocked_domain(domain: str) -> bool:
    blocked = {
        "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "freddiemac.com",
        "fanniemae.com", "linkedin.com", "facebook.com", "instagram.com", "youtube.com",
        "bankrate.com", "nerdwallet.com", "investopedia.com", "forbes.com", "wikipedia.org",
    }
    return not domain or domain in blocked or any(domain.endswith("." + item) for item in blocked)


def _candidate_rows(conn, run_id: int, state: str) -> list[dict]:
    candidates: list[dict] = []
    for row in conn.execute(
        """select company_name,person_name,title,snippet,nmls_id,city,state,
                  source_url,source_domain,candidate_type,run_id,id,phone,public_email
           from public_search_results
           where review_status<>'Rejected'
             and trim(coalesce(source_url,''))<>''
             and (run_id=? or state=?)
           order by case when run_id=? then 0 else 1 end,id desc
           limit 1000""",
        (run_id, state, run_id),
    ).fetchall():
        candidates.append(dict(row))
    try:
        for row in conn.execute(
            """select company_name as company,source_url,state,'' as city,'' as nmls_id,
                      '' as title,'' as person_name,'' as snippet,'' as phone,'' as public_email
               from ember_company_history
               where upper(state)=? and trim(coalesce(source_url,''))<>''
               order by id desc limit 500""",
            (state,),
        ).fetchall():
            candidates.append(dict(row))
    except Exception:
        pass
    try:
        for row in conn.execute(
            """select company,source_url,state,coalesce(city,'') city,coalesce(nmls,'') nmls_id,
                      company as title,'' as person_name,'' as snippet,'' as phone,'' as public_email
               from national_broker_index
               where upper(state)=? and trim(coalesce(source_url,''))<>''
               order by id desc limit 1000""",
            (state,),
        ).fetchall():
            candidates.append(dict(row))
    except Exception:
        pass
    return candidates


def _build_company_seeds(conn, run_id: int, state: str, company_limit: int) -> list[dict]:
    state = (state or "").strip().upper()[:2]
    seen: set[str] = set()
    seeds: list[dict] = []
    for row in _candidate_rows(conn, run_id, state):
        url = str(row.get("source_url") or "").strip()
        domain = _domain(url)
        if _blocked_domain(domain) or domain in seen:
            continue
        company = _company_from_row(row)
        context = " ".join((str(row.get("title") or ""), str(row.get("snippet") or "")))
        if is_excluded_retail_lender(company, url, context) or not company:
            continue
        seen.add(domain)
        seeds.append({
            "company": company,
            "nmls": str(row.get("nmls_id") or row.get("nmls") or ""),
            "city": str(row.get("city") or ""),
            "state": state or str(row.get("state") or ""),
            "source_url": url,
            "phone": str(row.get("phone") or ""),
            "public_email": str(row.get("public_email") or ""),
        })
        if len(seeds) >= max(1, min(int(company_limit), 25)):
            break
    return seeds


def _persist_seeded_companies(conn, result: dict, state: str) -> dict:
    """Persist every successfully seeded brokerage even when no website survives crawl filtering."""
    names = [str(name or "").strip() for name in (result.get("companies") or []) if str(name or "").strip()]
    if not names:
        return {"received": 0, "created": 0, "updated": 0, "rejected": 0}
    source_id = create_source(
        conn,
        "Ember seeded broker companies",
        "Discovery fallback",
        "Public search or broker index company record; review required",
        "",
    )
    job_id = create_import_job(conn, source_id, state)
    records = []
    seen = set()
    for name in names:
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        if not key or key in seen or is_excluded_retail_lender(name, "", ""):
            continue
        seen.add(key)
        row = conn.execute(
            """select company,coalesce(nmls,''),coalesce(city,''),coalesce(source_url,'')
               from national_broker_index where upper(state)=? and lower(company)=lower(?)
               order by id desc limit 1""",
            (state, name),
        ).fetchone()
        records.append({
            "legal_name": name,
            "nmls_id": str(row[1] if row else ""),
            "website": str(row[3] if row else ""),
            "phone": "",
            "public_email": "",
            "city": str(row[2] if row else ""),
            "state": state,
            "postal_code": "",
            "source_record_id": f"seed:{state}:{key}",
            "verification_status": "Needs review - seeded by Ember",
        })
    return ingest_companies(conn, job_id, source_id, records) if records else {
        "received": 0, "created": 0, "updated": 0, "rejected": 0
    }


def launch(conn, *, state: str = "", company_limit: int = 12, contact_limit: int = 500) -> dict:
    result = launch_hunt(conn, state=state, company_limit=company_limit, contact_limit=contact_limit)
    run_id = int(result.get("search_run_id") or 0)
    resolved_state = str(result.get("state") or state).upper()
    seeds = _build_company_seeds(conn, run_id, resolved_state, company_limit)
    result["broker_domains_selected"] = len(seeds)
    result["broker_seed_domains"] = [_domain(seed.get("source_url", "")) for seed in seeds]
    try:
        crawl = crawl_and_ingest(conn, seeds, state=resolved_state, max_pages=7) if seeds else {
            "attempted": 0, "completed": 0, "failed": 0, "fallbacks": 0, "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [{"company": "", "reason": "No eligible broker-owned domains found"}],
        }
    except Exception as exc:
        crawl = {
            "attempted": len(seeds), "completed": 0, "failed": len(seeds), "fallbacks": 0,
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [{"company": "", "reason": str(exc)[:500]}], "status": "Failed safely",
        }
    warehouse = crawl.get("warehouse") or {}
    if int(warehouse.get("created", 0)) + int(warehouse.get("updated", 0)) == 0:
        fallback = _persist_seeded_companies(conn, result, resolved_state)
        crawl["seed_fallback_warehouse"] = fallback
        crawl["warehouse"] = {
            "received": int(warehouse.get("received", 0)) + int(fallback.get("received", 0)),
            "created": int(warehouse.get("created", 0)) + int(fallback.get("created", 0)),
            "updated": int(warehouse.get("updated", 0)) + int(fallback.get("updated", 0)),
            "rejected": int(warehouse.get("rejected", 0)) + int(fallback.get("rejected", 0)),
        }
        if fallback.get("received", 0):
            crawl["completed"] = max(int(crawl.get("completed", 0)), int(fallback.get("received", 0)))
    result["company_crawl"] = crawl
    result["company_contact_sync"] = sync_company_contacts(conn, state=resolved_state)
    result["message"] = (
        f"Ember completed {resolved_state} mortgage-broker discovery, brokerage prospect creation, "
        "loan-officer team attachment, website crawling, warehouse deduplication, and review preparation."
    )
    return result
