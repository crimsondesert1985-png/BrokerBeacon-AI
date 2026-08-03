"""Bounded, review-gated Ember hunt with durable multi-state progress."""
from __future__ import annotations
import json, sqlite3, urllib.parse
from datetime import datetime, timedelta
from ai_intelligence import initialize as init_ai, process_batch as process_ai_batch
from public_search_connector import initialize as init_public, run_public_search
from website_enrichment import initialize as init_enrichment, enqueue_search_results, run_batch
from ember_activity import initialize as init_activity, record
from national_scheduler import approved_states
from multi_search_provider import configured_providers
from source_resilience import initialize as init_resilience, record_yield, state_available
NOW=lambda:datetime.now().isoformat(timespec="seconds")

STATE_METROS={
 'AL':['Birmingham','Huntsville','Mobile'],'AK':['Anchorage','Fairbanks'],'AZ':['Phoenix','Tucson','Mesa'],
 'AR':['Little Rock','Fayetteville','Fort Smith'],'CA':['Los Angeles','San Diego','San Francisco','Sacramento','Fresno'],
 'CO':['Denver','Colorado Springs','Fort Collins'],'CT':['Hartford','New Haven','Stamford'],'DE':['Wilmington','Dover'],
 'FL':['Miami','Tampa','Orlando','Jacksonville','Fort Lauderdale'],'GA':['Atlanta','Savannah','Augusta'],
 'HI':['Honolulu','Hilo'],'ID':['Boise','Idaho Falls','Coeur d Alene'],'IL':['Chicago','Springfield','Rockford'],
 'IN':['Indianapolis','Fort Wayne','Evansville'],'IA':['Des Moines','Cedar Rapids','Davenport'],
 'KS':['Wichita','Overland Park','Topeka'],'KY':['Louisville','Lexington','Bowling Green'],
 'LA':['New Orleans','Baton Rouge','Shreveport'],'ME':['Portland','Bangor'],'MD':['Baltimore','Bethesda','Frederick'],
 'MA':['Boston','Worcester','Springfield'],'MI':['Detroit','Grand Rapids','Lansing'],
 'MN':['Minneapolis','Saint Paul','Rochester'],'MS':['Jackson','Gulfport','Hattiesburg'],
 'MO':['Saint Louis','Kansas City','Springfield'],'MT':['Billings','Missoula','Bozeman'],
 'NE':['Omaha','Lincoln'],'NV':['Las Vegas','Reno','Henderson'],'NH':['Manchester','Nashua','Concord'],
 'NJ':['Newark','Jersey City','Cherry Hill'],'NM':['Albuquerque','Santa Fe','Las Cruces'],
 'NY':['New York City','Buffalo','Rochester','Albany','Syracuse'],'NC':['Charlotte','Raleigh','Greensboro','Wilmington','Asheville'],
 'ND':['Fargo','Bismarck'],'OH':['Columbus','Cleveland','Cincinnati','Dayton','Toledo'],
 'OK':['Oklahoma City','Tulsa','Norman'],'OR':['Portland','Eugene','Salem'],
 'PA':['Philadelphia','Pittsburgh','Allentown','Harrisburg'],'RI':['Providence','Warwick'],
 'SC':['Charleston','Columbia','Greenville','Myrtle Beach'],'SD':['Sioux Falls','Rapid City'],
 'TN':['Nashville','Memphis','Knoxville','Chattanooga'],'TX':['Houston','Dallas','Austin','San Antonio','Fort Worth'],
 'UT':['Salt Lake City','Provo','Ogden'],'VT':['Burlington','Montpelier'],'VA':['Virginia Beach','Richmond','Arlington','Roanoke'],
 'WA':['Seattle','Spokane','Tacoma'],'WV':['Charleston','Morgantown','Huntington'],
 'WI':['Milwaukee','Madison','Green Bay'],'WY':['Cheyenne','Casper']
}

def _domain(url:str)->str:
 return urllib.parse.urlparse(url).netloc.lower().removeprefix('www.')

def _valid_public_url(value:str)->bool:
 try:
  parsed=urllib.parse.urlparse((value or '').strip());return parsed.scheme in {'http','https'} and bool(parsed.netloc)
 except Exception:return False

