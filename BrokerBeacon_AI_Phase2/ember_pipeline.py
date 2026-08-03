"""Full Ember discovery pipeline: hunt, crawl, warehouse, review."""
from __future__ import annotations

import re
import urllib.parse

from ember_company_crawler import crawl_and_ingest
from ember_hunt import launch as launch_hunt


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _company_from_row(row: dict) -> str:
    value = str(row.get("company_name") or "").strip()
    if value:
        return value
    title = str(row.get("title") or row.get("person_name") or "").strip()
    title = re.sub(r"\s*[-|·].*$", "", title).strip()
    return title or _domain(str(row.get("source_url") or "")).split(".")[0].replace("-", " ").title()


def _build_company_seeds(conn, run_id: int, company_limit: int) -> list[dict]:
    """Use every accepted broker-domain result, not only rows classified as Company."""
    rows = conn.execute(
        """select company_name,person_name,title,nmls_id,city,state,source_url,source_domain,candidate_type
           from public_search_results
           where run_id=? and review_status='Pending review'
             and trim(coalesce(source_url,''))<>''
           order by case when candidate_type='Company' then 0 else 1 end,result_rank,id""",
        (run_id,),
    ).fetchall()
    blocked_domains = {
        "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "freddiemac.com",
        "fanniemae.com", "linkedin.com", "facebook.com", "instagram.com", "youtube.com",
    }
    seen: set[str] = set()
    seeds: list[dict] = []
    for raw in rows:
        row = dict(raw)
        domain = _domain(str(row.get("source_url") or ""))
        if not domain or domain in blocked_domains or any(domain.endswith("." + blocked) for blocked in blocked_domains):
            continue
        if domain in seen:
            continue
        seen.add(domain)
        seeds.append({
            "company": _company_from_row(row),
            "nmls": str(row.get("nmls_id") or ""),
            "city": str(row.get("city") or ""),
            "state": str(row.get("state") or ""),
            "source_url": str(row.get("source_url") or ""),
        })
        if len(seeds) >= max(1, min(int(company_limit), 25)):
            break
    return seeds


def launch(conn, *, state: str = "", company_limit: int = 12, contact_limit: int = 500) -> dict:
    """Run the guarded broker hunt, then crawl and warehouse valid broker domains."""
    result = launch_hunt(
        conn,
        state=state,
        company_limit=company_limit,
        contact_limit=contact_limit,
    )
    run_id = int(result.get("search_run_id") or 0)
    seeds = _build_company_seeds(conn, run_id, company_limit) if run_id else []
    result["broker_domains_selected"] = len(seeds)
    try:
        result["company_crawl"] = crawl_and_ingest(
            conn,
            seeds,
            state=str(result.get("state") or state).upper(),
            max_pages=7,
        ) if seeds else {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [],
        }
    except Exception as exc:
        result["company_crawl"] = {
            "attempted": len(seeds),
            "completed": 0,
            "failed": len(seeds),
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [{"company": "", "reason": str(exc)[:500]}],
            "status": "Failed safely",
        }
    result["message"] = (
        f"Ember completed {result.get('state','')} mortgage-broker discovery, public website crawling, "
        "warehouse deduplication, contact extraction, and review preparation."
    )
    return result
