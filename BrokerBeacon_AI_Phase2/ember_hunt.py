"""Bounded, review-gated Ember hunt using BrokerBeacon's existing public website index."""
from __future__ import annotations

import sqlite3
import urllib.parse
from datetime import datetime

from ai_intelligence import initialize as init_ai, process_batch as process_ai_batch
from public_search_connector import initialize as init_public
from website_enrichment import initialize as init_enrichment, enqueue_search_results, run_batch

NOW = lambda: datetime.now().isoformat(timespec="seconds")


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _valid_public_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse((value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _seed_rows(conn: sqlite3.Connection, state: str, limit: int) -> list[sqlite3.Row]:
    """Read existing public company websites without assuming every legacy column exists."""
    columns = {row[1] for row in conn.execute("pragma table_info(national_broker_index)")}
    required = {"company", "state", "source_url"}
    if not required.issubset(columns):
        return []
    fields = ["company", "state", "source_url"]
    for optional in ("city", "nmls", "source_name"):
        if optional in columns:
            fields.append(optional)
    query = f"select {','.join(fields)} from national_broker_index where upper(state)=? and trim(coalesce(source_url,''))<>'' order by id limit ?"
    return conn.execute(query, (state, limit)).fetchall()


def launch(conn: sqlite3.Connection, *, state: str = "NC", company_limit: int = 10,
           contact_limit: int = 200) -> dict:
    state = (state or "NC").strip().upper()
    if len(state) != 2 or not state.isalpha():
        raise ValueError("A valid two-letter state is required")
    company_limit = min(max(int(company_limit), 1), 25)
    contact_limit = min(max(int(contact_limit), 1), 500)

    init_public(conn)
    init_enrichment(conn)
    init_ai(conn)

    now = NOW()
    run_id = int(conn.execute(
        "insert into public_search_runs(state,status,created_at,started_at) values(?,'Running',?,?)",
        (state, now, now),
    ).lastrowid)
    seeded = skipped = 0
    seen_domains: set[str] = set()

    for rank, row in enumerate(_seed_rows(conn, state, company_limit * 4), start=1):
        url = str(row["source_url"] or "").strip()
        if not _valid_public_url(url):
            skipped += 1
            continue
        domain = _domain(url)
        if not domain or domain in seen_domains:
            skipped += 1
            continue
        seen_domains.add(domain)
        company = str(row["company"] or "").strip()
        city = str(row["city"] or "").strip() if "city" in row.keys() else ""
        nmls = str(row["nmls"] or "").strip() if "nmls" in row.keys() else ""
        source_name = str(row["source_name"] or "Existing Broker Index").strip() if "source_name" in row.keys() else "Existing Broker Index"
        conn.execute(
            """insert or ignore into public_search_results(
               run_id,query_text,result_rank,title,snippet,source_url,source_domain,
               candidate_type,company_name,city,state,nmls_id,review_status,created_at)
               values(?,?,?,?,?,?,?,?,?,?,?,?, 'Pending review',?)""",
            (run_id, "existing-index-seed", rank, company,
             f"Seeded from {source_name}; public website queued for review-gated enrichment.",
             url, domain, "Company", company, city, state, nmls, now),
        )
        seeded += 1
        if seeded >= company_limit:
            break

    finished = NOW()
    conn.execute(
        """update public_search_runs set status='Completed',query_count=1,result_count=?,
           accepted_count=?,rejected_count=?,finished_at=? where id=?""",
        (seeded + skipped, seeded, skipped, finished, run_id),
    )
    conn.commit()

    enqueued = enqueue_search_results(conn, state=state, limit=company_limit)
    enrichment = run_batch(
        conn,
        state=state,
        batch_size=company_limit,
        per_domain_limit=3,
        delay_seconds=0.5,
    ) if enqueued else {"claimed": 0, "processed": 0, "contacts_found": 0, "pages_fetched": 0}
    ai = process_ai_batch(conn, limit=contact_limit)

    # Reassert the safety boundary after every hunt.
    conn.execute(
        """update autonomy_policies set enabled=1,approved_states_json='[\"NC\"]',
           require_human_review=1,allow_crm_promotion=0,allow_outreach=0,
           allow_permission_changes=0,updated_at=? where policy_key='default'""",
        (NOW(),),
    )
    conn.commit()

    pending = conn.execute(
        "select count(*) from discovered_contacts where state=? and review_status='Pending review'",
        (state,),
    ).fetchone()[0]
    return {
        "state": state,
        "search_run_id": run_id,
        "companies_seeded": seeded,
        "companies_skipped": skipped,
        "enqueued": enqueued,
        "enrichment": enrichment,
        "ai": ai,
        "pending_review": int(pending or 0),
        "outreach_enabled": False,
        "crm_promotion_enabled": False,
    }
