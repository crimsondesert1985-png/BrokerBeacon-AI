"""Public browser-search discovery connector for Sprint 37.

Uses an approved search API rather than scraping search-result pages directly.
Every result preserves its source URL and remains review-gated before CRM use.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Iterable

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
    review_status text not null default 'Pending review',
    created_at text not null,
    unique(run_id,source_url)
);
create index if not exists idx_public_search_runs_state on public_search_runs(state,status,id desc);
create index if not exists idx_public_search_results_review on public_search_results(review_status,state,id desc);
"""

SEARCH_TEMPLATES = (
    'mortgage broker {state} NMLS',
    'mortgage company {state} loan officers',
    'wholesale mortgage broker {state} contact',
    'site:nmlsconsumeraccess.org mortgage {state}',
)


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def build_queries(state: str, metro: str = "") -> list[str]:
    state = (state or "").strip().upper()
    metro = (metro or "").strip()
    if len(state) != 2 or not state.isalpha():
        raise ValueError("A valid two-letter state is required")
    suffix = f" {metro}" if metro else ""
    return [template.format(state=state) + suffix for template in SEARCH_TEMPLATES]


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


def classify_result(title: str, snippet: str, url: str) -> dict:
    combined = " ".join([title or "", snippet or "", url or ""])
    lower = combined.lower()
    candidate_type = "Loan officer" if any(term in lower for term in ("loan officer", "mortgage loan originator", "mlo")) else "Company"
    title_clean = re.sub(r"\s*[-|·].*$", "", title or "").strip()
    return {
        "candidate_type": candidate_type,
        "company_name": "" if candidate_type == "Loan officer" else title_clean,
        "person_name": title_clean if candidate_type == "Loan officer" else "",
        "nmls_id": _extract_nmls(combined),
        "phone": _extract_phone(combined),
        "public_email": _extract_email(combined),
    }


def search_provider(query: str, *, count: int = 10) -> list[dict]:
    """Query an approved search API.

    Supported provider: Brave Search API. Configure BRAVE_SEARCH_API_KEY.
    The function intentionally does not scrape Google/Bing result HTML.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not configured")
    params = urllib.parse.urlencode({"q": query, "count": min(max(count, 1), 20), "safesearch": "moderate"})
    req = urllib.request.Request("https://api.search.brave.com/res/v1/web/search?" + params)
    req.add_header("Accept", "application/json")
    req.add_header("X-Subscription-Token", api_key)
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return list((payload.get("web") or {}).get("results") or [])


def run_public_search(conn: sqlite3.Connection, *, connector_id: int | None,
                      state: str, metro: str = "", results_per_query: int = 10,
                      delay_seconds: float = 0.25) -> dict:
    initialize(conn)
    queries = build_queries(state, metro)
    now = NOW()
    cur = conn.execute(
        "insert into public_search_runs(connector_id,state,status,created_at,started_at) values(?,?,'Running',?,?)",
        (connector_id, state.upper(), now, now),
    )
    run_id = int(cur.lastrowid)
    conn.commit()
    accepted = rejected = total = 0
    try:
        for query in queries:
            results = search_provider(query, count=results_per_query)
            for rank, item in enumerate(results, start=1):
                url = str(item.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    rejected += 1
                    continue
                title = str(item.get("title") or "")
                snippet = str(item.get("description") or "")
                parsed = classify_result(title, snippet, url)
                conn.execute(
                    """insert or ignore into public_search_results(
                       run_id,query_text,result_rank,title,snippet,source_url,source_domain,
                       candidate_type,company_name,person_name,state,nmls_id,phone,public_email,created_at
                       ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, query, rank, title, snippet, url, _domain(url),
                     parsed["candidate_type"], parsed["company_name"], parsed["person_name"],
                     state.upper(), parsed["nmls_id"], parsed["phone"], parsed["public_email"], NOW()),
                )
                total += 1
                accepted += 1
            conn.commit()
            if delay_seconds:
                time.sleep(delay_seconds)
        finished = NOW()
        conn.execute(
            """update public_search_runs set status='Completed',query_count=?,result_count=?,
               accepted_count=?,rejected_count=?,finished_at=? where id=?""",
            (len(queries), total, accepted, rejected, finished, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "queries": len(queries), "results": total, "accepted": accepted, "rejected": rejected}
    except Exception as exc:
        finished = NOW()
        conn.execute(
            "update public_search_runs set status='Failed',error=?,finished_at=? where id=?",
            (str(exc)[:500], finished, run_id),
        )
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
