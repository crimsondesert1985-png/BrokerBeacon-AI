"""Ingest Mortgage Matchup company/profile records into BrokerBeacon.

Only canonical mortgagematchup.com Company/Profile URLs are eligible. Direct page
content is preferred. When Cloudflare blocks Render, Ember falls back to the title
and excerpt supplied by the public search index for that exact canonical page.
"""
from __future__ import annotations

import html
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

from national_warehouse import create_import_job, create_source, digits, ingest_companies, normalize

BASE = "https://mortgagematchup.com"
DOMAIN = "mortgagematchup.com"
UA = "Mozilla/5.0 (compatible; BrokerBeacon-Ember/3.0; public directory research)"
NOW = lambda: datetime.now().isoformat(timespec="seconds")


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


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read(3_000_000).decode("utf-8", "ignore")


def _plain(raw: str) -> str:
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _heading(raw: str) -> str:
    for tag in ("h1", "h2", "h3", "title"):
        match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", raw, re.I | re.S)
        if match:
            value = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))).strip()
            value = re.sub(r"\s*[-|]\s*Mortgage Matchup.*$", "", value, flags=re.I).strip()
            if value:
                return value
    return ""


def _phone_email(text: str) -> tuple[str, str]:
    phone_match = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
    return (digits(phone_match.group(0))[-10:] if phone_match else "", email_match.group(0).lower() if email_match else "")


def _address(text: str, state_hint: str = "") -> tuple[str, str, str, str]:
    match = re.search(
        r"(\d{1,6}\s+[A-Za-z0-9 .#'\-/]+?)\s+([A-Za-z .'-]+?),?\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b",
        text,
    )
    if not match:
        return "", "", state_hint.upper(), ""
    values = [re.sub(r"\s+", " ", value).strip(" ,") for value in match.groups()]
    return values[0], values[1], values[2], values[3]


def _website(text: str) -> str:
    match = re.search(r"\b(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?", text, re.I)
    if not match:
        return ""
    value = match.group(0).rstrip(".,)")
    host = urllib.parse.urlparse(value if "://" in value else "https://" + value).netloc.lower().removeprefix("www.")
    if host in {DOMAIN, "nmlsconsumeraccess.org"}:
        return ""
    return value if "://" in value else "https://" + value


def _clean_title(title: str) -> str:
    return re.sub(r"\s*[-|]\s*Mortgage Matchup.*$", "", title or "", flags=re.I).strip()


def _indexed_company(row: dict, state_hint: str = "") -> dict:
    title = _clean_title(str(row.get("title") or ""))
    snippet = re.sub(r"\s+", " ", str(row.get("snippet") or "")).strip()
    nmls_match = re.search(r"NMLS\s*#?:?\s*(\d{4,12})", snippet, re.I)
    nmls_id = digits(str(row.get("nmls_id") or (nmls_match.group(1) if nmls_match else "")))
    address, city, state, postal = _address(snippet, state_hint)
    phone, email = _phone_email(snippet)
    officers = []
    roster = snippet
    if "Mortgage Originators" in roster:
        roster = roster.split("Mortgage Originators", 1)[1]
    if "Contact Information" in roster:
        roster = roster.split("Contact Information", 1)[0]
    for match in re.finditer(r"([A-Z][A-Za-z' .-]{2,70}?)\s+NMLS\s*#\s*(\d{4,12})", roster):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" ,-.")
        if title and name.lower().startswith(title.lower()):
            name = name[len(title):].strip(" ,-.")
        if name and 1 < len(name.split()) <= 6:
            officers.append({"officer_name": name, "officer_nmls": match.group(2), "officer_phone": "", "officer_email": ""})
    return {
        "company_url": str(row.get("source_url") or ""), "company_name": title, "company_nmls": nmls_id,
        "company_phone": phone, "company_email": email, "company_website": _website(snippet),
        "address1": address, "city": city, "state": state or state_hint.upper(), "postal_code": postal,
        "officers": officers,
    }


def _indexed_profile(row: dict, state_hint: str = "") -> dict:
    title = _clean_title(str(row.get("title") or ""))
    snippet = re.sub(r"\s+", " ", str(row.get("snippet") or "")).strip()
    ids = [digits(value) for value in re.findall(r"NMLS\s*#?:?\s*(\d{4,12})", snippet, re.I)]
    officer_nmls = digits(str(row.get("nmls_id") or (ids[0] if ids else "")))
    relation = re.search(r"NMLS\s*#?:?\s*\d{4,12}\s*[|·-]\s*([^|]{2,100}?)(?=\s+(?:Contact|About|Licensed In|$))", snippet, re.I)
    company_name = re.sub(r"\s+", " ", relation.group(1)).strip(" |-·") if relation else ""
    company_nmls = next((value for value in ids if value != officer_nmls), "")
    phone, email = _phone_email(snippet)
    address, city, state, postal = _address(snippet, state_hint)
    return {
        "profile_url": str(row.get("source_url") or ""), "officer_name": title, "officer_nmls": officer_nmls,
        "officer_phone": phone, "officer_email": email, "company_name": company_name,
        "company_nmls": company_nmls, "company_phone": phone, "company_email": "",
        "company_website": _website(snippet), "address1": address, "city": city,
        "state": state or state_hint.upper(), "postal_code": postal,
    }


def _company_id(conn: sqlite3.Connection, nmls_id: str, name: str, state: str) -> int:
    row = conn.execute("select id from warehouse_companies where nmls_id=? order by id desc limit 1", (nmls_id,)).fetchone() if nmls_id else None
    if not row and name:
        row = conn.execute("select id from warehouse_companies where normalized_name=? and upper(state)=? order by id desc limit 1", (normalize(name), state.upper())).fetchone()
    if not row:
        raise RuntimeError("Mortgage Matchup company could not be resolved")
    return int(row[0])


