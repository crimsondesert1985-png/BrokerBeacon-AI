"""Official company website resolver and crawler for BrokerBeacon's warehouse.

The crawler resolves an official website from a verified company identity,
honors robots.txt, stays on that domain, uses a small page budget, and stores
public company and employee contact information for review-gated CRM promotion.
"""
from __future__ import annotations

import html
import re
import socket
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime
from html.parser import HTMLParser

from multi_search_provider import search_all
from national_warehouse import (
    canonical_company_key,
    canonical_officer_key,
    create_import_job,
    create_source,
    ingest_companies,
    normalize,
)

USER_AGENT = "BrokerBeacon-Ember/1.0 (+public-business-data; contact=platform-owner)"
PAGE_HINTS = ("contact", "about", "location", "branch", "office", "team", "loan-officer", "staff")
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
NMLS_RE = re.compile(r"(?:NMLS(?:\s*(?:ID|#|No\.?))?\s*[:#-]?\s*)(\d{4,10})", re.I)
ZIP_RE = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
ADDRESS_RE = re.compile(
    r"\b(\d{1,6}\s+[A-Za-z0-9 .'-]{2,80}\s(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Parkway|Pkwy|Highway|Hwy|Way|Circle|Cir))\b",
    re.I,
)
PERSON_RE = re.compile(
    r"\b([A-Z][A-Za-z'\u2019.-]+(?:\s+[A-Z][A-Za-z'\u2019.-]+){1,3})\s*(?:,|-|\||\u2013|\u2014)?\s*"
    r"(?i:(Loan Officer|Mortgage Loan Originator|Branch Manager|Producing Manager|Broker Owner|Mortgage Broker|MLO))\b",
)
DIRECTORY_DOMAINS = {
    "mortgagematchup.com", "nmlsconsumeraccess.org", "zillow.com", "linkedin.com",
    "facebook.com", "instagram.com", "yelp.com", "bbb.org", "mapquest.com",
}
COMPANY_SUFFIXES = {"llc", "inc", "corp", "corporation", "company", "co", "ltd", "mortgage", "mortgages"}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self.title = ""
        self._in_title = False
        self._href = ""
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = attrs.get("href", "")
            self._link_text = []
            if self._href.lower().startswith("mailto:"):
                self.text.append(urllib.parse.unquote(self._href[7:].split("?", 1)[0]))
            elif self._href.lower().startswith("tel:"):
                self.text.append(urllib.parse.unquote(self._href[4:].split("?", 1)[0]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._link_text).strip()))
            self._href = ""
            self._link_text = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        self.text.append(value)
        if self._in_title:
            self.title += (" " if self.title else "") + value
        if self._href:
            self._link_text.append(value)


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if not urllib.parse.urlparse(value).scheme:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def _official_candidate(url: str) -> bool:
    domain = _domain(url)
    return bool(domain) and not any(
        domain == blocked or domain.endswith("." + blocked) for blocked in DIRECTORY_DOMAINS
    )


def resolve_company_website(seed: dict) -> str:
    """Return a plausible official website, preferring a supplied company URL."""
    supplied = _normalize_url(str(seed.get("website") or seed.get("source_url") or ""))
    if supplied and _official_candidate(supplied):
        return supplied
    company = str(seed.get("company") or seed.get("legal_name") or "").strip()
    if not company:
        return ""
    nmls = str(seed.get("nmls") or seed.get("nmls_id") or "").strip()
    city = str(seed.get("city") or "").strip()
    state = str(seed.get("state") or "").strip().upper()
    query = f'"{company}" official website mortgage {city} {state} {("NMLS " + nmls) if nmls else ""}'.strip()
    response = search_all(query, limit_per_provider=10)
    company_tokens = {
        token for token in normalize(company).split()
        if token not in COMPANY_SUFFIXES and len(token) > 2
    }
    ranked = []
    for item in response.get("results", []):
        url = _normalize_url(str(item.get("url") or ""))
        if not url or not _official_candidate(url):
            continue
        haystack = normalize(" ".join((
            str(item.get("title") or ""), str(item.get("description") or ""), _domain(url)
        )))
        matches = sum(1 for token in company_tokens if token in haystack)
        if company_tokens and matches == 0:
            continue
        score = matches * 10 + (20 if nmls and nmls in haystack else 0)
        ranked.append((score, url))
    return max(ranked, default=(0, ""), key=lambda item: item[0])[1]


def _allowed(url: str, cache: dict[str, urllib.robotparser.RobotFileParser]) -> bool:
    parsed = urllib.parse.urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(root + "/robots.txt")
        try:
            parser.read()
        except Exception:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse([])
        cache[root] = parser
    try:
        return cache[root].can_fetch(USER_AGENT, url)
    except Exception:
        return True


def _fetch(url: str, timeout: int = 12, max_bytes: int = 1_500_000) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            return response.geturl(), ""
        raw = response.read(max_bytes)
        charset = response.headers.get_content_charset() or "utf-8"
        return response.geturl(), raw.decode(charset, errors="replace")


