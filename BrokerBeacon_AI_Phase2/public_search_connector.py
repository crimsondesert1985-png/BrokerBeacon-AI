"""Review-gated public search discovery using every configured provider."""
from __future__ import annotations

import re
import sqlite3
import time
import urllib.parse
from datetime import datetime

from multi_search_provider import configured_providers, search_all

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists public_search_runs(
    id integer primary key,
    connector_id integer,
    state text not null,
    query_count integer not null default 0,
    result_count integer not null default 0,
    accepted_count integer not null default 0,
    rejected_count integer not null default 0,
    status text not null default 'Queued',
    error text default '',
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    foreign key(connector_id) references state_connectors(id)
);
create table if not exists public_search_results(
    id integer primary key,
    run_id integer not null,
    query_text text not null,
    result_rank integer not null,
    title text default '',
    snippet text default '',
    source_url text not null,
    source_domain text default '',
    candidate_type text not null default 'Unknown',
    company_name text default '',
    person_name text default '',
    city text default '',
    state text default '',
    nmls_id text default '',
    phone text default '',
    public_email text default '',
    provider_name text default '',
    review_status text not null default 'Pending review',
    created_at text not null,
    unique(run_id,source_url)
);
create index if not exists idx_public_search_runs_state on public_search_runs(state,status,id desc);
create index if not exists idx_public_search_results_review on public_search_results(review_status,state,id desc);
"""

STATE_NAMES = {
    'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'
}

SEARCH_TEMPLATES = (
    'independent mortgage broker {state_name} NMLS contact -wholesale -TPO',
    'mortgage brokerage in {state_name} loan officers -wholesale lender',
    'licensed mortgage broker company {state_name} NMLS',
    'mortgage broker directory {state_name}',
    'mortgage loan officer team {state_name} brokerage',
    'mortgage broker owner {state_name} contact',
    'site:nmlsconsumeraccess.org mortgage broker {state_name}',
)

BROKER_SIGNALS = (
    'mortgage broker','mortgage brokerage','broker owner','broker-owner',
    'independent mortgage','loan officer','mortgage loan originator','nmls',
    'mortgage licensee','mortgage company','home loan','mortgage advisor',
)

NON_BROKER_SIGNALS = (
    'wholesale mortgage lender','wholesale lender','wholesale lending',
    'wholesale mortgages available','what is wholesale mortgage',
    'become an approved broker','broker portal','third-party originator',
    'tpo lending','correspondent lending','our broker partners',
)

EDITORIAL_DOMAINS = {
    'bankrate.com','investopedia.com','nerdwallet.com','forbes.com','wikipedia.org',
}


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {row[1] for row in conn.execute("pragma table_info(public_search_results)")}
    if "provider_name" not in columns:
        conn.execute("alter table public_search_results add column provider_name text default ''")
    conn.commit()


def build_queries(state: str, metro: str = "") -> list[str]:
    state = (state or "").strip().upper()
    metro = (metro or "").strip()
    if state not in STATE_NAMES:
        raise ValueError("A valid two-letter state is required")
    values = {'state': state, 'state_name': STATE_NAMES[state]}
    suffix = f" {metro}" if metro else ""
    return [template.format(**values) + suffix for template in SEARCH_TEMPLATES]


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _extract_nmls(text: str) -> str:
    match = re.search(r"\bNMLS(?:\s*ID)?\s*[:#-]?\s*(\d{4,12})\b", text or "", re.I)
    return match.group(1) if match else ""


def _extract_email(text: str) -> str:
    match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text or "", re.I)
    return match.group(0).lower() if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", text or "")
    return re.sub(r"\D+", "", match.group(0))[-10:] if match else ""


def is_broker_candidate(title: str, snippet: str, url: str) -> bool:
    combined = " ".join((title or "", snippet or "", url or "")).lower()
    domain = _domain(url)
    if domain in EDITORIAL_DOMAINS:
        return False
    has_broker = any(term in combined for term in BROKER_SIGNALS)
    has_non_broker = any(term in combined for term in NON_BROKER_SIGNALS)
    official = (
        'nmlsconsumeraccess.org' in domain or domain.endswith('.gov')
        or 'search mortgage licensees' in combined or 'mortgage licensee' in combined
    )
    explicit_broker = any(term in combined for term in ('mortgage broker','mortgage brokerage','loan officer','mortgage loan originator'))
    if has_non_broker and not explicit_broker:
        return False
    return has_broker or official


def classify_result(title: str, snippet: str, url: str) -> dict:
    combined = " ".join([title or "", snippet or "", url or ""])
    lower = combined.lower()
    person_page = any(term in lower for term in ('loan officer','mortgage loan originator','mortgage advisor',' mlo '))
    title_clean = re.sub(r"\s*[-|·].*$", "", title or "").strip()
    domain_name = _domain(url).split('.')[0].replace('-', ' ').title()
    # Keep useful LO/team pages eligible as company-domain seeds. Website
    # enrichment extracts the individual people later with source evidence.
    return {
        "candidate_type": "Company",
        "company_name": title_clean or domain_name,
        "person_name": title_clean if person_page else "",
        "nmls_id": _extract_nmls(combined),
        "phone": _extract_phone(combined),
        "public_email": _extract_email(combined),
    }


def search_provider(query: str, *, count: int = 20) -> dict:
    providers = configured_providers()
    if not providers:
        raise RuntimeError("No public search provider is configured")
    response = search_all(query, limit_per_provider=min(max(int(count), 1), 20), providers=providers)
    completed = [name for name, stats in response.get("provider_stats", {}).items() if stats.get("status") == "Completed"]
    if not completed:
        errors = [stats.get("error", "") for stats in response.get("provider_stats", {}).values() if stats.get("error")]
        raise RuntimeError("; ".join(errors) or "All configured public search providers failed")
    return response


def run_public_search(conn: sqlite3.Connection, *, connector_id: int | None,
                      state: str, metro: str = "", results_per_query: int = 20,
                      delay_seconds: float = 0.25) -> dict:
    initialize(conn)
    queries = build_queries(state, metro)
    now = NOW()
    run_id = int(conn.execute(
        "insert into public_search_runs(connector_id,state,status,created_at,started_at) values(?,?,'Running',?,?)",
        (connector_id, state.upper(), now, now),
    ).lastrowid)
    conn.commit()
    accepted = rejected = total = 0
    used_providers: set[str] = set()
    provider_stats: dict[str, dict] = {}
    seen_domains: set[str] = set()
    try:
        for query in queries:
            response = search_provider(query, count=results_per_query)
            provider_stats.update(response.get("provider_stats", {}))
            for rank, item in enumerate(response.get("results", []), start=1):
                url = str(item.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    rejected += 1
                    continue
                title = str(item.get("title") or "")
                snippet = str(item.get("description") or "")
                if not is_broker_candidate(title, snippet, url):
                    rejected += 1
                    continue
                domain = _domain(url)
                canonical_key = domain + urllib.parse.urlparse(url).path.rstrip('/').lower()
                if canonical_key in seen_domains:
                    continue
                seen_domains.add(canonical_key)
                providers = [str(p.get("provider") or "") for p in item.get("providers", []) if p.get("provider")]
                used_providers.update(providers)
                parsed = classify_result(title, snippet, url)
                conn.execute(
                    """insert or ignore into public_search_results(
                       run_id,query_text,result_rank,title,snippet,source_url,source_domain,
                       candidate_type,company_name,person_name,state,nmls_id,phone,public_email,provider_name,created_at
                       ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, query, rank, title, snippet, url, domain,
                     parsed["candidate_type"], parsed["company_name"], parsed["person_name"],
                     state.upper(), parsed["nmls_id"], parsed["phone"], parsed["public_email"], ",".join(providers), NOW()),
                )
                total += 1
                accepted += 1
            conn.commit()
            if delay_seconds:
                time.sleep(delay_seconds)
        conn.execute(
            """update public_search_runs set status='Completed',query_count=?,result_count=?,
               accepted_count=?,rejected_count=?,finished_at=? where id=?""",
            (len(queries), total, accepted, rejected, NOW(), run_id),
        )
        conn.commit()
        return {"run_id": run_id, "queries": len(queries), "results": total, "accepted": accepted,
                "rejected": rejected, "providers": sorted(used_providers), "provider_stats": provider_stats}
    except Exception as exc:
        conn.execute("update public_search_runs set status='Failed',error=?,finished_at=? where id=?",
                     (str(exc)[:500], NOW(), run_id))
        conn.commit()
        raise


def pending_results(conn: sqlite3.Connection, state: str = "", limit: int = 200) -> list[dict]:
    initialize(conn)
    state = (state or "").strip().upper()
    rows = conn.execute(
        """select * from public_search_results where review_status='Pending review'
           and (?='' or state=?) order by id desc limit ?""",
        (state, state, min(max(int(limit), 1), 1000)),
    ).fetchall()
    return [dict(row) for row in rows]
