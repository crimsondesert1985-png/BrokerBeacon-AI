"""Bounded, review-gated Ember hunt with durable multi-state progress."""
from __future__ import annotations
import json, os, sqlite3, urllib.parse
from datetime import datetime, timedelta
from ai_intelligence import initialize as init_ai, process_batch as process_ai_batch
from public_search_connector import initialize as init_public, run_public_search
from website_enrichment import initialize as init_enrichment, enqueue_search_results, run_batch
from ember_activity import initialize as init_activity, record
from national_scheduler import approved_states
NOW=lambda:datetime.now().isoformat(timespec="seconds")

def _domain(url:str)->str:
 return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")

def _valid_public_url(value:str)->bool:
 try:
  parsed=urllib.parse.urlparse((value or '').strip());return parsed.scheme in {'http','https'} and bool(parsed.netloc)
 except Exception:return False

def choose_state(conn:sqlite3.Connection)->str:
 init_activity(conn);states=approved_states()
 rows={r['state']:dict(r) for r in conn.execute("select * from ember_state_cursors")}
 return sorted(states,key=lambda s:(rows.get(s,{}).get('last_run_at',''),rows.get(s,{}).get('companies_processed',0),s))[0]

def _seed_rows(conn:sqlite3.Connection,state:str,after_id:int,limit:int):
 columns={row[1] for row in conn.execute("pragma table_info(national_broker_index)")}
 if not {'id','company','state','source_url'}.issubset(columns):return []
 fields=['id','company','state','source_url']+[x for x in ('city','nmls','source_name') if x in columns]
 q=f"select {','.join(fields)} from national_broker_index where upper(state)=? and id>? and trim(coalesce(source_url,''))<>'' order by id limit ?"
 rows=conn.execute(q,(state,after_id,limit)).fetchall()
 if not rows and after_id>0: rows=conn.execute(q,(state,0,limit)).fetchall()
 return rows

def _promote_public_results(conn:sqlite3.Connection,run_id:int,state:str)->int:
 rows=conn.execute("""select company_name,title,source_url,nmls_id,city from public_search_results
                     where run_id=? and candidate_type='Company' and trim(source_url)<>''""",(run_id,)).fetchall()
 now=NOW();created=0
 for row in rows:
  url=str(row['source_url'] or '').strip()
  if conn.execute("select 1 from national_broker_index where source_url=? limit 1",(url,)).fetchone():continue
  company=str(row['company_name'] or row['title'] or _domain(url) or 'Mortgage company').strip()
  conn.execute("""insert into national_broker_index(nmls,company,city,state,source_name,source_url,
                verification_status,indexed_at,updated_at) values(?,?,?,?,? ,?,'Needs verification',?,?)""",
               (str(row['nmls_id'] or ''),company,str(row['city'] or ''),state,'Google Custom Search',url,now,now))
  created+=1
 conn.commit();return created

def _refresh_index_from_public_search(conn:sqlite3.Connection,state:str,company_limit:int)->dict:
 if not os.getenv('GOOGLE_CSE_API_KEY','').strip() or not os.getenv('GOOGLE_CSE_ID','').strip():
  record(conn,'source_configuration_required','Google public search is not configured',state=state,
         detail='Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID to let Ember discover new public company sources.',severity='warning')
  return {'status':'Blocked','reason':'Google CSE credentials are not configured','indexed':0}
 try:
  result=run_public_search(conn,connector_id=None,state=state,results_per_query=min(max(company_limit,3),10),delay_seconds=0.2)
  indexed=_promote_public_results(conn,int(result['run_id']),state)
  record(conn,'public_search_completed',f'Indexed {indexed} Google company sources for {state}',state=state,
         detail=f"{result.get('results',0)} search results reviewed by the automated intake gate.",severity='success')
  return {'status':'Completed','indexed':indexed,**result}
 except Exception as exc:
  record(conn,'public_search_failed',f'Google public search failed for {state}',state=state,detail=str(exc)[:500],severity='warning')
  return {'status':'Failed','reason':str(exc)[:500],'indexed':0}

