"""Scalable company-website enrichment for public-search discoveries.

Pipeline:
1. Claim pending public-search results.
2. Resolve the company website.
3. Respect robots.txt and conservative per-domain limits.
4. Crawl a small set of likely contact/team pages.
5. Extract public business contact details with source provenance.
6. Stage everything for review; never add records directly to outreach.
"""
from __future__ import annotations

import html
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import defaultdict
from datetime import datetime, timedelta

NOW = lambda: datetime.now().isoformat(timespec="seconds")
USER_AGENT = "BrokerBeaconBot/1.0 (+public-business-data; review-gated)"
MAX_PAGE_BYTES = 1_500_000
DEFAULT_PATHS = ("/", "/contact", "/about", "/team", "/loan-officers", "/our-team", "/branches")

SCHEMA = """
create table if not exists website_enrichment_jobs(
    id integer primary key,
    state text default '',
    status text not null default 'Queued',
    batch_size integer not null default 100,
    claimed_count integer not null default 0,
    processed_count integer not null default 0,
    companies_found integer not null default 0,
    contacts_found integer not null default 0,
    pages_fetched integer not null default 0,
    pages_blocked integer not null default 0,
    failures integer not null default 0,
    created_at text not null,
    started_at text default '',
    finished_at text default '',
    error text default ''
);
create table if not exists website_enrichment_queue(
    id integer primary key,
    search_result_id integer not null unique,
    state text default '',
    domain text default '',
    status text not null default 'Queued',
    attempts integer not null default 0,
    next_attempt_at text default '',
    locked_at text default '',
    job_id integer,
    error text default '',
    created_at text not null,
    updated_at text not null,
    foreign key(search_result_id) references public_search_results(id),
    foreign key(job_id) references website_enrichment_jobs(id)
);
create table if not exists website_pages(
    id integer primary key,
    search_result_id integer not null,
    url text not null,
    domain text not null,
    http_status integer not null default 0,
    content_type text default '',
    title text default '',
    fetched_at text not null,
    unique(search_result_id,url)
);
create table if not exists discovered_contacts(
    id integer primary key,
    search_result_id integer not null,
    company_name text default '',
    person_name text default '',
    role text default '',
    phone text default '',
    public_email text default '',
    city text default '',
    state text default '',
    nmls_id text default '',
    source_url text not null,
    source_domain text not null,
    confidence integer not null default 50,
    review_status text not null default 'Pending review',
    created_at text not null,
    unique(search_result_id,source_url,person_name,public_email,phone)
);
create index if not exists idx_enrichment_queue_status on website_enrichment_queue(status,next_attempt_at,id);
create index if not exists idx_discovered_contacts_review on discovered_contacts(review_status,state,id desc);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _same_domain(url: str, domain: str) -> bool:
    host = _domain(url)
    return host == domain or host.endswith("." + domain)


def _clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _title(raw: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    return _clean_text(match.group(1))[:240] if match else ""


def _emails(text: str) -> list[str]:
    values = re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text or "", re.I)
    blocked = {"example.com", "sentry.io", "wixpress.com"}
    result = []
    for value in values:
        value = value.lower().strip(".,;:()[]<>")
        if value.split("@")[-1] not in blocked and value not in result:
            result.append(value)
    return result[:50]


def _phones(text: str) -> list[str]:
    values = re.findall(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", text or "")
    result = []
    for value in values:
        number = re.sub(r"\D+", "", value)[-10:]
        if len(number) == 10 and number not in result:
            result.append(number)
    return result[:50]


def _nmls(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bNMLS(?:\s*ID)?\s*[:#-]?\s*(\d{4,12})\b", text or "", re.I)))[:50]


def _person_candidates(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'’-]+){1,2})\s*(?:,|-|\|)?\s*"
        r"(Loan Officer|Mortgage Loan Originator|Branch Manager|Producing Manager|Broker Owner|Mortgage Broker|MLO)\b",
        re.I,
    )
    result = []
    for name, role in pattern.findall(text or ""):
        key = (name.strip(), role.strip())
        if key not in result:
            result.append(key)
    return result[:100]


def enqueue_search_results(conn: sqlite3.Connection, state: str = "", limit: int = 5000) -> int:
    initialize(conn)
    state = (state or "").strip().upper()
    rows = conn.execute(
        """select id,state,source_url,source_domain from public_search_results
           where review_status='Pending review' and (?='' or state=?)
           order by id limit ?""",
        (state, state, min(max(int(limit), 1), 50000)),
    ).fetchall()
    now = NOW()
    created = 0
    for row in rows:
        cur = conn.execute(
            """insert or ignore into website_enrichment_queue
               (search_result_id,state,domain,created_at,updated_at) values(?,?,?,?,?)""",
            (row["id"], row["state"], row["source_domain"] or _domain(row["source_url"]), now, now),
        )
        created += int(cur.rowcount > 0)
    conn.commit()
    return created


def _robots_allows(base_url: str, target_url: str) -> bool:
    parsed = urllib.parse.urlparse(base_url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(USER_AGENT, target_url)
    except Exception:
        return True


def _fetch(url: str) -> tuple[int, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(request, timeout=15) as response:
        content_type = response.headers.get("Content-Type", "")[:160]
        if "text/html" not in content_type.lower():
            return int(response.status), content_type, ""
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            body = body[:MAX_PAGE_BYTES]
        return int(response.status), content_type, body.decode("utf-8", errors="ignore")


def _candidate_pages(source_url: str) -> list[str]:
    parsed = urllib.parse.urlparse(source_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    base = f"{parsed.scheme}://{parsed.netloc}"
    paths = [parsed.path or "/", *DEFAULT_PATHS]
    urls = []
    for path in paths:
        url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        if url not in urls:
            urls.append(url)
    return urls


def _store_contacts(conn: sqlite3.Connection, search_result: sqlite3.Row, page_url: str, text: str) -> int:
    company = (search_result["company_name"] or search_result["title"] or "").strip()
    domain = _domain(page_url)
    emails, phones, nmls_ids = _emails(text), _phones(text), _nmls(text)
    people = _person_candidates(text)
    now = NOW()
    created = 0
    if people:
        for index, (name, role) in enumerate(people):
            email = emails[index] if index < len(emails) else ""
            phone = phones[index] if index < len(phones) else ""
            nmls_id = nmls_ids[index] if index < len(nmls_ids) else ""
            cur = conn.execute(
                """insert or ignore into discovered_contacts
                   (search_result_id,company_name,person_name,role,phone,public_email,state,nmls_id,
                    source_url,source_domain,confidence,created_at)
                   values(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (search_result["id"], company, name, role, phone, email, search_result["state"], nmls_id,
                 page_url, domain, 75 if email or phone or nmls_id else 60, now),
            )
            created += int(cur.rowcount > 0)
    elif emails or phones or nmls_ids:
        cur = conn.execute(
            """insert or ignore into discovered_contacts
               (search_result_id,company_name,phone,public_email,state,nmls_id,source_url,source_domain,confidence,created_at)
               values(?,?,?,?,?,?,?,?,?,?)""",
            (search_result["id"], company, phones[0] if phones else "", emails[0] if emails else "",
             search_result["state"], nmls_ids[0] if nmls_ids else "", page_url, domain, 65, now),
        )
        created += int(cur.rowcount > 0)
    return created


