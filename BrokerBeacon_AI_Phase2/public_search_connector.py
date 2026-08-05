"""Mortgage Matchup-only discovery for Ember.

Search providers are used only to locate public Mortgage Matchup Company/Profile
pages. Generic web results can never enter the prospect pipeline.
"""
from __future__ import annotations

import re
import sqlite3
import time
import urllib.parse
from datetime import datetime

from multi_search_provider import configured_providers, search_all

NOW = lambda: datetime.now().isoformat(timespec="seconds")
DOMAIN = "mortgagematchup.com"
SCHEMA = """
create table if not exists public_search_runs(
 id integer primary key,connector_id integer,state text not null,query_count integer not null default 0,
 result_count integer not null default 0,accepted_count integer not null default 0,rejected_count integer not null default 0,
 status text not null default 'Queued',error text default '',created_at text not null,started_at text default '',finished_at text default '');
create table if not exists public_search_results(
 id integer primary key,run_id integer not null,query_text text not null,result_rank integer not null,title text default '',
 snippet text default '',source_url text not null,source_domain text default '',candidate_type text not null default 'Unknown',
 company_name text default '',person_name text default '',city text default '',state text default '',nmls_id text default '',
 phone text default '',public_email text default '',provider_name text default '',review_status text not null default 'Pending review',
 created_at text not null,unique(run_id,source_url));
create index if not exists idx_public_search_runs_state on public_search_runs(state,status,id desc);
create index if not exists idx_public_search_results_review on public_search_results(review_status,state,id desc);
"""
STATE_NAMES={'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'}


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def build_queries(state: str, metro: str = "") -> list[str]:
    state=(state or '').strip().upper()
    if state not in STATE_NAMES: raise ValueError('A valid two-letter state is required')
    place=(metro or STATE_NAMES[state]).strip()
    return [
        f'site:mortgagematchup.com/Company/ "{place}" "NMLS"',
        f'site:mortgagematchup.com/Profile/ "{place}" "NMLS"',
        f'site:mortgagematchup.com/Company/ "{STATE_NAMES[state]}" mortgage originators',
    ]


def _canonical(url: str) -> str:
    try:
        p=urllib.parse.urlparse(url)
        host=p.netloc.lower().removeprefix('www.')
        path=re.sub(r'/+','/',p.path).rstrip('/')
        if host != DOMAIN or not re.fullmatch(r'/(Company|Profile)/[^/?#]+',path,re.I): return ''
        return f'https://{DOMAIN}{path}'
    except Exception: return ''


def _extract_nmls(text: str) -> str:
    m=re.search(r'\bNMLS(?:\s*ID)?\s*[:#-]?\s*(\d{4,12})\b',text or '',re.I)
    return m.group(1) if m else ''


def is_broker_candidate(title: str, snippet: str, url: str) -> bool:
    return bool(_canonical(url))


def classify_result(title: str, snippet: str, url: str) -> dict:
    url=_canonical(url)
    person='/Profile/' in url
    clean=re.sub(r'\s*[-|·].*$','',title or '').strip()
    return {'candidate_type':'Person' if person else 'Company','company_name':'' if person else clean,
            'person_name':clean if person else '','nmls_id':_extract_nmls(' '.join((title or '',snippet or ''))),
            'phone':'','public_email':''}


def search_provider(query: str, *, count: int = 20) -> dict:
    providers=configured_providers()
    if not providers: raise RuntimeError('No public search provider is configured')
    response=search_all(query,limit_per_provider=min(max(int(count),1),20),providers=providers)
    if not any(v.get('status')=='Completed' for v in response.get('provider_stats',{}).values()):
        raise RuntimeError('All configured public search providers failed')
    return response


def run_public_search(conn: sqlite3.Connection, *, connector_id: int | None, state: str,
                      metro: str = '', results_per_query: int = 20, delay_seconds: float = .25) -> dict:
    initialize(conn); state=state.upper(); queries=build_queries(state,metro); now=NOW()
    run_id=int(conn.execute("insert into public_search_runs(connector_id,state,status,created_at,started_at) values(?,?,'Running',?,?)",(connector_id,state,now,now)).lastrowid); conn.commit()
    accepted=rejected=completed=0; seen=set(); errors=[]; providers=set()
    try:
        for query in queries:
            try: response=search_provider(query,count=results_per_query); completed+=1
            except Exception as exc: errors.append({'query':query,'error':str(exc)[:300]}); continue
            for rank,item in enumerate(response.get('results',[]),1):
                url=_canonical(str(item.get('url') or ''))
                if not url: rejected+=1; continue
                if url.lower() in seen: continue
                seen.add(url.lower()); title=str(item.get('title') or ''); snippet=str(item.get('description') or '')
                parsed=classify_result(title,snippet,url)
                pnames=[str(p.get('provider') or '') for p in item.get('providers',[]) if p.get('provider')]; providers.update(pnames)
                conn.execute("""insert or ignore into public_search_results(run_id,query_text,result_rank,title,snippet,source_url,source_domain,candidate_type,company_name,person_name,state,nmls_id,phone,public_email,provider_name,created_at) values(?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?)""",
                    (run_id,query,rank,title,snippet,url,DOMAIN,parsed['candidate_type'],parsed['company_name'],parsed['person_name'],state,parsed['nmls_id'],'','',','.join(pnames),NOW()))
                accepted+=1
            conn.commit(); time.sleep(delay_seconds if delay_seconds else 0)
        if not completed: raise RuntimeError('; '.join(e['error'] for e in errors[:3]) or 'Mortgage Matchup search failed')
        conn.execute("update public_search_runs set status='Completed',query_count=?,result_count=?,accepted_count=?,rejected_count=?,finished_at=? where id=?",(completed,accepted,accepted,rejected,NOW(),run_id)); conn.commit()
        return {'run_id':run_id,'queries':completed,'queries_attempted':len(queries),'query_failures':errors,'results':accepted,'accepted':accepted,'rejected':rejected,'providers':sorted(providers),'source':'Mortgage Matchup only'}
    except Exception as exc:
        conn.execute("update public_search_runs set status='Failed',error=?,finished_at=? where id=?",(str(exc)[:500],NOW(),run_id)); conn.commit(); raise


def pending_results(conn: sqlite3.Connection, state: str = '', limit: int = 200) -> list[dict]:
    initialize(conn); state=(state or '').upper()
    rows=conn.execute("select * from public_search_results where review_status='Pending review' and source_domain=? and (?='' or state=?) order by id desc limit ?",(DOMAIN,state,state,min(max(int(limit),1),1000))).fetchall()
    return [dict(r) for r in rows]
