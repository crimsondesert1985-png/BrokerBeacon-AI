"""Promote only Mortgage Matchup-verified warehouse entities into CRM prospects."""
from __future__ import annotations
import json,re,sqlite3
from datetime import datetime
NOW=lambda: datetime.now().isoformat(timespec='seconds')
SCHEMA="""
create table if not exists autonomous_prospecting_runs(id integer primary key,state text default '',status text not null default 'Running',warehouse_examined integer not null default 0,prospects_created integer not null default 0,prospects_updated integer not null default 0,contacts_created integer not null default 0,duplicates_skipped integer not null default 0,rejected integer not null default 0,error text default '',started_at text not null,finished_at text default '');
create table if not exists autonomous_prospect_links(warehouse_company_id integer primary key,prospect_id integer not null,promotion_reason text not null default '',promoted_at text not null,updated_at text not null);
create index if not exists idx_autonomous_runs_state on autonomous_prospecting_runs(state,id desc);
create index if not exists idx_autonomous_links_prospect on autonomous_prospect_links(prospect_id);
"""

def initialize(conn): conn.executescript(SCHEMA); conn.commit()
def _cols(conn,t): return {str(r[1]) for r in conn.execute(f'pragma table_info({t}')}
def _norm(v): return re.sub(r'[^a-z0-9]+',' ',(v or '').lower()).strip()
def _digits(v): return re.sub(r'\D+','',v or '')

def _insert(conn,table,values):
    cols={str(r[1]) for r in conn.execute(f'pragma table_info({table})')}; p={k:v for k,v in values.items() if k in cols}
    names=list(p); cur=conn.execute(f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})",tuple(p[n] for n in names)); return int(cur.lastrowid)

def _update(conn,table,row_id,values):
    cols={str(r[1]) for r in conn.execute(f'pragma table_info({table})')}; p={k:v for k,v in values.items() if k in cols and k!='id'}
    if p: conn.execute(f"update {table} set "+','.join(f'{k}=?' for k in p)+" where id=?",tuple(p[k] for k in p)+(row_id,))

def _find(conn,c):
    cols={str(r[1]) for r in conn.execute('pragma table_info(prospects)')}; n=_digits(str(c.get('nmls_id') or ''))
    if n and 'nmls' in cols:
        r=conn.execute("select * from prospects where replace(replace(coalesce(nmls,''),'-',''),' ','')=? limit 1",(n,)).fetchone()
        if r:return r
    name=_norm(str(c.get('legal_name') or '')); state=str(c.get('state') or '').upper()
    rows=conn.execute("select * from prospects where upper(coalesce(state,''))=?",(state,)).fetchall() if 'state' in cols else conn.execute('select * from prospects').fetchall()
    return next((r for r in rows if _norm(str(r['company'] or ''))==name),None)

def purge_invalid_ember_prospects(conn):
    initialize(conn)
    bad=[int(r[0]) for r in conn.execute("""select p.id from prospects p where lower(coalesce(p.source_name,'')) like 'ember%'
      and not exists(select 1 from autonomous_prospect_links l join warehouse_source_records wr on wr.entity_type='company' and wr.entity_id=l.warehouse_company_id join warehouse_sources s on s.id=wr.source_id where l.prospect_id=p.id and s.name='Mortgage Matchup')""").fetchall()]
    if bad:
        marks=','.join('?' for _ in bad)
        conn.execute(f'delete from contacts where prospect_id in ({marks})',bad)
        conn.execute(f'delete from autonomous_prospect_links where prospect_id in ({marks})',bad)
        conn.execute(f'delete from prospects where id in ({marks})',bad)
        conn.commit()
    return len(bad)

