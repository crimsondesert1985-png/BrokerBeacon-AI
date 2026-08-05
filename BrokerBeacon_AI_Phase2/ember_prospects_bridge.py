"""Serve a clean nationwide prospect catalog and keep it populated from trusted records."""
from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime

from flask import jsonify, request

STATE_CODES=tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY".split())
STATE_SET=set(STATE_CODES)
NOW=lambda: datetime.now().isoformat(timespec="seconds")
GENERIC_PATTERNS=(
    "annual report","best mortgage brokers","top loan officers","broker near me",
    "department of savings","division of banks","real estate in ","nmls esb",
    "cyber — fbi","cyber - fbi","mortgage lenders & loan officers",
    "mortgage broker directory","search results","consumer access",
)


def _norm(value):
    return re.sub(r"[^a-z0-9]+"," ",str(value or "").lower()).strip()


def _cols(conn,table):
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _insert_dynamic(conn,table,values):
    cols=_cols(conn,table); payload={k:v for k,v in values.items() if k in cols}
    names=list(payload)
    cur=conn.execute(f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})",tuple(payload[n] for n in names))
    return int(cur.lastrowid)


def _is_generic_name(name):
    value=_norm(name)
    return not value or any(pattern in value for pattern in GENERIC_PATTERNS)


