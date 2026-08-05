"""Parse public Mortgage Matchup company/profile pages into BrokerBeacon's warehouse."""
from __future__ import annotations

import html
import re
import sqlite3
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime

from national_warehouse import create_import_job, create_source, ingest_companies, normalize, digits

BASE='https://mortgagematchup.com'
UA='BrokerBeacon-Ember/1.0 (+public mortgage broker research)'
NOW=lambda: datetime.now().isoformat(timespec='seconds')


def _allowed(url: str) -> bool:
    try:
        rp=urllib.robotparser.RobotFileParser(); rp.set_url(BASE+'/robots.txt'); rp.read()
        return rp.can_fetch(UA,url)
    except Exception:
        return False


def _fetch(url: str) -> str:
    if not _allowed(url): raise RuntimeError('Mortgage Matchup robots policy did not allow this page')
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=20) as response:
        if response.status != 200: raise RuntimeError(f'Mortgage Matchup returned HTTP {response.status}')
        return response.read(2_000_000).decode('utf-8','ignore')


def _text(raw: str) -> str:
    raw=re.sub(r'<script\b[^>]*>.*?</script>',' ',raw,flags=re.I|re.S)
    raw=re.sub(r'<style\b[^>]*>.*?</style>',' ',raw,flags=re.I|re.S)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',raw))).strip()


def _match(pattern: str, value: str) -> str:
    m=re.search(pattern,value,re.I|re.S)
    return html.unescape(re.sub(r'<[^>]+>',' ',m.group(1))).strip() if m else ''


def _company_url(url: str) -> str:
    try:
        p=urllib.parse.urlparse(url); host=p.netloc.lower().removeprefix('www.'); path=p.path.rstrip('/')
        if host!='mortgagematchup.com' or not re.fullmatch(r'/Company/[^/?#]+',path,re.I): return ''
        return BASE+path
    except Exception: return ''


