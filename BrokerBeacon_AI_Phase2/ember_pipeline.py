"""Full Ember discovery pipeline: hunt, crawl, warehouse, review."""
from __future__ import annotations

import re
import urllib.parse

from broker_company_contacts import is_excluded_retail_lender, sync_company_contacts
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


def _build_company_seeds(conn, run_id: int, state: str, company_limit: int) -> list[dict]:
    """Select recent accepted broker-owned domains, not regulator seed URLs.

    The hunt's returned run can be the national-index seed run. That run often
    contains NMLS/regulator URLs, while the immediately preceding public-search
    run contains the actual brokerage websites. Search the current run first,
    then recent accepted results for the same state and deduplicate by domain.
    """
    state = (state or "").strip().upper()[:2]
    rows = conn.execute(
        """select company_name,person_name,title,snippet,nmls_id,city,state,
                  source_url,source_domain,candidate_type,run_id,id
           from public_search_results
           where review_status='Pending review'
             and trim(coalesce(source_url,''))<>''
             and (run_id=? or state=?)
           order by case when run_id=? then 0 else 1 end,
                    case when candidate_type='Company' then 0 else 1 end,
                    id desc
           limit 750""",
        (run_id, state, run_id),
    ).fetchall()
    blocked_domains = {
        "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "freddiemac.com",
        "fanniemae.com", "linkedin.com", "facebook.com", "instagram.com", "youtube.com",
        "bankrate.com", "nerdwallet.com", "investopedia.com", "forbes.com", "wikipedia.org",
    }
    seen: set[str] = set()
    seeds: list[dict] = []
    for raw in rows:
        row = dict(raw)
        url = str(row.get("source_url") or "").strip()
        domain = _domain(url)
        if not domain or domain in blocked_domains or any(domain.endswith("." + blocked) for blocked in blocked_domains):
            continue
        if is_excluded_retail_lender(
            str(row.get("company_name") or row.get("title") or ""),
            url,
            str(row.get("snippet") or ""),
        ):
            continue
        if domain in seen:
            continue
        company = _company_from_row(row)
        if not company:
            continue
        seen.add(domain)
        seeds.append({
            "company": company,
            "nmls": str(row.get("nmls_id") or ""),
            "city": str(row.get("city") or ""),
            "state": state or str(row.get("state") or ""),
            "source_url": url,
        })
        if len(seeds) >= max(1, min(int(company_limit), 25)):
            break
    return seeds


def launch(conn, *, state: str = "", company_limit: int = 12, contact_limit: int = 500) -> dict:
    """Run broker discovery, build brokerage prospects, and attach public loan-officer teams."""
    result = launch_hunt(
        conn,
        state=state,
        company_limit=company_limit,
        contact_limit=contact_limit,
    )
    run_id = int(result.get("search_run_id") or 0)
    resolved_state = str(result.get("state") or state).upper()
    seeds = _build_company_seeds(conn, run_id, resolved_state, company_limit) if run_id else []
    result["broker_domains_selected"] = len(seeds)
    try:
        result["company_crawl"] = crawl_and_ingest(
            conn,
            seeds,
            state=resolved_state,
            max_pages=7,
        ) if seeds else {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "fallbacks": 0,
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [],
        }
    except Exception as exc:
        result["company_crawl"] = {
            "attempted": len(seeds),
            "completed": 0,
            "failed": len(seeds),
            "fallbacks": 0,
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [{"company": "", "reason": str(exc)[:500]}],
            "status": "Failed safely",
        }
    result["company_contact_sync"] = sync_company_contacts(conn, state=resolved_state)
    result["message"] = (
        f"Ember completed {resolved_state} mortgage-broker discovery, brokerage prospect creation, "
        "loan-officer team attachment, website crawling, warehouse deduplication, and review preparation."
    )
    return result
