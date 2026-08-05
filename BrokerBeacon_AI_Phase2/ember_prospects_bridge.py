"""Expose only Mortgage Matchup-backed Ember CRM prospects on the Prospects screen."""
from __future__ import annotations
import sqlite3
from contextlib import closing
from flask import jsonify,request
from autonomous_prospecting import purge_invalid_ember_prospects,promote_warehouse_companies

STATE_CODES=tuple('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split())
STATE_SET=set(STATE_CODES)

def install_ember_prospects_bridge(app,db_path):
    def connect():
        conn=sqlite3.connect(str(db_path),timeout=30); conn.row_factory=sqlite3.Row; conn.execute('pragma busy_timeout=30000'); return conn
    # Immediate cleanup/backfill: no generic search-result prospects survive startup.
    try:
        with closing(connect()) as conn:
            removed=purge_invalid_ember_prospects(conn)
            backfill=promote_warehouse_companies(conn,state='',limit=500,minimum_score=50)
            app.logger.warning('EMBER_MATCHUP startup cleanup removed=%s created=%s updated=%s contacts=%s',removed,backfill.get('prospects_created',0),backfill.get('prospects_updated',0),backfill.get('contacts_created',0))
    except Exception:
        app.logger.exception('EMBER_MATCHUP startup cleanup/backfill failed safely')

    @app.get('/api/ember/main-prospects')
    def ember_main_prospects():
        requested=str(request.args.get('state') or '').strip().upper(); state=requested if requested in STATE_SET else ''
        query=str(request.args.get('q') or '').strip()[:120]; like=f'%{query.lower()}%'; limit=min(max(int(request.args.get('limit') or 1000),1),5000)
        with closing(connect()) as conn:
            rows=conn.execute("""select p.* from prospects p
              where lower(trim(coalesce(p.source_name,'')))='mortgage matchup via ember'
                and (?='' or upper(trim(coalesce(p.state,'')))=?)
                and (?='' or lower(coalesce(p.company,'')) like ? or lower(coalesce(p.city,'')) like ? or lower(coalesce(p.nmls,'')) like ?)
              order by coalesce(p.updated_at,p.created_at,'') desc,p.id desc limit ?""",(state,state,query,like,like,like,limit)).fetchall()
            items=[]
            for p in rows:
                contacts=conn.execute('select * from contacts where prospect_id=? order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id',(p['id'],)).fetchall()
                primary=contacts[0] if contacts else None
                items.append({'id':p['id'],'crm_prospect_id':p['id'],'company_name':p['company'],'nmls_id':p['nmls'] or '',
                    'source_url':p['source_url'] or p['website'] or 'https://mortgagematchup.com','phone':p['phone'] or (primary['phone'] if primary else '') or '',
                    'public_email':p['email'] or (primary['email'] if primary else '') or '','city':p['city'] or '','state':p['state'] or '',
                    'review_status':p['verification_status'] or 'Verify in NMLS','pipeline_status':p['status'] or 'New','opportunity_score':int(p['score'] or 80),
                    'loan_officer_count':len(contacts),'primary_contact':primary['name'] if primary else '','source':'Mortgage Matchup via Ember','record_type':'crm'})
        return jsonify(items=items,states=list(STATE_CODES),count=len(items),selected_state=state,source='mortgage_matchup_only')

    @app.after_request
    def inject(response):
        if response.status_code!=200 or 'text/html' not in response.headers.get('Content-Type','').lower(): return response
        try: page=response.get_data(as_text=True)
        except Exception: return response
        if 'ember-matchup-prospects' in page or '</body>' not in page.lower(): return response
        script=r'''<script id="ember-matchup-prospects">(function(){
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function root(){return document.querySelector('#prospects')||[...document.querySelectorAll('.view,section')].find(x=>/prospect/i.test(x.id||'')||/prospect/i.test(x.querySelector('h1,h2')?.textContent||''))}
function body(){return root()?.querySelector('#rows,tbody,[data-prospect-rows]')||document.querySelector('#rows')}
function search(){return root()?.querySelector('#search,input[type="search"],[data-prospect-search]')}
function state(){return root()?.querySelector('#state,select[data-prospect-state]')}
function row(x){const loc=[x.city,x.state].filter(Boolean).join(', ');return `<tr data-ember-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="ember-badge">MATCHUP</span><span class="ember-sub">${x.loan_officer_count} loan officers${x.nmls_id?` · NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${x.phone?`<a href="tel:${esc(x.phone)}">${esc(x.phone)}</a>`:''}${x.public_email?`<a href="mailto:${esc(x.public_email)}">${esc(x.public_email)}</a>`:''}<span class="ember-sub">${esc(x.primary_contact||'Contact research pending')}</span></td><td><span class="pill">Mortgage Matchup</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${x.opportunity_score}</td><td><span class="pill">${esc(x.review_status)}</span></td><td>${esc(x.pipeline_status)}</td><td><button class="btn smallbtn" onclick="openProfile(${Number(x.crm_prospect_id)})">Open</button></td></tr>`}
let timer=0;async function load(){const b=body();if(!b)return;const st=(state()?.value||''),q=(search()?.value||'');b.innerHTML='<tr><td colspan="9">Loading Mortgage Matchup prospects…</td></tr>';try{const r=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(st)+'&q='+encodeURIComponent(q),{cache:'no-store'}),d=await r.json();b.innerHTML=d.items.length?d.items.map(row).join(''):'<tr><td colspan="9">No Mortgage Matchup prospects for this filter yet.</td></tr>'}catch(e){b.innerHTML='<tr><td colspan="9">Unable to load Mortgage Matchup prospects.</td></tr>'}}
function wire(){if(!body())return;state()?.addEventListener('change',load);search()?.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)});load()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();setInterval(load,300000);
})();</script>'''
        pos=page.lower().rfind('</body>'); page=page[:pos]+script+page[pos:]; response.set_data(page); response.headers['Content-Length']=str(len(response.get_data())); return response
    return app

__all__=['install_ember_prospects_bridge']