def choose_state(conn:sqlite3.Connection)->str:
 init_activity(conn);init_resilience(conn);states=approved_states()
 available=[state for state in states if state_available(conn,state)] or states
 rows={r['state']:dict(r) for r in conn.execute('select * from ember_state_cursors')}
 return sorted(available,key=lambda s:(rows.get(s,{}).get('last_run_at',''),rows.get(s,{}).get('companies_processed',0),s))[0]

def _seed_rows(conn:sqlite3.Connection,state:str,after_id:int,limit:int,ignore_cooldown:bool=False):
 columns={row[1] for row in conn.execute('pragma table_info(national_broker_index)')}
 if not {'id','company','state','source_url'}.issubset(columns):return []
 optional=[x for x in ('city','nmls','source_name') if x in columns]
 fields=['id','company','state','source_url']+optional
 selected=','.join(f'n.{field}' for field in fields)
 now=NOW()
 cooldown='' if ignore_cooldown else """and not exists (
            select 1 from ember_company_history h
            where upper(h.state)=upper(n.state) and h.source_url=n.source_url
              and trim(coalesce(h.next_crawl_at,''))<>'' and h.next_crawl_at>?
          )"""
 params=(state,after_id,limit) if ignore_cooldown else (state,after_id,now,limit)
 q=f"""select {selected} from national_broker_index n
        where upper(n.state)=? and n.id>? and trim(coalesce(n.source_url,''))<>''
          {cooldown}
        order by n.id limit ?"""
 rows=conn.execute(q,params).fetchall()
 if not rows and after_id>0:
  params=(state,0,limit) if ignore_cooldown else (state,0,now,limit)
  rows=conn.execute(q,params).fetchall()
 return rows

def _promote_public_results(conn:sqlite3.Connection,run_id:int,state:str)->int:
 columns={row[1] for row in conn.execute('pragma table_info(public_search_results)')}
 provider_field='provider_name' if 'provider_name' in columns else "'' as provider_name"
 rows=conn.execute(f"""select company_name,title,source_url,nmls_id,city,{provider_field} from public_search_results
                     where run_id=? and candidate_type='Company' and trim(source_url)<>''""",(run_id,)).fetchall()
 now=NOW();created=0
 for row in rows:
  url=str(row['source_url'] or '').strip()
  domain=_domain(url)
  if not domain:continue
  if conn.execute("select 1 from national_broker_index where lower(source_url)=lower(?) or lower(source_url) like ? limit 1",(url,f'%://{domain}/%')).fetchone():continue
  company=str(row['company_name'] or row['title'] or domain.split('.')[0].replace('-',' ').title() or 'Mortgage company').strip()
  providers=str(row['provider_name'] or '').strip()
  source_name='Public search: '+providers if providers else 'Public search'
  conn.execute("""insert into national_broker_index(nmls,company,city,state,source_name,source_url,
                verification_status,indexed_at,updated_at) values(?,?,?,?,? ,?,'Needs verification',?,?)""",
               (str(row['nmls_id'] or ''),company,str(row['city'] or ''),state,source_name,url,now,now))
  created+=1
 conn.commit();return created

def _eligible_count(conn:sqlite3.Connection,state:str)->int:
 try:
  return int(conn.execute("select count(distinct lower(source_url)) from national_broker_index where upper(state)=? and trim(coalesce(source_url,''))<>''",(state,)).fetchone()[0] or 0)
 except Exception:return 0