def launch(conn:sqlite3.Connection,*,state:str='',company_limit:int=6,contact_limit:int=250)->dict:
 init_public(conn);init_enrichment(conn);init_ai(conn);init_activity(conn)
 state=(state or choose_state(conn)).upper();company_limit=min(max(int(company_limit),1),12);contact_limit=min(max(int(contact_limit),1),500)
 if state not in approved_states(): raise ValueError(f'State {state} is not enabled for Ember discovery')
 cursor=conn.execute("select * from ember_state_cursors where state=?",(state,)).fetchone();after_id=int(cursor['last_index_id'] if cursor else 0)
 seed_rows=list(_seed_rows(conn,state,after_id,company_limit*8));public_search={'status':'Not needed','indexed':0}
 if not seed_rows:
  public_search=_refresh_index_from_public_search(conn,state,company_limit)
  seed_rows=list(_seed_rows(conn,state,after_id,company_limit*8))
 now=NOW();run_id=int(conn.execute("insert into public_search_runs(state,status,created_at,started_at) values(?,'Running',?,?)",(state,now,now)).lastrowid)
 seeded=skipped=0;seen=set();last_index_id=after_id;companies=[]
 record(conn,'hunt_started',f'Ember started a {state} hunt',state=state,detail=f'Beginning after broker index record {after_id}.')
 for rank,row in enumerate(seed_rows,start=1):
  last_index_id=max(last_index_id,int(row['id']))
  url=str(row['source_url'] or '').strip();domain=_domain(url) if _valid_public_url(url) else ''
  if not domain or domain in seen: skipped+=1;continue
  existing=conn.execute("select id,next_crawl_at from ember_company_history where state=? and source_url=?",(state,url)).fetchone()
  if existing and str(existing['next_crawl_at'] or '')>now: skipped+=1;continue
  seen.add(domain);company=str(row['company'] or '').strip();city=str(row['city'] or '') if 'city' in row.keys() else '';nmls=str(row['nmls'] or '') if 'nmls' in row.keys() else ''
  conn.execute("""insert or ignore into public_search_results(run_id,query_text,result_rank,title,snippet,source_url,source_domain,candidate_type,company_name,city,state,nmls_id,review_status,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?, 'Pending review',?)""",(run_id,'national-index-seed',rank,company,'Queued by Ember from the national broker index.',url,domain,'Company',company,city,state,nmls,now))
  conn.execute("""insert into ember_company_history(state,company_name,source_url,source_domain,index_id,status,first_seen_at,last_crawled_at,next_crawl_at) values(?,?,?,?,?,'Queued',?,?,?) on conflict(state,source_url) do update set company_name=excluded.company_name,index_id=excluded.index_id,status='Queued',last_crawled_at=excluded.last_crawled_at,next_crawl_at=excluded.next_crawl_at""",(state,company,url,domain,int(row['id']),now,now,(datetime.now()+timedelta(days=30)).isoformat(timespec='seconds')))
  companies.append(company);seeded+=1
  record(conn,'company_queued',f'Queued {company}',state=state,company_name=company,detail=url)
  if seeded>=company_limit:break
 conn.execute("update public_search_runs set status='Completed',query_count=1,result_count=?,accepted_count=?,rejected_count=?,finished_at=? where id=?",(seeded+skipped,seeded,skipped,NOW(),run_id));conn.commit()
 before=int(conn.execute("select count(*) from discovered_contacts where state=?",(state,)).fetchone()[0])
 enqueued=enqueue_search_results(conn,state=state,limit=max(company_limit,1))
 enrichment=run_batch(conn,state=state,batch_size=min(company_limit,6),per_domain_limit=2,delay_seconds=0.0) if enqueued else {'claimed':0,'processed':0,'contacts_found':0,'pages_fetched':0}
 ai=process_ai_batch(conn,limit=contact_limit)
 after=int(conn.execute("select count(*) from discovered_contacts where state=?",(state,)).fetchone()[0]);new_contacts=max(0,after-before)
 conn.execute("""insert into ember_state_cursors(state,last_index_id,companies_processed,contacts_found,last_run_at,updated_at) values(?,?,?,?,?,?) on conflict(state) do update set last_index_id=excluded.last_index_id,companies_processed=ember_state_cursors.companies_processed+excluded.companies_processed,contacts_found=ember_state_cursors.contacts_found+excluded.contacts_found,last_run_at=excluded.last_run_at,updated_at=excluded.updated_at""",(state,last_index_id,seeded,new_contacts,NOW(),NOW()))
 for company in companies: conn.execute("update ember_company_history set status='Completed',contacts_found=?,pages_fetched=? where state=? and company_name=? and last_crawled_at=?",(new_contacts,int(enrichment.get('pages_fetched',0)),state,company,now))
 conn.execute("update autonomy_policies set enabled=1,approved_states_json=?,require_human_review=1,allow_crm_promotion=0,allow_outreach=0,allow_permission_changes=0,updated_at=? where policy_key='default'",(json.dumps(approved_states()),NOW()));conn.commit()
 record(conn,'hunt_completed',f'Ember completed {state}: {new_contacts} new contacts',state=state,detail=f'{seeded} companies checked; {after} contacts waiting in state inventory.',severity='success' if seeded or new_contacts else 'warning')
 pending=int(conn.execute("select count(*) from discovered_contacts where review_status='Pending review'").fetchone()[0])
 return {'state':state,'search_run_id':run_id,'companies_seeded':seeded,'companies_skipped':skipped,'companies':companies,'public_search':public_search,'enqueued':enqueued,'enrichment':enrichment,'ai':ai,'new_contacts':new_contacts,'pending_review':pending,'cursor':last_index_id,'approved_states':approved_states(),'outreach_enabled':False,'crm_promotion_enabled':False,'message':f'Ember completed a safe {state} discovery batch.'}