def _candidate_pages(base_url: str, parser: PageParser, max_pages: int) -> list[str]:
    base_domain = _domain(base_url)
    ranked: list[tuple[int, str]] = []
    seen = {base_url}
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or _domain(absolute) != base_domain:
            continue
        clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if clean in seen:
            continue
        haystack = (parsed.path + " " + label).lower()
        score = sum(3 for hint in PAGE_HINTS if hint in haystack)
        if score:
            ranked.append((-score, clean))
            seen.add(clean)
    ranked.sort()
    return [url for _, url in ranked[: max(0, max_pages - 1)]]


def _best_company_name(seed_name: str, titles: list[str], domain: str) -> str:
    if seed_name and len(seed_name.strip()) > 2:
        return seed_name.strip()
    for title in titles:
        value = re.split(r"[|â€“â€”]", title)[0].strip()
        if 2 < len(value) < 180:
            return value
    return domain.split(".")[0].replace("-", " ").title()


def _extract_location(text: str, state: str) -> tuple[str, str, str]:
    address_match = ADDRESS_RE.search(text)
    address = address_match.group(1).strip(" ,") if address_match else ""
    postal_match = ZIP_RE.search(text[address_match.start():address_match.start()+220] if address_match else text)
    postal = postal_match.group(1) if postal_match else ""
    city = ""
    if address_match:
        tail = text[address_match.end():address_match.end()+140]
        city_match = re.search(r"[,\s]+([A-Za-z .'-]{2,50}),?\s+" + re.escape(state) + r"\s+\d{5}", tail, re.I)
        if city_match:
            city = city_match.group(1).strip(" ,")
    return address, city, postal


def _extract_officers(text: str, *, city: str, state: str, source_url: str) -> list[dict]:
    """Extract named mortgage professionals and contact details near their names."""
    officers = []
    seen = set()
    for match in PERSON_RE.finditer(text or ""):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        parts = name.split()
        while len(parts) > 2 and parts[0].lower() in {"email", "contact", "meet", "about", "call"}:
            parts.pop(0)
        name = " ".join(parts)
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        after = text[match.end(): min(len(text), match.end() + 300)]
        before = text[max(0, match.start() - 180): match.start()]
        email_match = EMAIL_RE.search(after) or EMAIL_RE.search(before)
        phone_match = PHONE_RE.search(after) or PHONE_RE.search(before)
        nmls_match = NMLS_RE.search(after) or NMLS_RE.search(before)
        officers.append({
            "full_name": name,
            "title": re.sub(r"\s+", " ", match.group(2)).strip(),
            "public_email": email_match.group(0).lower() if email_match else "",
            "phone": phone_match.group(0) if phone_match else "",
            "nmls_id": nmls_match.group(1) if nmls_match else "",
            "city": city,
            "state": state,
            "source_url": source_url,
        })
    return officers[:100]


def _fallback_record(seed: dict, source_url: str, state: str) -> dict | None:
    company = str(seed.get("company") or seed.get("legal_name") or "").strip()
    if not company or not source_url:
        return None
    domain = _domain(source_url)
    return {
        "legal_name": company,
        "nmls_id": str(seed.get("nmls") or seed.get("nmls_id") or ""),
        "website": source_url,
        "phone": str(seed.get("phone") or ""),
        "public_email": str(seed.get("public_email") or ""),
        "address1": "",
        "city": str(seed.get("city") or ""),
        "state": state,
        "postal_code": "",
        "source_record_id": domain,
        "source_url": source_url,
        "source_pages": [source_url],
        "verified_at": datetime.now().isoformat(timespec="seconds"),
        "verification_status": "Search result only - website crawl unavailable",
    }


