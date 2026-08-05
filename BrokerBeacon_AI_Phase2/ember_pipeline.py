"""Mortgage Matchup-only Ember pipeline."""
from __future__ import annotations

from ember_hunt import launch as launch_hunt
from mortgage_matchup_ingest import ingest_matchup_results


def launch(conn, *, state: str = "", company_limit: int = 50, contact_limit: int = 1000) -> dict:
    result=launch_hunt(conn,state=state,company_limit=company_limit,contact_limit=contact_limit)
    run_id=int(result.get('search_run_id') or 0)
    resolved_state=str(result.get('state') or state).upper()
    if not run_id:
        raise RuntimeError('Mortgage Matchup search did not produce a run id')
    ingest=ingest_matchup_results(conn,run_id,resolved_state,limit=company_limit)
    result['mortgage_matchup_ingest']=ingest
    result['company_crawl']={
        'attempted':ingest.get('company_pages',0),
        'completed':ingest.get('company_pages',0)-len([f for f in ingest.get('failures',[]) if '/Company/' in f.get('url','')]),
        'failed':len(ingest.get('failures',[])),
        'pages_fetched':ingest.get('company_pages',0)+ingest.get('officers_created',0)+ingest.get('officers_updated',0),
        'warehouse':{
            'received':ingest.get('company_pages',0),
            'created':ingest.get('companies_created',0),
            'updated':ingest.get('companies_updated',0),
            'rejected':len(ingest.get('failures',[])),
        },
    }
    result['new_contacts']=ingest.get('officers_created',0)
    result['message']=(f'Ember completed {resolved_state} Mortgage Matchup discovery, company ingestion, '
                       'loan-officer ingestion, warehouse deduplication, and CRM promotion preparation.')
    return result