def _refresh_index_from_public_search(conn:sqlite3.Connection,state:str,company_limit:int)->dict:
 providers=configured_providers()
 if not providers:
  reason='No public search provider is configured'
  record(conn,'source_configuration_required',reason,state=state,
         detail='Configure Google CSE, Brave, Tavily, Firecrawl, or SerpAPI to expand national discovery.',severity='warning')
  return {'status':'Blocked','reason':reason,'indexed':0,'providers':[],'runs':[],'errors':[]}
 per_query=min(max(company_limit,10),50)
 scopes=['']+STATE_METROS.get(state,[])[:4]
 indexed_total=0;results_total=0;accepted_total=0;queries_total=0;runs=[];errors=[];used=set()
 for metro in scopes:
  try:
   result=run_public_search(conn,connector_id=None,state=state,metro=metro,results_per_query=per_query,delay_seconds=0.1)
   indexed=_promote_public_results(conn,int(result['run_id']),state)
   indexed_total+=indexed;results_total+=int(result.get('results',0));accepted_total+=int(result.get('accepted',0));queries_total+=int(result.get('queries',0))
   used.update(result.get('providers') or [])
   runs.append({'run_id':result.get('run_id'),'metro':metro or 'Statewide','indexed':indexed,'results':result.get('results',0),'status':'Completed'})
   if _eligible_count(conn,state)>=company_limit:break
  except Exception as exc:
   error=str(exc)[:500];errors.append({'metro':metro or 'Statewide','error':error})
   runs.append({'metro':metro or 'Statewide','indexed':0,'results':0,'status':'Failed','error':error})
   record(conn,'public_search_scope_failed',f'Public search scope failed for {state}',state=state,detail=f'{metro or "Statewide"}: {error}',severity='warning')
 status='Completed' if any(r['status']=='Completed' for r in runs) else 'Failed'
 reason='; '.join(e['error'] for e in errors[:3]) if status=='Failed' else ''
 record(conn,'public_search_completed' if status=='Completed' else 'public_search_failed',
        f'Indexed {indexed_total} public company sources for {state}' if status=='Completed' else f'Public search failed for {state}',
        state=state,detail=f'{results_total} results across {queries_total} queries and {len(scopes)} geographic scopes. {reason}'.strip(),
        severity='success' if status=='Completed' else 'warning')
 return {'status':status,'reason':reason,'indexed':indexed_total,'results':results_total,'accepted':accepted_total,
         'queries':queries_total,'providers':sorted(used) or providers,'runs':runs,'errors':errors}

