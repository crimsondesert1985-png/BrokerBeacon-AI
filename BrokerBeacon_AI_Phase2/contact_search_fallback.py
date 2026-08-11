"""Official-site search-snippet fallback for contact enrichment.

When Render cannot fetch a company's site directly, use configured public search
providers to inspect snippets from that same official domain. Only phone/email
values actually present in those official-domain search results are returned.
"""
from __future__ import annotations

import re
import urllib.parse

from ember_company_crawler import crawl_company as direct_crawl, resolve_company_website
from multi_search_provider import search_all

PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")


def resilient_contact_crawl(seed: dict, *, max_pages: int = 3) -> dict:
    result = direct_crawl(seed, max_pages=max_pages)
    record = result.get("record") or {}
    if result.get("status") == "Completed" and (record.get("phone") or record.get("public_email") or record.get("officers")):
        return result

    try:
        official = str(record.get("website") or resolve_company_website(seed) or "").strip()
    except Exception:
        official = str(record.get("website") or "").strip()
    domain = _domain(official)
    if not domain:
        return result

    company = str(seed.get("company") or seed.get("legal_name") or "").strip()
    queries = [
        f'site:{domain} "{company}" contact phone email',
        f'site:{domain} "{company}" mortgage contact',
    ]
    phone = email = source_url = ""
    for query in queries:
        try:
            response = search_all(query, limit_per_provider=10)
        except Exception:
            continue
        for item in response.get("results") or []:
            url = str(item.get("url") or "")
            if _domain(url) != domain:
                continue
            text = " ".join((str(item.get("title") or ""), str(item.get("description") or "")))
            if not phone:
                match = PHONE_RE.search(text)
                if match:
                    phone = match.group(0).strip()
                    source_url = url
            if not email:
                match = EMAIL_RE.search(text)
                if match:
                    candidate = match.group(0).lower().rstrip(".,;:")
                    if not candidate.endswith((".png", ".jpg", ".jpeg", ".webp")):
                        email = candidate
                        source_url = source_url or url
            if phone or email:
                break
        if phone or email:
            break
    if not phone and not email:
        return result

    fallback = dict(record)
    fallback.update({
        "legal_name": fallback.get("legal_name") or company,
        "nmls_id": fallback.get("nmls_id") or str(seed.get("nmls") or seed.get("nmls_id") or ""),
        "website": official,
        "phone": phone or fallback.get("phone", ""),
        "public_email": email or fallback.get("public_email", ""),
        "city": fallback.get("city") or str(seed.get("city") or ""),
        "state": fallback.get("state") or str(seed.get("state") or "").upper(),
        "source_url": source_url or official,
        "source_pages": [source_url or official],
        "officers": fallback.get("officers") or [],
        "verification_status": "Official-site search snippet contact - verify before outreach",
    })
    return {
        "status": "Completed",
        "reason": "Recovered public contact channel from official-domain search snippet",
        "record": fallback,
        "pages_fetched": int(result.get("pages_fetched") or 0),
    }


def install_contact_search_fallback(app=None) -> None:
    try:
        import contact_enrichment_worker
        contact_enrichment_worker.crawl_company = resilient_contact_crawl
        if app is not None:
            app.logger.warning("CONTACT_ENRICH official-domain snippet fallback enabled")
    except Exception:
        if app is not None:
            app.logger.exception("CONTACT_ENRICH snippet fallback failed safely")


__all__ = ["install_contact_search_fallback", "resilient_contact_crawl"]
