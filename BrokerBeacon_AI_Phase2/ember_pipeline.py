"""Verified-directory discovery followed by official-website enrichment."""
from __future__ import annotations

from ember_company_crawler import crawl_and_ingest
from ember_hunt import launch as launch_hunt
from mortgage_matchup_ingest import ingest_matchup_results


def _website_seed(item: dict, default_state: str) -> dict:
    return {
        "company": item.get("legal_name", ""),
        "nmls": item.get("nmls_id", ""),
        "website": item.get("website", ""),
        "city": item.get("city", ""),
        "state": item.get("state", default_state),
        "phone": item.get("phone", ""),
        "public_email": item.get("public_email", ""),
    }


def _backfill_website_seeds(conn, state: str, limit: int, existing: list[dict]) -> list[dict]:
    """Add older verified companies that have never completed official-site enrichment."""
    if limit <= len(existing):
        return existing[:limit]
    seen = {
        str(item.get("nmls") or "").strip() or str(item.get("company") or "").strip().lower()
        for item in existing
    }
    rows = conn.execute(
        """select company.* from warehouse_companies company
           where (?='' or upper(company.state)=?)
             and exists (
               select 1 from warehouse_source_records record
               join warehouse_sources source on source.id=record.source_id
               where record.entity_type='company' and record.entity_id=company.id
                 and source.name='Mortgage Matchup')
             and not exists (
               select 1 from warehouse_source_records record
               join warehouse_sources source on source.id=record.source_id
               where record.entity_type='company' and record.entity_id=company.id
                 and source.name='Ember public company websites')
           order by company.updated_at,company.id limit ?""",
        (state, state, limit * 3),
    ).fetchall()
    for row in rows:
        item = dict(row)
        seed = _website_seed(item, state)
        key = str(seed.get("nmls") or "").strip() or str(seed.get("company") or "").strip().lower()
        if not key or key in seen:
            continue
        existing.append(seed)
        seen.add(key)
        if len(existing) >= limit:
            break
    return existing


def launch(conn, *, state: str = "", company_limit: int = 50, contact_limit: int = 1000) -> dict:
    result=launch_hunt(conn,state=state,company_limit=company_limit,contact_limit=contact_limit)
    run_id=int(result.get('search_run_id') or 0)
    resolved_state=str(result.get('state') or state).upper()
    if not run_id:
        raise RuntimeError('Mortgage Matchup search did not produce a run id')
    ingest=ingest_matchup_results(conn,run_id,resolved_state,limit=company_limit)
    website_seeds=[
        _website_seed(item,resolved_state)
        for item in ingest.get('companies',[]) if item.get('legal_name')
    ]
    website_seeds=_backfill_website_seeds(conn,resolved_state,company_limit,website_seeds)
    website_crawl=crawl_and_ingest(conn,website_seeds,state=resolved_state,max_pages=3) if website_seeds else {
        'attempted':0,'completed':0,'failed':0,'fallbacks':0,'pages_fetched':0,
        'officers_created':0,'officers_updated':0,
        'warehouse':{'received':0,'created':0,'updated':0,'rejected':0},'failures':[],
    }
    result['mortgage_matchup_ingest']=ingest
    result['company_crawl']=website_crawl
    result['new_contacts']=ingest.get('officers_created',0)+website_crawl.get('officers_created',0)
    result['message']=(f'Ember completed {resolved_state} verified-directory discovery, resolved each official '
                       'company website, enriched company and contact details, deduplicated the warehouse, '
                       'and prepared CRM promotion.')
    return result