def crawl_company(seed: dict, *, max_pages: int = 5) -> dict:
    try:
        source_url = resolve_company_website(seed)
    except Exception as exc:
        return {
            "status": "Failed", "reason": f"Website resolution failed: {exc}",
            "record": None, "pages_fetched": 0,
        }
    if not source_url:
        return {"status": "Skipped", "reason": "Missing valid website", "record": None, "pages_fetched": 0}
    state = str(seed.get("state") or "").strip().upper()[:2]
    robots: dict[str, urllib.robotparser.RobotFileParser] = {}
    queue = [source_url]
    visited: set[str] = set()
    texts: list[str] = []
    titles: list[str] = []
    source_pages: list[str] = []
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited or not _allowed(url, robots):
            continue
        visited.add(url)
        try:
            final_url, markup = _fetch(url)
        except (OSError, ValueError, socket.timeout):
            continue
        if not markup:
            continue
        parser = PageParser()
        try:
            parser.feed(markup)
        except Exception:
            pass
        page_text = html.unescape(" ".join(parser.text))
        texts.append(page_text)
        titles.append(parser.title)
        source_pages.append(final_url)
        if len(visited) == 1:
            queue.extend(_candidate_pages(final_url, parser, max_pages))
    if not texts:
        fallback = _fallback_record(seed, source_url, state)
        return {"status": "Fallback" if fallback else "Failed", "reason": "No crawlable HTML pages", "record": fallback, "pages_fetched": 0}
    combined = "\n".join(texts)
    emails = [e for e in dict.fromkeys(EMAIL_RE.findall(combined)) if not e.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    phones = list(dict.fromkeys(PHONE_RE.findall(combined)))
    nmls = list(dict.fromkeys(NMLS_RE.findall(combined)))
    address, city, postal = _extract_location(combined, state)
    domain = _domain(source_pages[0] if source_pages else source_url)
    record = {
        "legal_name": _best_company_name(str(seed.get("company") or seed.get("legal_name") or ""), titles, domain),
        "nmls_id": str(seed.get("nmls") or seed.get("nmls_id") or (nmls[0] if nmls else "")),
        "website": source_pages[0] if source_pages else source_url,
        "phone": phones[0] if phones else str(seed.get("phone") or ""),
        "public_email": emails[0] if emails else str(seed.get("public_email") or ""),
        "address1": address,
        "city": str(seed.get("city") or city),
        "state": state,
        "postal_code": postal,
        "source_record_id": domain,
        "source_url": source_pages[0] if source_pages else source_url,
        "source_pages": source_pages,
        "verified_at": datetime.now().isoformat(timespec="seconds"),
        "verification_status": "Public company website crawled - verify licensing before outreach",
        "officers": _extract_officers(
            combined,
            city=str(seed.get("city") or city),
            state=state,
            source_url=source_pages[0] if source_pages else source_url,
        ),
    }
    return {"status": "Completed", "reason": "", "record": record, "pages_fetched": len(source_pages)}


def crawl_and_ingest(conn, seeds: list[dict], *, state: str, max_pages: int = 5) -> dict:
    """Resolve and crawl company sites, then persist company and employee records."""
    source_id = create_source(
        conn,
        "Ember public company websites",
        "Public website crawler",
        "Public business pages; robots.txt honored; review-gated company and employee data",
        "",
    )
    job_id = create_import_job(conn, source_id, state)
    records = []
    completed = failed = pages = fallbacks = officers_created = officers_updated = 0
    failures = []
    for seed in seeds:
        result = crawl_company(seed, max_pages=max_pages)
        pages += int(result.get("pages_fetched") or 0)
        if result.get("record"):
            records.append(result["record"])
            completed += 1
            if result.get("status") == "Fallback":
                fallbacks += 1
        else:
            failed += 1
            failures.append({"company": seed.get("company", ""), "reason": result.get("reason", "")})
    counts = ingest_companies(conn, job_id, source_id, records) if records else {
        "received": 0, "created": 0, "updated": 0, "rejected": 0
    }
    for record in records:
        company_row = conn.execute(
            "select id from warehouse_companies where canonical_key=?",
            (canonical_company_key(record),),
        ).fetchone()
        if not company_row:
            continue
        company_id = int(company_row[0])
        for officer in record.get("officers", []):
            name = str(officer.get("full_name") or "").strip()
            if not name:
                continue
            key = canonical_officer_key(officer, company_id)
            existing = conn.execute(
                "select id from warehouse_officers where canonical_key=?", (key,)
            ).fetchone()
            stamp = datetime.now().isoformat(timespec="seconds")
            nmls_id = str(officer.get("nmls_id") or "")
            title = str(officer.get("title") or "")
            phone = str(officer.get("phone") or "")
            public_email = str(officer.get("public_email") or "")
            city = str(officer.get("city") or "")
            officer_state = str(officer.get("state") or state).upper()
            verification = "Public company website - verify identity and licensing"
            if existing:
                conn.execute(
                    """update warehouse_officers set company_id=?,full_name=?,normalized_name=?,
                       nmls_id=case when ?<>'' then ? else nmls_id end,title=?,
                       phone=case when ?<>'' then ? else phone end,
                       public_email=case when ?<>'' then ? else public_email end,
                       city=?,state=?,verification_status=?,last_seen_at=?,updated_at=? where id=?""",
                    (company_id, name, normalize(name), nmls_id, nmls_id, title,
                     phone, phone, public_email, public_email, city, officer_state,
                     verification, stamp, stamp, int(existing[0])),
                )
                officers_updated += 1
            else:
                conn.execute(
                    """insert into warehouse_officers(
                       company_id,canonical_key,full_name,normalized_name,nmls_id,title,phone,public_email,
                       city,state,verification_status,first_seen_at,last_seen_at,created_at,updated_at)
                       values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (company_id, key, name, normalize(name), nmls_id, title, phone, public_email,
                     city, officer_state, verification, stamp, stamp, stamp, stamp),
                )
                officers_created += 1
    conn.execute(
        "update warehouse_import_jobs set officers_created=?,updated_at=? where id=?",
        (officers_created, datetime.now().isoformat(timespec="seconds"), job_id),
    )
    conn.commit()
    if not records:
        stamp = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "update warehouse_import_jobs set status='Completed',records_received=0,finished_at=?,updated_at=? where id=?",
            (stamp, stamp, job_id),
        )
        conn.commit()
    return {
        "job_id": job_id,
        "attempted": len(seeds),
        "completed": completed,
        "failed": failed,
        "fallbacks": fallbacks,
        "pages_fetched": pages,
        "officers_created": officers_created,
        "officers_updated": officers_updated,
        "warehouse": counts,
        "failures": failures[:20],
    }

