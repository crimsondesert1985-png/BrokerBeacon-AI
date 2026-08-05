"""Ingest public Mortgage Matchup profiles into BrokerBeacon's warehouse.

Mortgage Matchup exposes loan-originator profile pages that include the associated
brokerage and NMLS identifiers. Ember uses those public pages as the authoritative
source and does not promote generic search-result titles.
"""
from __future__ import annotations

import html
import re
import sqlite3
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime

from national_warehouse import create_import_job, create_source, digits, ingest_companies, normalize

BASE = "https://mortgagematchup.com"
DOMAIN = "mortgagematchup.com"
UA = "BrokerBeacon-Ember/2.0 (+public mortgage broker directory indexing)"
NOW = lambda: datetime.now().isoformat(timespec="seconds")
_ROBOTS_ALLOWED: bool | None = None


def _allowed(url: str) -> bool:
    global _ROBOTS_ALLOWED
    if _ROBOTS_ALLOWED is None:
        try:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(BASE + "/robots.txt")
            parser.read()
            _ROBOTS_ALLOWED = parser.can_fetch(UA, BASE + "/Profile/example")
        except Exception:
            _ROBOTS_ALLOWED = False
    return bool(_ROBOTS_ALLOWED and url.startswith(BASE + "/"))


def _fetch(url: str) -> str:
    if not _allowed(url):
        raise RuntimeError("Mortgage Matchup robots policy did not allow this public page")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"Mortgage Matchup returned HTTP {response.status}")
        return response.read(3_000_000).decode("utf-8", "ignore")


def _text(raw: str) -> str:
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _heading(raw: str) -> str:
    for level in range(1, 7):
        match = re.search(rf"<h{level}\b[^>]*>(.*?)</h{level}>", raw, re.I | re.S)
        if match:
            value = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))).strip()
            if value and value.lower() not in {"contact", "about", "client reviews", "specializations"}:
                return value
    title = re.search(r"<title\b[^>]*>(.*?)</title>", raw, re.I | re.S)
    return re.sub(r"\s*[-|].*$", "", html.unescape(title.group(1))).strip() if title else ""


def _canonical(url: str, kind: str = "") -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = re.sub(r"/+", "/", parsed.path).rstrip("/")
        pattern = rf"/{kind}/[^/?#]+" if kind else r"/(?:Company|Profile)/[^/?#]+"
        if host != DOMAIN or not re.fullmatch(pattern, path, re.I):
            return ""
        segment, slug = path.strip("/").split("/", 1)
        return f"{BASE}/{segment.title()}/{slug}"
    except Exception:
        return ""


def _contact_values(text: str) -> tuple[str, str]:
    phone_match = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    phone = digits(phone_match.group(0))[-10:] if phone_match else ""
    email = email_match.group(0).lower() if email_match else ""
    return phone, email


def _external_website(raw: str, page_url: str) -> str:
    excluded = {
        DOMAIN, "maps.google.com", "linkedin.com", "facebook.com", "instagram.com",
        "youtube.com", "tiktok.com", "nmlsconsumeraccess.org", "uwm.com",
    }
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", raw, re.I):
        full = urllib.parse.urljoin(page_url, html.unescape(href))
        host = urllib.parse.urlparse(full).netloc.lower().removeprefix("www.")
        if host and host not in excluded and not host.endswith(".google.com"):
            return full
    return ""


