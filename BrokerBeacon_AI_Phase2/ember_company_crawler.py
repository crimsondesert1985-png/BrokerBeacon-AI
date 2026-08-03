"""Public company website crawler for Ember's national BrokerBeacon warehouse.

The crawler intentionally collects company-level business information only. It
honors robots.txt, stays on the source domain, uses a small page budget, and
stores source-aware records in the national warehouse.
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

from national_warehouse import create_import_job, create_source, ingest_companies

USER_AGENT = "BrokerBeacon-Ember/1.0 (+public-business-data; contact=platform-owner)"
PAGE_HINTS = ("contact", "about", "location", "branch", "office", "team", "loan-officer", "staff")
PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
NMLS_RE = re.compile(r"(?:NMLS(?:\s*(?:ID|#|No\.?))?\s*[:#-]?\s*)(\d{4,10})", re.I)
ZIP_RE = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
ADDRESS_RE = re.compile(
    r"\b(\d{1,6}\s+[A-Za-z0-9 .'-]{2,80}\s(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Parkway|Pkwy|Highway|Hwy|Way|Circle|Cir)\b[^\n]{0,100})",
    re.I,
)


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
        value = re.split(r"[|–—]", title)[0].strip()
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
    source_url = _normalize_url(str(seed.get("source_url") or seed.get("website") or ""))
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
    }
    return {"status": "Completed", "reason": "", "record": record, "pages_fetched": len(source_pages)}


def crawl_and_ingest(conn, seeds: list[dict], *, state: str, max_pages: int = 5) -> dict:
    """Crawl seed companies and persist deduplicated company records."""
    source_id = create_source(
        conn,
        "Ember public company websites",
        "Public website crawler",
        "Public business pages; robots.txt honored; company-level data only",
        "",
    )
    job_id = create_import_job(conn, source_id, state)
    records = []
    completed = failed = pages = fallbacks = 0
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
        "warehouse": counts,
        "failures": failures[:20],
    }