def run_batch(conn: sqlite3.Connection, *, state: str = "", batch_size: int = 100,
              per_domain_limit: int = 3, delay_seconds: float = 0.4) -> dict:
    initialize(conn)
    batch_size = min(max(int(batch_size), 1), 1000)
    stale = (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
    conn.execute(
        """update website_enrichment_queue set status='Queued',locked_at='',job_id=null,
           error='Recovered stale lock',updated_at=? where status='Running' and locked_at<?""",
        (NOW(), stale),
    )
    now = NOW()
    job_id = int(conn.execute(
        "insert into website_enrichment_jobs(state,status,batch_size,created_at,started_at) values(?,'Running',?,?,?)",
        ((state or "").upper(), batch_size, now, now),
    ).lastrowid)
    rows = conn.execute(
        """select q.id queue_id,r.* from website_enrichment_queue q
           join public_search_results r on r.id=q.search_result_id
           where q.status='Queued' and (q.next_attempt_at='' or q.next_attempt_at<=?)
           and (?='' or q.state=?) order by q.id limit ?""",
        (now, (state or "").upper(), (state or "").upper(), batch_size),
    ).fetchall()
    claimed = []
    for row in rows:
        changed = conn.execute(
            """update website_enrichment_queue set status='Running',locked_at=?,job_id=?,attempts=attempts+1,updated_at=?
               where id=? and status='Queued'""",
            (now, job_id, now, row["queue_id"]),
        ).rowcount
        if changed:
            claimed.append(row)
    conn.execute("update website_enrichment_jobs set claimed_count=? where id=?", (len(claimed), job_id))
    conn.commit()

    stats = defaultdict(int)
    domain_hits = defaultdict(int)
    for row in claimed:
        try:
            source_url = row["source_url"]
            domain = _domain(source_url)
            if not domain or domain_hits[domain] >= per_domain_limit:
                conn.execute("update website_enrichment_queue set status='Queued',locked_at='',job_id=null,updated_at=? where id=?", (NOW(), row["queue_id"]))
                continue
            pages = _candidate_pages(source_url)
            for page_url in pages:
                if domain_hits[domain] >= per_domain_limit:
                    break
                if not _same_domain(page_url, domain):
                    continue
                if not _robots_allows(source_url, page_url):
                    stats["pages_blocked"] += 1
                    continue
                status, content_type, raw = _fetch(page_url)
                domain_hits[domain] += 1
                stats["pages_fetched"] += 1
                conn.execute(
                    """insert or ignore into website_pages(search_result_id,url,domain,http_status,content_type,title,fetched_at)
                       values(?,?,?,?,?,?,?)""",
                    (row["id"], page_url, domain, status, content_type, _title(raw), NOW()),
                )
                if raw:
                    stats["contacts_found"] += _store_contacts(conn, row, page_url, _clean_text(raw))
                conn.commit()
                if delay_seconds:
                    time.sleep(delay_seconds)
            conn.execute(
                "update website_enrichment_queue set status='Completed',locked_at='',error='',updated_at=? where id=?",
                (NOW(), row["queue_id"]),
            )
            stats["processed"] += 1
        except Exception as exc:
            attempts = conn.execute("select attempts from website_enrichment_queue where id=?", (row["queue_id"],)).fetchone()[0]
            status = "Failed" if attempts >= 3 else "Queued"
            next_attempt = "" if status == "Failed" else (datetime.now() + timedelta(minutes=5 * attempts)).isoformat(timespec="seconds")
            conn.execute(
                """update website_enrichment_queue set status=?,next_attempt_at=?,locked_at='',error=?,updated_at=? where id=?""",
                (status, next_attempt, str(exc)[:500], NOW(), row["queue_id"]),
            )
            stats["failures"] += 1
        conn.commit()

    finished = NOW()
    conn.execute(
        """update website_enrichment_jobs set status='Completed',processed_count=?,contacts_found=?,
           pages_fetched=?,pages_blocked=?,failures=?,finished_at=? where id=?""",
        (stats["processed"], stats["contacts_found"], stats["pages_fetched"],
         stats["pages_blocked"], stats["failures"], finished, job_id),
    )
    conn.commit()
    return {"job_id": job_id, "claimed": len(claimed), **dict(stats)}


def dashboard(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    queue = {row[0]: row[1] for row in conn.execute("select status,count(*) from website_enrichment_queue group by status")}
    totals = conn.execute(
        "select count(*),count(distinct source_domain),sum(case when public_email<>'' then 1 else 0 end),sum(case when phone<>'' then 1 else 0 end) from discovered_contacts"
    ).fetchone()
    jobs = [dict(row) for row in conn.execute("select * from website_enrichment_jobs order by id desc limit 20")]
    return {
        "queue": queue,
        "contacts": int(totals[0] or 0),
        "domains": int(totals[1] or 0),
        "with_email": int(totals[2] or 0),
        "with_phone": int(totals[3] or 0),
        "recent_jobs": jobs,
    }
