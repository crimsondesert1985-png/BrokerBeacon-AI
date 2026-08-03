"""Consolidate Ember discoveries into brokerage-level prospects with attached teams."""
from __future__ import annotations

import re
import sqlite3
import urllib.parse
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

EXCLUDED_RETAIL_DOMAINS = {
    "bankofamerica.com", "wellsfargo.com", "chase.com", "jpmorganchase.com",
    "usbank.com", "truist.com", "pnc.com", "citi.com", "citibank.com",
    "capitalone.com", "regions.com", "fifththird.com", "huntington.com",
    "key.com", "td.com", "tdbank.com", "citizensbank.com", "flagstar.com",
    "bmo.com", "santanderbank.com", "navyfederal.org", "penfed.org",
}

EXCLUDED_RETAIL_NAMES = {
    "bank of america", "wells fargo", "jpmorgan chase", "jp morgan chase",
    "chase bank", "u.s. bank", "us bank", "truist bank", "pnc bank",
    "citibank", "capital one", "regions bank", "fifth third bank",
    "huntington bank", "keybank", "td bank", "citizens bank", "bmo bank",
    "santander bank", "navy federal credit union", "penfed credit union",
}


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_excluded_retail_lender(name: str = "", url: str = "", text: str = "") -> bool:
    domain = domain_of(url)
    if domain in EXCLUDED_RETAIL_DOMAINS or any(domain.endswith("." + item) for item in EXCLUDED_RETAIL_DOMAINS):
        return True
    combined = " ".join((name or "", text or "")).lower()
    if any(item in combined for item in EXCLUDED_RETAIL_NAMES):
        return True
    retail_markers = ("member fdic", "national bank", "credit union", "personal checking", "banking products")
    broker_markers = ("mortgage broker", "mortgage brokerage", "broker owner", "independent mortgage broker")
    return any(marker in combined for marker in retail_markers) and not any(marker in combined for marker in broker_markers)


def _clean_company_name(value: str, domain: str) -> str:
    value = re.sub(r"\s*[-|·].*$", "", value or "").strip()
    person_page = re.search(r"\b(loan officer|mortgage loan originator|mortgage advisor|branch manager|nmls)\b", value, re.I)
    if value and not person_page and 2 < len(value) < 160:
        return value
    return domain.split(".")[0].replace("-", " ").title()


def reject_excluded_retail_lenders(conn: sqlite3.Connection, state: str = "") -> int:
    state = (state or "").strip().upper()
    rows = conn.execute(
        """select id,company_name,title,snippet,source_url,state from public_search_results
           where review_status<>'Rejected' and (?='' or state=?)""",
        (state, state),
    ).fetchall()
    rejected = 0
    for row in rows:
        if not is_excluded_retail_lender(row["company_name"], row["source_url"], f"{row['title']} {row['snippet']}"):
            continue
        conn.execute("update public_search_results set review_status='Rejected' where id=?", (row["id"],))
        conn.execute("update discovered_contacts set review_status='Rejected' where search_result_id=?", (row["id"],))
        rejected += 1
    conn.commit()
    return rejected


def sync_company_contacts(conn: sqlite3.Connection, state: str = "") -> dict:
    """Create one top-level brokerage prospect per domain; people remain attached team rows."""
    state = (state or "").strip().upper()
    rejected = reject_excluded_retail_lenders(conn, state)
    rows = conn.execute(
        """select p.id,p.company_name,p.title,p.snippet,p.source_url,p.source_domain,p.state,
                  p.city,p.nmls_id,p.phone,p.public_email,p.created_at
           from public_search_results p
           where p.review_status='Pending review' and trim(coalesce(p.source_url,''))<>''
             and (?='' or p.state=?)
           order by p.id desc""",
        (state, state),
    ).fetchall()
    created = updated = 0
    seen: set[tuple[str, str]] = set()
    for row in rows:
        domain = str(row["source_domain"] or domain_of(row["source_url"])).lower()
        if not domain or is_excluded_retail_lender(row["company_name"], row["source_url"], f"{row['title']} {row['snippet']}"):
            continue
        key = (str(row["state"] or "").upper(), domain)
        if key in seen:
            continue
        seen.add(key)
        company = _clean_company_name(str(row["company_name"] or row["title"] or ""), domain)
        team_contact = conn.execute(
            """select phone,public_email,nmls_id from discovered_contacts
               where source_domain=? and state=? and trim(coalesce(person_name,''))<>''
               order by confidence desc,id desc limit 1""",
            (domain, key[0]),
        ).fetchone()
        phone = str(row["phone"] or (team_contact["phone"] if team_contact else "") or "")
        email = str(row["public_email"] or (team_contact["public_email"] if team_contact else "") or "")
        nmls = str(row["nmls_id"] or (team_contact["nmls_id"] if team_contact else "") or "")
        existing = conn.execute(
            """select id from discovered_contacts where state=? and source_domain=?
               and trim(coalesce(person_name,''))='' and role='Mortgage Brokerage' limit 1""",
            (key[0], domain),
        ).fetchone()
        if existing:
            conn.execute(
                """update discovered_contacts set company_name=?,phone=case when trim(phone)='' then ? else phone end,
                   public_email=case when trim(public_email)='' then ? else public_email end,
                   nmls_id=case when trim(nmls_id)='' then ? else nmls_id end,
                   source_url=?,confidence=max(confidence,80) where id=?""",
                (company, phone, email, nmls, row["source_url"], existing["id"]),
            )
            updated += 1
        else:
            conn.execute(
                """insert or ignore into discovered_contacts
                   (search_result_id,company_name,person_name,role,phone,public_email,city,state,nmls_id,
                    source_url,source_domain,confidence,review_status,created_at)
                   values(?,?,'','Mortgage Brokerage',?,?,?,?,?,?,?,80,'Pending review',?)""",
                (row["id"], company, phone, email, str(row["city"] or ""), key[0], nmls,
                 row["source_url"], domain, NOW()),
            )
            created += 1
    conn.commit()
    return {"company_contacts_created": created, "company_contacts_updated": updated, "retail_lenders_rejected": rejected}


def company_team(conn: sqlite3.Connection, company_name: str, source_domain: str = "") -> list[dict]:
    if source_domain:
        rows = conn.execute(
            """select * from discovered_contacts where source_domain=?
               and trim(coalesce(person_name,''))<>'' and review_status<>'Rejected'
               order by confidence desc,id desc""",
            (source_domain,),
        ).fetchall()
    else:
        rows = conn.execute(
            """select * from discovered_contacts where company_name=?
               and trim(coalesce(person_name,''))<>'' and review_status<>'Rejected'
               order by confidence desc,id desc""",
            (company_name,),
        ).fetchall()
    return [dict(row) for row in rows]