def parse_company_page(url: str, raw: str, state_hint: str='') -> dict:
    text=_text(raw)
    name=_match(r'<h3[^>]*>(.*?)</h3>',raw) or _match(r'<title[^>]*>(.*?)</title>',raw).split('|')[0].strip()
    nmls=_match(r'NMLS\s*#?:?\s*</?[^>]*>?\s*(\d{4,12})',raw) or (_match(r'NMLS\s*#?:?\s*(\d{4,12})',text))
    phone=''; pm=re.search(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}',text)
    if pm: phone=digits(pm.group(0))[-10:]
    email=''; em=re.search(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',text,re.I)
    if em: email=em.group(0).lower()
    address=''; city=''; state=state_hint.upper(); postal=''
    am=re.search(r'([A-Za-z0-9 .#-]+?)\s+([A-Za-z .-]+)\s*,\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',text)
    if am: address,city,state,postal=[x.strip() for x in am.groups()]
    external=''
    for href in re.findall(r'href=["\']([^"\']+)["\']',raw,re.I):
        full=urllib.parse.urljoin(url,html.unescape(href)); host=urllib.parse.urlparse(full).netloc.lower().removeprefix('www.')
        if host and host not in {'mortgagematchup.com','maps.google.com','linkedin.com','facebook.com','instagram.com','youtube.com','tiktok.com','nmlsconsumeraccess.org'} and not host.endswith('.google.com'):
            external=full; break
    profiles=[]
    for href in re.findall(r'href=["\']([^"\']*/Profile/[^"\'?#]+)["\']',raw,re.I):
        full=urllib.parse.urljoin(url,html.unescape(href)).rstrip('/')
        if full not in profiles: profiles.append(full)
    # Fallback for pages whose profile cards are rendered into text but links are hidden.
    officers=[]
    for person,oid in re.findall(r'(?:LLC|Inc\.?|Mortgage|Company|Group|Funding|Capital)\s+([A-Z][A-Za-z .\'-]{2,60}?)\s+NMLS\s*#\s*(\d{4,12})',text):
        officers.append({'full_name':person.strip(),'nmls_id':oid})
    return {'legal_name':name,'nmls_id':digits(nmls),'website':external,'phone':phone,'public_email':email,
            'address1':address,'city':city,'state':state,'postal_code':postal,'source_url':url,
            'source_record_id':url,'verification_status':'Mortgage Matchup listing - verify in NMLS',
            'profile_urls':profiles,'embedded_officers':officers}


def parse_profile_page(url: str, raw: str, company_id: int, company_name: str, state_hint: str='') -> dict:
    text=_text(raw)
    name=_match(r'<h3[^>]*>(.*?)</h3>',raw) or _match(r'<title[^>]*>(.*?)</title>',raw).split('|')[0].strip()
    nmls=''; m=re.search(r'NMLS\s*#?:?\s*(\d{4,12})',text,re.I)
    if m: nmls=m.group(1)
    phone=''; pm=re.search(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}',text)
    if pm: phone=digits(pm.group(0))[-10:]
    email=''; em=re.search(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',text,re.I)
    if em: email=em.group(0).lower()
    return {'company_id':company_id,'full_name':name,'normalized_name':normalize(name),'nmls_id':digits(nmls),
            'title':'Mortgage Loan Originator','phone':phone,'public_email':email,'city':'','state':state_hint.upper(),
            'verification_status':'Mortgage Matchup profile - verify in NMLS','source_url':url,'company_name':company_name}


def _upsert_officer(conn: sqlite3.Connection, record: dict) -> tuple[int,bool]:
    if not record.get('full_name'): return 0,False
    key=f"nmls:{record['nmls_id']}" if record.get('nmls_id') else f"officer:{record['company_id']}:{normalize(record['full_name'])}"
    row=conn.execute('select id from warehouse_officers where canonical_key=?',(key,)).fetchone(); now=NOW()
    vals=(record['company_id'],key,record['full_name'],normalize(record['full_name']),record.get('nmls_id',''),record.get('title',''),record.get('phone',''),record.get('public_email',''),record.get('city',''),record.get('state',''),record.get('verification_status','Needs review'),now,now)
    if row:
        conn.execute('''update warehouse_officers set company_id=?,full_name=?,normalized_name=?,nmls_id=?,title=?,phone=?,public_email=?,city=?,state=?,verification_status=?,last_seen_at=?,updated_at=? where id=?''',
                     (record['company_id'],record['full_name'],normalize(record['full_name']),record.get('nmls_id',''),record.get('title',''),record.get('phone',''),record.get('public_email',''),record.get('city',''),record.get('state',''),record.get('verification_status','Needs review'),now,now,int(row[0])))
        return int(row[0]),False
    cur=conn.execute('''insert into warehouse_officers(company_id,canonical_key,full_name,normalized_name,nmls_id,title,phone,public_email,city,state,verification_status,first_seen_at,last_seen_at,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',vals+(now,now))
    return int(cur.lastrowid),True


def ingest_matchup_results(conn: sqlite3.Connection, run_id: int, state: str, limit: int=100) -> dict:
    urls=[str(r[0]) for r in conn.execute("select source_url from public_search_results where run_id=? and source_domain='mortgagematchup.com' and source_url like '%/Company/%' order by id limit ?",(run_id,max(1,min(limit,250)))).fetchall()]
    source_id=create_source(conn,'Mortgage Matchup','Public verified broker directory','Public company/profile pages; verify licensing in NMLS',BASE)
    job_id=create_import_job(conn,source_id,state)
    counts={'company_pages':0,'companies_created':0,'companies_updated':0,'officers_created':0,'officers_updated':0,'failures':[]}
    for url in urls:
        url=_company_url(url)
        if not url: continue
        try:
            company=parse_company_page(url,_fetch(url),state); counts['company_pages']+=1
            result=ingest_companies(conn,job_id,source_id,[company]); counts['companies_created']+=result['created']; counts['companies_updated']+=result['updated']
            company_id=int(conn.execute('select id from warehouse_companies where nmls_id=? order by id desc limit 1',(company['nmls_id'],)).fetchone()[0]) if company['nmls_id'] else int(conn.execute('select id from warehouse_companies where lower(legal_name)=lower(?) order by id desc limit 1',(company['legal_name'],)).fetchone()[0])
            officer_records=[]
            for embedded in company['embedded_officers']:
                officer_records.append({**embedded,'company_id':company_id,'title':'Mortgage Loan Originator','phone':'','public_email':'','city':company['city'],'state':company['state'],'verification_status':'Mortgage Matchup company listing - verify in NMLS'})
            for profile in company['profile_urls'][:100]:
                try: officer_records.append(parse_profile_page(profile,_fetch(profile),company_id,company['legal_name'],company['state']))
                except Exception as exc: counts['failures'].append({'url':profile,'error':str(exc)[:180]})
            seen=set()
            for officer in officer_records:
                key=officer.get('nmls_id') or normalize(officer.get('full_name',''))
                if not key or key in seen: continue
                seen.add(key); _,created=_upsert_officer(conn,officer)
                counts['officers_created' if created else 'officers_updated']+=1
            conn.commit()
        except Exception as exc:
            counts['failures'].append({'url':url,'error':str(exc)[:180]})
    return counts