def _address(text: str, state_hint: str = "") -> tuple[str, str, str, str]:
    patterns = [
        r"(\d{1,6}\s+[A-Za-z0-9 .#'\-/]+?)\s+(?:NMLS\s*\d{4,12}\s+)?([A-Za-z .'-]+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b",
        r"(\d{1,6}\s+[A-Za-z0-9 .#'\-/]+?),?\s+([A-Za-z .'-]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            address, city, state, postal = [re.sub(r"\s+", " ", value).strip(" ,") for value in match.groups()]
            return address, city, state, postal
    return "", "", state_hint.upper(), ""


def parse_profile_page(url: str, raw: str, state_hint: str = "") -> dict:
    text = _text(raw)
    name = _heading(raw)
    relation = re.search(r"NMLS\s*:?#?\s*(\d{4,12})\s*[|·-]\s*([^|]{2,120}?)(?=\s+(?:Contact|About|Client Reviews|Specializations|Licensed In)\b|$)", text, re.I)
    officer_nmls = digits(relation.group(1)) if relation else ""
    company_name = re.sub(r"\s+", " ", relation.group(2)).strip(" |-·") if relation else ""
    if not company_name:
        company_match = re.search(r"\bCompany\s+(.{2,120}?)(?=\s+(?:About|Client Reviews|Specializations|Licensed In|Send Email|Call)\b|$)", text, re.I)
        company_name = re.sub(r"\s+", " ", company_match.group(1)).strip(" |-·") if company_match else ""

    nmls_values = []
    for value in re.findall(r"\bNMLS\s*:?#?\s*(\d{4,12})\b", text, re.I):
        value = digits(value)
        if value and value not in nmls_values:
            nmls_values.append(value)
    company_nmls = next((value for value in nmls_values if value != officer_nmls), "")

    phone, email = _contact_values(text)
    address, city, state, postal = _address(text, state_hint)
    licensed = re.search(r"Licensed In\s+([A-Za-z ,]+?)(?=\s+(?:Send Email|Call|Email|©|$))", text, re.I)
    if not state and licensed:
        state = state_hint.upper()

    return {
        "profile_url": _canonical(url, "Profile"),
        "officer_name": name,
        "officer_nmls": officer_nmls,
        "officer_phone": phone,
        "officer_email": email,
        "company_name": company_name,
        "company_nmls": company_nmls,
        "company_phone": phone,
        "company_email": "",
        "company_website": _external_website(raw, url),
        "address1": address,
        "city": city,
        "state": state or state_hint.upper(),
        "postal_code": postal,
    }


def parse_company_page(url: str, raw: str, state_hint: str = "") -> dict:
    text = _text(raw)
    name = _heading(raw)
    nmls_match = re.search(r"\bNMLS\s*:?#?\s*(\d{4,12})\b", text, re.I)
    phone, email = _contact_values(text)
    address, city, state, postal = _address(text, state_hint)
    profiles = []
    for href in re.findall(r"href=[\"']([^\"']*/Profile/[^\"'?#]+)[\"']", raw, re.I):
        profile = _canonical(urllib.parse.urljoin(url, html.unescape(href)), "Profile")
        if profile and profile not in profiles:
            profiles.append(profile)
    return {
        "company_url": _canonical(url, "Company"),
        "company_name": name,
        "company_nmls": digits(nmls_match.group(1)) if nmls_match else "",
        "company_phone": phone,
        "company_email": email,
        "company_website": _external_website(raw, url),
        "address1": address,
        "city": city,
        "state": state or state_hint.upper(),
        "postal_code": postal,
        "profile_urls": profiles,
    }


def _company_id(conn: sqlite3.Connection, nmls_id: str, name: str, state: str) -> int:
    row = None
    if nmls_id:
        row = conn.execute("select id from warehouse_companies where nmls_id=? order by id desc limit 1", (nmls_id,)).fetchone()
    if not row and name:
        row = conn.execute(
            "select id from warehouse_companies where normalized_name=? and upper(state)=? order by id desc limit 1",
            (normalize(name), state.upper()),
        ).fetchone()
    if not row:
        raise RuntimeError("Mortgage Matchup company could not be resolved after ingestion")
    return int(row[0])


def _upsert_officer(conn: sqlite3.Connection, company_id: int, profile: dict) -> tuple[int, bool]:
    name = str(profile.get("officer_name") or "").strip()
    nmls_id = digits(str(profile.get("officer_nmls") or ""))
    if not name or not nmls_id:
        return 0, False
    key = f"nmls:{nmls_id}"
    row = conn.execute("select id from warehouse_officers where canonical_key=?", (key,)).fetchone()
    now = NOW()
    values = {
        "company_id": company_id,
        "canonical_key": key,
        "full_name": name,
        "normalized_name": normalize(name),
        "nmls_id": nmls_id,
        "title": "Mortgage Loan Originator",
        "phone": profile.get("officer_phone", ""),
        "public_email": profile.get("officer_email", ""),
        "city": profile.get("city", ""),
        "state": profile.get("state", ""),
        "verification_status": "Mortgage Matchup profile - verify in NMLS",
        "last_seen_at": now,
        "updated_at": now,
    }
    if row:
        officer_id = int(row[0])
        conn.execute(
            """update warehouse_officers set company_id=:company_id,full_name=:full_name,
               normalized_name=:normalized_name,nmls_id=:nmls_id,title=:title,phone=:phone,
               public_email=:public_email,city=:city,state=:state,
               verification_status=:verification_status,last_seen_at=:last_seen_at,updated_at=:updated_at
               where id=:id""",
            {**values, "id": officer_id},
        )
        return officer_id, False
    cursor = conn.execute(
        """insert into warehouse_officers(company_id,canonical_key,full_name,normalized_name,nmls_id,
           title,phone,public_email,city,state,verification_status,first_seen_at,last_seen_at,created_at,updated_at)
           values(:company_id,:canonical_key,:full_name,:normalized_name,:nmls_id,:title,:phone,
           :public_email,:city,:state,:verification_status,:now,:last_seen_at,:now,:updated_at)""",
        {**values, "now": now},
    )
    return int(cursor.lastrowid), True


def _result_urls(conn: sqlite3.Connection, run_id: int, limit: int) -> list[str]:
    params: list[object] = [DOMAIN]
    run_clause = ""
    if run_id > 0:
        run_clause = "and run_id=?"
        params.append(run_id)
    params.append(max(1, min(int(limit), 500)))
    rows = conn.execute(
        f"""select distinct source_url from public_search_results
            where source_domain=? {run_clause}
              and (source_url like '%/Profile/%' or source_url like '%/Company/%')
              and review_status<>'Rejected'
            order by id desc limit ?""",
        tuple(params),
    ).fetchall()
    urls = []
    for row in rows:
        url = _canonical(str(row[0] or ""))
        if url and url not in urls:
            urls.append(url)
    return urls


def ingest_matchup_results(conn: sqlite3.Connection, run_id: int = 0, state: str = "", limit: int = 100) -> dict:
    source_id = create_source(
        conn,
        "Mortgage Matchup",
        "Public verified broker directory",
        "Public profile/company pages; search indexing permitted; verify licensing in NMLS",
        BASE,
    )
    job_id = create_import_job(conn, source_id, state)
    counts = {
        "urls_found": 0,
        "profile_pages": 0,
        "company_pages": 0,
        "companies_created": 0,
        "companies_updated": 0,
        "officers_created": 0,
        "officers_updated": 0,
        "rejected": 0,
        "failures": [],
    }
    urls = _result_urls(conn, int(run_id or 0), max(int(limit) * 4, 100))
    counts["urls_found"] = len(urls)

    def ingest_profile(url: str, profile: dict) -> None:
        if not profile.get("company_name") or not profile.get("company_nmls"):
            raise RuntimeError("Profile did not expose a brokerage name and company NMLS")
        company_record = {
            "legal_name": profile["company_name"],
            "nmls_id": profile["company_nmls"],
            "website": profile.get("company_website", ""),
            "phone": profile.get("company_phone", ""),
            "public_email": profile.get("company_email", ""),
            "address1": profile.get("address1", ""),
            "city": profile.get("city", ""),
            "state": profile.get("state", state).upper(),
            "postal_code": profile.get("postal_code", ""),
            "source_record_id": url,
            "source_url": url,
            "verification_status": "Mortgage Matchup listing - verify in NMLS",
        }
        result = ingest_companies(conn, job_id, source_id, [company_record])
        counts["companies_created"] += result["created"]
        counts["companies_updated"] += result["updated"]
        company_id = _company_id(conn, company_record["nmls_id"], company_record["legal_name"], company_record["state"])
        _, created = _upsert_officer(conn, company_id, profile)
        counts["officers_created" if created else "officers_updated"] += 1
        conn.commit()

    for url in urls:
        try:
            if "/Profile/" in url:
                profile = parse_profile_page(url, _fetch(url), state)
                ingest_profile(url, profile)
                counts["profile_pages"] += 1
            else:
                company = parse_company_page(url, _fetch(url), state)
                if not company.get("company_name") or not company.get("company_nmls"):
                    raise RuntimeError("Company page did not expose company name and NMLS")
                record = {
                    "legal_name": company["company_name"],
                    "nmls_id": company["company_nmls"],
                    "website": company.get("company_website", ""),
                    "phone": company.get("company_phone", ""),
                    "public_email": company.get("company_email", ""),
                    "address1": company.get("address1", ""),
                    "city": company.get("city", ""),
                    "state": company.get("state", state).upper(),
                    "postal_code": company.get("postal_code", ""),
                    "source_record_id": url,
                    "source_url": url,
                    "verification_status": "Mortgage Matchup listing - verify in NMLS",
                }
                result = ingest_companies(conn, job_id, source_id, [record])
                counts["companies_created"] += result["created"]
                counts["companies_updated"] += result["updated"]
                counts["company_pages"] += 1
                for profile_url in company.get("profile_urls", [])[:100]:
                    profile = parse_profile_page(profile_url, _fetch(profile_url), record["state"])
                    if not profile.get("company_name"):
                        profile["company_name"] = record["legal_name"]
                    if not profile.get("company_nmls"):
                        profile["company_nmls"] = record["nmls_id"]
                    ingest_profile(profile_url, profile)
                    counts["profile_pages"] += 1
        except Exception as exc:
            counts["rejected"] += 1
            counts["failures"].append({"url": url, "error": str(exc)[:240]})
    return counts