def promote_warehouse_companies(conn,*,state='',limit=100,minimum_score=50):
    initialize(conn); purge_invalid_ember_prospects(conn); state=(state or '').upper()[:2]; now=NOW()
    run_id=int(conn.execute('insert into autonomous_prospecting_runs(state,started_at) values(?,?)',(state,now)).lastrowid)
    counts={'run_id':run_id,'warehouse_examined':0,'prospects_created':0,'prospects_updated':0,'contacts_created':0,'duplicates_skipped':0,'rejected':0}
    try:
        rows=conn.execute("""select distinct c.* from warehouse_companies c join warehouse_source_records wr on wr.entity_type='company' and wr.entity_id=c.id join warehouse_sources s on s.id=wr.source_id and s.name='Mortgage Matchup' where (?='' or upper(c.state)=?) order by c.id desc limit ?""",(state,state,max(1,min(int(limit),500)))).fetchall()
        pcols={str(r[1]) for r in conn.execute('pragma table_info(prospects)')}; ccols={str(r[1]) for r in conn.execute('pragma table_info(contacts)')}
        for raw in rows:
            c=dict(raw); counts['warehouse_examined']+=1
            if not c.get('legal_name') or not _digits(str(c.get('nmls_id') or '')):
                counts['rejected']+=1; continue
            score=90 if c.get('phone') or c.get('public_email') else 80
            reasons=['Mortgage Matchup company listing','Company NMLS identifier available']
            existing=_find(conn,c)
            vals={'company':c['legal_name'],'nmls':c.get('nmls_id',''),'website':c.get('website',''),'phone':c.get('phone',''),'email':c.get('public_email',''),'city':c.get('city',''),'state':c.get('state',''),'status':'New','score':score,'signal':'Mortgage Matchup verified broker listing','source_name':'Mortgage Matchup via Ember','source_url':c.get('source_url','') or 'https://mortgagematchup.com','verification_status':'Verify in NMLS before outreach','ai_summary':'; '.join(reasons),'next_best_action':'Verify licensing and contact details, then review for outreach.','created_at':now,'updated_at':now}
            if existing:
                pid=int(existing['id']); improvements={k:v for k,v in vals.items() if k in pcols and k not in {'created_at'} and (k in {'source_name','source_url','signal','verification_status','ai_summary','next_best_action','updated_at'} or not str(existing[k] or '').strip())}; _update(conn,'prospects',pid,improvements); counts['prospects_updated']+=1; counts['duplicates_skipped']+=1
            else:
                pid=_insert(conn,'prospects',vals); counts['prospects_created']+=1
            conn.execute("insert into autonomous_prospect_links(warehouse_company_id,prospect_id,promotion_reason,promoted_at,updated_at) values(?,?,?,?,?) on conflict(warehouse_company_id) do update set prospect_id=excluded.prospect_id,promotion_reason=excluded.promotion_reason,updated_at=excluded.updated_at",(c['id'],pid,json.dumps(reasons),now,now))
            for o in conn.execute('select * from warehouse_officers where company_id=? order by id',(c['id'],)).fetchall():
                o=dict(o); name=str(o.get('full_name') or '').strip()
                if not name: continue
                dup=conn.execute("select id from contacts where prospect_id=? and (lower(trim(coalesce(name,'')))=lower(trim(?)) or (?<>'' and replace(replace(coalesce(nmls,''),'-',''),' ','')=?)) limit 1",(pid,name,_digits(str(o.get('nmls_id') or '')),_digits(str(o.get('nmls_id') or '')))).fetchone() if 'prospect_id' in ccols else None
                if dup: continue
                _insert(conn,'contacts',{'prospect_id':pid,'name':name,'title':o.get('title') or 'Mortgage Loan Originator','email':o.get('public_email',''),'phone':o.get('phone',''),'nmls':o.get('nmls_id',''),'city':o.get('city',''),'state':o.get('state',''),'roster_status':'Needs review','source_name':'Mortgage Matchup via Ember','created_at':now,'updated_at':now}); counts['contacts_created']+=1
        conn.execute("update autonomous_prospecting_runs set status='Completed',warehouse_examined=?,prospects_created=?,prospects_updated=?,contacts_created=?,duplicates_skipped=?,rejected=?,finished_at=? where id=?",(counts['warehouse_examined'],counts['prospects_created'],counts['prospects_updated'],counts['contacts_created'],counts['duplicates_skipped'],counts['rejected'],NOW(),run_id)); conn.commit(); return counts
    except Exception as exc:
        conn.rollback(); initialize(conn); conn.execute("update autonomous_prospecting_runs set status='Failed',error=?,finished_at=? where id=?",(str(exc)[:1000],NOW(),run_id)); conn.commit(); raise
