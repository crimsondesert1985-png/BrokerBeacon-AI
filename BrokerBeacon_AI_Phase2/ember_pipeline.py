"""Full Ember discovery pipeline: hunt, crawl, warehouse, review."""
from __future__ import annotations

from ember_company_crawler import crawl_and_ingest
from ember_hunt import launch as launch_hunt


def launch(conn, *, state: str = "", company_limit: int = 6, contact_limit: int = 250) -> dict:
    """Run the existing guarded hunt, then build the company warehouse."""
    result = launch_hunt(
        conn,
        state=state,
        company_limit=company_limit,
        contact_limit=contact_limit,
    )
    run_id = int(result.get("search_run_id") or 0)
    seeds = []
    if run_id:
        rows = conn.execute(
            """select company_name as company,nmls_id as nmls,city,state,source_url
               from public_search_results
               where run_id=? and candidate_type='Company' and trim(coalesce(source_url,''))<>''
               order by result_rank limit ?""",
            (run_id, max(1, min(int(company_limit), 25))),
        ).fetchall()
        seeds = [dict(row) for row in rows]
    try:
        result["company_crawl"] = crawl_and_ingest(
            conn,
            seeds,
            state=str(result.get("state") or state).upper(),
            max_pages=5,
        ) if seeds else {
            "attempted": 0,
            "completed": 0,
            "failed": 0,
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [],
        }
    except Exception as exc:
        # Company crawling must never bypass the existing review-gated hunt or
        # prevent the queue from advancing to the next state.
        result["company_crawl"] = {
            "attempted": len(seeds),
            "completed": 0,
            "failed": len(seeds),
            "pages_fetched": 0,
            "warehouse": {"received": 0, "created": 0, "updated": 0, "rejected": 0},
            "failures": [{"company": "", "reason": str(exc)[:500]}],
            "status": "Failed safely",
        }
    result["message"] = (
        f"Ember completed {result.get('state','')} discovery, public website crawling, "
        "warehouse deduplication, and review preparation."
    )
    return result