def launch(conn:sqlite3.Connection,*,state:str='',company_limit:int=50,contact_limit:int=1000)->dict:
 init_public(conn);init_enrichment(conn);init_ai(conn);init_activity(conn);init_resilience(conn)
 state=(state or choose_state(conn)).upper();company_limit=min(max(int(company_limit),1),100);contact_limit=min(max(int(contact_limit),1),2000)
 if state not in approved_states(): raise ValueError(f'State {state} is not enabled for Ember discovery')
 cursor=conn.execute('select * from ember_state_cursors where state=?',(state,)).fetchone();after_id=int(cursor['last_index_id'] if cursor else 0)
 seed_rows=list(_seed_rows(conn,state,after_id,company_limit*20));public_search={'status':'Not needed','indexed':0,'providers':[],'runs':[]}
 if len(seed_rows)<company_limit:
  public_search=_refresh_index_from_public_search(conn,state,company_limit)
  seed_rows=list(_seed_rows(conn,state,after_id,company_limit*20))
 if not seed_rows:
  seed_rows=list(_seed_rows(conn,state,0,company_limit*20,ignore_cooldown=True))
  if seed_rows:
   public_search['fallback']='Reused known broker index records because fresh discovery was unavailable.'
 now=NOW();run_id=int(conn.execute("insert into public_search_runs(state,status,created_at,started_at) values(?,'Running',?,?)",(state,now,now)).lastrowid)
 seeded=skipped=0;seen=set();last_index_id=after_id;companies=[]
 record(conn,'hunt_started',f'Ember started a {state} hunt',state=state,detail=f'Targeting up to {company_limit} broker companies after index record {after_id}.')
 for rank,row in enumerate(seed_rows,start=1):
  last_index_id=max(last_index_id,int(row['id']))
  url=str(row['source_url'] or '').strip();domain=_domain(url) if _valid_public_url(url) else ''
  if not domain or domain in seen:skipped+=1;continue
  existing=conn.execute('select id,next_crawl_at from ember_company_history where state=? and source_url=?',(state,url)).fetchone()
  if existing and str(existing['next_crawl_at'] or '')>now and not public_search.get('fallback'):skipped+=1;continue
  seen.add(domain);company=str(row['company'] or '').strip();city=str(row['city'] or '') if 'city' in row.keys() else '';nmls=str(row['nmls'] or '') if 'nmls' in row.keys() else ''
  conn.execute("""insert or ignore into public_search_results(run_id,query_text,result_rank,title,snippet,source_url,source_domain,candidate_type,company_name,city,state,nmls_id,review_status,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?, 'Pending review',?)""",(run_id,'national-index-seed',rank,company,'Queued by Ember from the national broker index.',url,domain,'Company',company,city,state,nmls,now))
  conn.execute("""insert into ember_company_history(state,company_name,source_url,source_domain,index_id,status,first_seen_at,last_crawled_at,next_crawl_at) values(?,?,?,?,?,'Queued',?,?,?) on conflict(state,source_url) do update set company_name=excluded.company_name,index_id=excluded.index_id,status='Queued',last_crawled_at=excluded.last_crawled_at,next_crawl_at=excluded.next_crawl_at""",(state,company,url,domain,int(row['id']),now,now,(datetime.now()+timedelta(days=30)).isoformat(timespec='seconds')))
  companies.append(company);seeded+=1
  record(conn,'company_queued',f'Queued {company}',state=state,company_name=company,detail=url)
  if seeded>=company_limit:break
 conn.execute("update public_search_runs set status='Completed',query_count=1,result_count=?,accepted_count=?,rejected_count=?,finished_at=? where id=?",(seeded+skipped,seeded,skipped,NOW(),run_id));conn.commit()
 before=int(conn.execute('select count(*) from discovered_contacts where state=?',(state,)).fetchone()[0])
 enqueued=enqueue_search_results(conn,state=state,limit=max(company_limit*4,200))
 enrichment=run_batch(conn,state=state,batch_size=min(company_limit,50),per_domain_limit=3,delay_seconds=0.0) if enqueued else {'claimed':0,'processed':0,'contacts_found':0,'pages_fetched':0}
 ai=process_ai_batch(conn,limit=contact_limit)
 after=int(conn.execute('select count(*) from discovered_contacts where state=?',(state,)).fetchone()[0]);new_contacts=max(0,after-before)
 conn.execute("""insert into ember_state_cursors(state,last_index_id,companies_processed,contacts_found,last_run_at,updated_at) values(?,?,?,?,?,?) on conflict(state) do update set last_index_id=excluded.last_index_id,companies_processed=ember_state_cursors.companies_processed+excluded.companies_processed,contacts_found=ember_state_cursors.contacts_found+excluded.contacts_found,last_run_at=excluded.last_run_at,updated_at=excluded.updated_at""",(state,last_index_id,seeded,new_contacts,NOW(),NOW()))
 for company in companies:conn.execute("update ember_company_history set status='Completed',contacts_found=?,pages_fetched=? where state=? and company_name=? and last_crawled_at=?",(new_contacts,int(enrichment.get('pages_fetched',0)),state,company,now))
 conn.execute("update autonomy_policies set enabled=1,approved_states_json=?,require_human_review=1,allow_crm_promotion=0,allow_outreach=0,allow_permission_changes=0,updated_at=? where policy_key='default'",(json.dumps(approved_states()),NOW()));conn.commit()
 resilience=record_yield(conn,state,companies=seeded,contacts=new_contacts,provider_status=public_search.get('status','Not needed'))
 if resilience.get('paused'):
  record(conn,'state_source_paused',f'{state} paused after repeated zero-yield hunts',state=state,detail=f"Automatic retry after {resilience.get('paused_until','')}",severity='warning')
 record(conn,'hunt_completed',f'Ember completed {state}: {new_contacts} new contacts',state=state,detail=f'{seeded} companies checked toward a target of {company_limit}; {after} contacts waiting in state inventory.',severity='success' if seeded or new_contacts else 'warning')
 pending=int(conn.execute("select count(*) from discovered_contacts where review_status='Pending review'").fetchone()[0])
 return {'state':state,'search_run_id':run_id,'company_target':company_limit,'companies_seeded':seeded,'companies_skipped':skipped,'companies':companies,'public_search':public_search,'source_resilience':resilience,'enqueued':enqueued,'enrichment':enrichment,'ai':ai,'new_contacts':new_contacts,'pending_review':pending,'cursor':last_index_id,'approved_states':approved_states(),'outreach_enabled':False,'crm_promotion_enabled':False,'message':f'Ember completed a safe {state} discovery batch.'}