def install_ember_prospects_bridge(app,db_path):
    def connect():
        conn=sqlite3.connect(str(db_path),timeout=30); conn.row_factory=sqlite3.Row
        conn.execute("pragma foreign_keys=on"); conn.execute("pragma busy_timeout=30000")
        return conn

    def clean_bad_ember_rows(conn):
        rows=conn.execute("select id,company,source_name,source_url from prospects").fetchall()
        bad=[]
        for row in rows:
            source=_norm(row["source_name"])
            if source.startswith("ember") and _is_generic_name(row["company"]): bad.append(int(row["id"]))
        if bad:
            marks=','.join('?' for _ in bad)
            conn.execute(f"delete from contacts where prospect_id in ({marks})",bad)
            conn.execute(f"delete from autonomous_prospect_links where prospect_id in ({marks})",bad)
            conn.execute(f"delete from prospects where id in ({marks})",bad)
            conn.commit()
        return len(bad)

    def find_prospect(conn,company):
        nmls=re.sub(r"\D+","",str(company["nmls_id"] or ""))
        if nmls:
            row=conn.execute("select * from prospects where replace(replace(coalesce(nmls,''),'-',''),' ','')=? limit 1",(nmls,)).fetchone()
            if row:return row
        state=str(company["state"] or "").upper(); name=_norm(company["legal_name"])
        for row in conn.execute("select * from prospects where upper(coalesce(state,''))=?",(state,)).fetchall():
            if _norm(row["company"])==name:return row
        return None

    def promote_trusted(conn,target=500):
        current=int(conn.execute("select count(*) from prospects where trim(coalesce(company,''))<>''").fetchone()[0])
        needed=max(0,target-current)
        if not needed:return {"created":0,"contacts":0,"examined":0,"current":current}
        rows=conn.execute("""select distinct c.* from warehouse_companies c
          join warehouse_source_records wr on wr.entity_type='company' and wr.entity_id=c.id
          join warehouse_sources s on s.id=wr.source_id
          where trim(coalesce(c.nmls_id,''))<>'' and upper(trim(coalesce(c.state,''))) in (%s)
            and lower(coalesce(s.name,'')) not like '%%public search%%'
            and lower(coalesce(s.name,'')) not like '%%web search%%'
          order by case when trim(coalesce(c.phone,''))<>'' or trim(coalesce(c.public_email,''))<>'' then 0 else 1 end,
                   c.source_count desc,c.id desc limit ?""" % ','.join('?' for _ in STATE_CODES),tuple(STATE_CODES)+(max(needed*3,needed),)).fetchall()
        created=contacts=examined=0; now=NOW()
        for company in rows:
            if created>=needed:break
            examined+=1
            if _is_generic_name(company["legal_name"]):continue
            existing=find_prospect(conn,company)
            if existing:continue
            values={"company":company["legal_name"],"nmls":company["nmls_id"],"website":company["website"],
                    "phone":company["phone"],"email":company["public_email"],"city":company["city"],"state":company["state"],
                    "status":"New","score":75,"signal":"Trusted NMLS-backed broker record","source_name":"BrokerBeacon verified warehouse",
                    "source_url":company["website"] or "","verification_status":"Verify in NMLS before outreach",
                    "ai_summary":"NMLS-backed mortgage company imported from a trusted BrokerBeacon source.",
                    "next_best_action":"Verify licensing and decision-maker contact details before outreach.",
                    "created_at":now,"updated_at":now}
            pid=_insert_dynamic(conn,"prospects",values); created+=1
            for officer in conn.execute("select * from warehouse_officers where company_id=? order by id limit 50",(company["id"],)).fetchall():
                if not str(officer["full_name"] or "").strip():continue
                _insert_dynamic(conn,"contacts",{"prospect_id":pid,"name":officer["full_name"],"title":officer["title"] or "Mortgage Loan Originator",
                    "email":officer["public_email"],"phone":officer["phone"],"nmls":officer["nmls_id"],"city":officer["city"],"state":officer["state"],
                    "roster_status":"Needs review","source_name":"BrokerBeacon verified warehouse","created_at":now,"updated_at":now})
                contacts+=1
        conn.commit()
        total=int(conn.execute("select count(*) from prospects where trim(coalesce(company,''))<>''").fetchone()[0])
        return {"created":created,"contacts":contacts,"examined":examined,"current":total}

    def startup_rebuild():
        try:
            with closing(connect()) as conn:
                removed=clean_bad_ember_rows(conn)
                promotion=promote_trusted(conn,500)
                state_counts=dict(conn.execute("select upper(state),count(*) from prospects where upper(state) in (%s) group by upper(state)" % ','.join('?' for _ in STATE_CODES),STATE_CODES).fetchall())
                app.logger.warning("PROSPECT_CATALOG rebuild removed_generic=%s examined=%s created=%s contacts=%s visible_total=%s states=%s",
                    removed,promotion["examined"],promotion["created"],promotion["contacts"],promotion["current"],len(state_counts))
        except Exception:
            app.logger.exception("PROSPECT_CATALOG startup rebuild failed")
    threading.Thread(target=startup_rebuild,name="prospect-catalog-rebuild",daemon=True).start()

    @app.get("/api/ember/main-prospects")
    def main_prospects():
        requested=str(request.args.get("state") or "").strip().upper(); state=requested if requested in STATE_SET else ""
        query=str(request.args.get("q") or "").strip()[:120]; like=f"%{query.lower()}%"; limit=min(max(int(request.args.get("limit") or 1000),1),5000)
        with closing(connect()) as conn:
            rows=conn.execute("""select p.* from prospects p where trim(coalesce(p.company,''))<>''
              and (?='' or upper(trim(coalesce(p.state,'')))=?)
              and (?='' or lower(coalesce(p.company,'')) like ? or lower(coalesce(p.city,'')) like ? or lower(coalesce(p.nmls,'')) like ?)
              order by upper(coalesce(p.state,'')),lower(p.company),p.id limit ?""",(state,state,query,like,like,like,limit)).fetchall()
            items=[]
            for p in rows:
                if _is_generic_name(p["company"]):continue
                contacts=conn.execute("select * from contacts where prospect_id=? order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id",(p["id"],)).fetchall(); primary=contacts[0] if contacts else None
                source=p["source_name"] or "BrokerBeacon CRM"
                items.append({"id":p["id"],"crm_prospect_id":p["id"],"company_name":p["company"],"nmls_id":p["nmls"] or "",
                    "source_url":p["source_url"] or p["website"] or "","phone":p["phone"] or (primary["phone"] if primary else "") or "",
                    "public_email":p["email"] or (primary["email"] if primary else "") or "","city":p["city"] or "","state":p["state"] or "",
                    "review_status":p["verification_status"] or "Verify in NMLS","pipeline_status":p["status"] or "New",
                    "opportunity_score":int(p["score"] or 75),"loan_officer_count":len(contacts),"primary_contact":primary["name"] if primary else "",
                    "source":source,"record_type":"crm"})
            coverage={row[0]:int(row[1]) for row in conn.execute("select upper(state),count(*) from prospects where upper(state) in (%s) group by upper(state)" % ','.join('?' for _ in STATE_CODES),STATE_CODES).fetchall()}
        return jsonify(items=items,states=list(STATE_CODES),coverage=coverage,count=len(items),selected_state=state,source="clean_crm_and_trusted_warehouse")

    @app.after_request
    def inject(response):
        if response.status_code!=200 or "text/html" not in response.headers.get("Content-Type","").lower():return response
        try: page=response.get_data(as_text=True)
        except Exception:return response
        if "brokerbeacon-clean-prospects-v7" in page or "</body>" not in page.lower():return response
        script=r'''<style id="brokerbeacon-clean-prospects-v7-style">.bb-sub{display:block;margin-top:4px;color:#637895;font-size:10px}.bb-badge{display:inline-flex;margin-left:7px;padding:3px 7px;border-radius:999px;background:#4f7cff18;color:#315bb4;font-size:9px;font-weight:900}.bb-message td{text-align:center;padding:32px;color:#637895}</style><script id="brokerbeacon-clean-prospects-v7">(function(){const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const states=new Set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY'.split(' '));function root(){return document.querySelector('#prospects')||document.querySelector('[data-view="prospects"]')||[...document.querySelectorAll('.view,section,main')].find(x=>/prospect/i.test(x.id||'')||/prospect/i.test(x.querySelector('h1,h2')?.textContent||''))}function body(){return root()?.querySelector('#rows,[data-prospect-rows],table tbody')||null}function search(){return root()?.querySelector('#search,[data-prospect-search],input[type="search"]')||null}function state(){return root()?.querySelector('#state,[data-prospect-state],select')||null}function visible(){const r=root();if(!r)return false;const s=getComputedStyle(r);return s.display!=='none'&&s.visibility!=='hidden'}function row(x){const loc=[x.city,x.state].filter(Boolean).join(', ');return `<tr data-clean-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="bb-badge">VERIFIED CRM</span><span class="bb-sub">${Number(x.loan_officer_count||0)} contacts${x.nmls_id?` · NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${x.phone?`<a href="tel:${esc(x.phone)}">${esc(x.phone)}</a>`:''}${x.public_email?`<a href="mailto:${esc(x.public_email)}">${esc(x.public_email)}</a>`:''}<span class="bb-sub">${esc(x.primary_contact||'Contact research pending')}</span></td><td><span class="pill">${esc(x.source||'BrokerBeacon')}</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${Number(x.opportunity_score||75)}</td><td><span class="pill">${esc(x.review_status||'Verify in NMLS')}</span></td><td>${esc(x.pipeline_status||'New')}</td><td><button class="btn smallbtn" data-open-prospect="${Number(x.crm_prospect_id)}">Open</button></td></tr>`}let timer=0;async function load(){const b=body();if(!b||!visible())return;const st=states.has((state()?.value||'').toUpperCase())?state().value.toUpperCase():'';const q=search()?.value||'';b.innerHTML='<tr class="bb-message"><td colspan="9">Loading BrokerBeacon prospects…</td></tr>';try{const r=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(st)+'&q='+encodeURIComponent(q),{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();b.innerHTML=(d.items||[]).length?d.items.map(row).join(''):'<tr class="bb-message"><td colspan="9">No prospects match this filter.</td></tr>'}catch(e){b.innerHTML='<tr class="bb-message"><td colspan="9">Prospects could not be loaded. Retrying automatically.</td></tr>'}}function bind(){if(!body())return;const q=search(),s=state();if(q&&!q.dataset.bbBound){q.dataset.bbBound='1';q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)})}if(s&&!s.dataset.bbBound){s.dataset.bbBound='1';s.addEventListener('change',load)}body().addEventListener('click',e=>{const btn=e.target.closest('[data-open-prospect]');if(!btn)return;const id=Number(btn.dataset.openProspect);if(typeof window.openProfile==='function')window.openProfile(id)});load()}const observer=new MutationObserver(()=>{if(visible()&&body())bind()});observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();setInterval(load,60000);})();</script>'''
        pos=page.lower().rfind("</body>");page=page[:pos]+script+page[pos:];response.set_data(page)
        response.headers["Content-Length"]=str(len(response.get_data()));response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0";return response
    return app

__all__=["install_ember_prospects_bridge"]