def _upsert_officer(conn: sqlite3.Connection, company_id: int, officer: dict, state: str, city: str) -> bool:
    name = str(officer.get("officer_name") or "").strip()
    nmls_id = digits(str(officer.get("officer_nmls") or ""))
    if not name or not nmls_id:
        return False
    key = f"nmls:{nmls_id}"
    existing = conn.execute("select id from warehouse_officers where canonical_key=?", (key,)).fetchone()
    now = NOW()
    if existing:
        conn.execute("""update warehouse_officers set company_id=?,full_name=?,normalized_name=?,nmls_id=?,title='Mortgage Loan Originator',phone=?,public_email=?,city=?,state=?,verification_status='Mortgage Matchup indexed profile - verify in NMLS',last_seen_at=?,updated_at=? where id=?""",
                     (company_id,name,normalize(name),nmls_id,officer.get("officer_phone", ""),officer.get("officer_email", ""),city,state,now,now,int(existing[0])))
        return False
    conn.execute("""insert into warehouse_officers(company_id,canonical_key,full_name,normalized_name,nmls_id,title,phone,public_email,city,state,verification_status,first_seen_at,last_seen_at,created_at,updated_at) values(?,?,?,?,?,'Mortgage Loan Originator',?,?,?,?,?,?,?,?,?)""",
                 (company_id,key,name,normalize(name),nmls_id,officer.get("officer_phone", ""),officer.get("officer_email", ""),city,state,"Mortgage Matchup indexed profile - verify in NMLS",now,now,now,now))
    return True


def _result_rows(conn: sqlite3.Connection, run_id: int, limit: int) -> list[dict]:
    params: list[object] = [DOMAIN]
    clause = ""
    if run_id > 0:
        clause = "and run_id=?"
        params.append(run_id)
    params.append(max(1, min(int(limit), 2000)))
    rows = conn.execute(f"""select id,source_url,title,snippet,state,nmls_id,candidate_type from public_search_results where source_domain=? {clause} and (source_url like '%/Profile/%' or source_url like '%/Company/%') and review_status<>'Rejected' order by id desc limit ?""", tuple(params)).fetchall()
    output=[]; seen=set()
    for row in rows:
        item=dict(row); url=_canonical(str(item.get("source_url") or ""))
        if url and url.lower() not in seen:
            item["source_url"]=url; output.append(item); seen.add(url.lower())
    return output


def ingest_matchup_results(conn: sqlite3.Connection, run_id: int = 0, state: str = "", limit: int = 100) -> dict:
    source_id=create_source(conn,"Mortgage Matchup","Public verified broker directory","Canonical company/profile URLs and public search-index excerpts; verify licensing in NMLS",BASE)
    job_id=create_import_job(conn,source_id,state)
    counts={"urls_found":0,"profile_pages":0,"company_pages":0,"indexed_fallbacks":0,"companies_created":0,"companies_updated":0,"officers_created":0,"officers_updated":0,"rejected":0,"failures":[]}
    rows=_result_rows(conn,int(run_id or 0),max(int(limit)*4,100)); counts["urls_found"]=len(rows)
    for row in rows:
        url=row["source_url"]; kind="Company" if "/Company/" in url else "Profile"
        try:
            parsed=None
            try:
                raw=_fetch(url)
                text=_plain(raw)
                # Keep direct parsing deliberately conservative; indexed fallback is authoritative when blocked.
                if kind=="Company":
                    direct={"title":_heading(raw),"snippet":text,"source_url":url,"state":row.get("state", ""),"nmls_id":row.get("nmls_id", "")}
                    parsed=_indexed_company(direct,state)
                else:
                    direct={"title":_heading(raw),"snippet":text,"source_url":url,"state":row.get("state", ""),"nmls_id":row.get("nmls_id", "")}
                    parsed=_indexed_profile(direct,state)
            except Exception:
                counts["indexed_fallbacks"]+=1
                parsed=_indexed_company(row,state) if kind=="Company" else _indexed_profile(row,state)
            if not parsed.get("company_name") or not parsed.get("company_nmls"):
                counts["rejected"]+=1
                continue
            company_record={"legal_name":parsed["company_name"],"nmls_id":parsed["company_nmls"],"website":parsed.get("company_website", ""),"phone":parsed.get("company_phone", ""),"public_email":parsed.get("company_email", ""),"city":parsed.get("city", ""),"state":parsed.get("state", state).upper(),"postal_code":parsed.get("postal_code", ""),"source_record_id":url,"source_url":url,"verification_status":"Mortgage Matchup indexed listing - verify in NMLS"}
            result=ingest_companies(conn,job_id,source_id,[company_record]); counts["companies_created"]+=result["created"]; counts["companies_updated"]+=result["updated"]
            company_id=_company_id(conn,company_record["nmls_id"],company_record["legal_name"],company_record["state"])
            officers=list(parsed.get("officers", []))
            if kind=="Profile": officers.append(parsed)
            for officer in officers:
                created=_upsert_officer(conn,company_id,officer,company_record["state"],company_record["city"])
                counts["officers_created" if created else "officers_updated"]+=1
            counts["company_pages" if kind=="Company" else "profile_pages"]+=1
            conn.commit()
        except Exception as exc:
            counts["failures"].append({"url":url,"error":str(exc)[:240]})
    return counts
