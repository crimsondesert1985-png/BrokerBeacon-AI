"""Expose only proven Mortgage Matchup prospects on BrokerBeacon's Prospects screen."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import datetime

from flask import jsonify, request

from autonomous_prospecting import purge_invalid_ember_prospects, promote_warehouse_companies
from mortgage_matchup_ingest import ingest_matchup_results
from public_search_connector import initialize as initialize_search

STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
STATE_SET = set(STATE_CODES)
MATCHUP_SOURCE = "Mortgage Matchup"
NOW = lambda: datetime.now().isoformat(timespec="seconds")
BOOTSTRAP_URLS = (
    "https://mortgagematchup.com/Company/EmeryFinancialInc86755",
    "https://mortgagematchup.com/Company/UhlerMortgageSolutionsInc34857",
    "https://mortgagematchup.com/Profile/rebeccadoesloans",
    "https://mortgagematchup.com/Profile/MajorSingleton38443",
    "https://mortgagematchup.com/Profile/MyloanbyLynn",
    "https://mortgagematchup.com/Profile/SamuelWax27446",
    "https://mortgagematchup.com/Profile/AlexMorgan82853",
)


def install_ember_prospects_bridge(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def seed_bootstrap_urls(conn):
        initialize_search(conn)
        stamp = NOW()
        run_id = int(conn.execute(
            """insert into public_search_runs(state,query_count,result_count,accepted_count,rejected_count,status,created_at,started_at,finished_at)
               values('',1,?,?,0,'Completed',?,?,?)""",
            (len(BOOTSTRAP_URLS), len(BOOTSTRAP_URLS), stamp, stamp, stamp),
        ).lastrowid)
        inserted = 0
        for rank, url in enumerate(BOOTSTRAP_URLS, 1):
            candidate_type = "Company" if "/Company/" in url else "Person"
            cur = conn.execute(
                """insert or ignore into public_search_results(
                   run_id,query_text,result_rank,title,snippet,source_url,source_domain,candidate_type,
                   company_name,person_name,state,nmls_id,phone,public_email,provider_name,review_status,created_at)
                   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id,"Verified Mortgage Matchup bootstrap",rank,"","",url,"mortgagematchup.com",candidate_type,
                 "","","","","","","BrokerBeacon verified seed","Pending review",stamp),
            )
            inserted += int(cur.rowcount > 0)
        conn.commit()
        return run_id, inserted

    def startup_rebuild():
        try:
            with closing(connect()) as conn:
                removed_before = purge_invalid_ember_prospects(conn)
                run_id, inserted = seed_bootstrap_urls(conn)
                ingest = ingest_matchup_results(conn, run_id=run_id, state="", limit=1000)
                promotion = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=80)
                removed_after = purge_invalid_ember_prospects(conn)
                visible = int(conn.execute(
                    """select count(distinct p.id)
                       from prospects p
                       join autonomous_prospect_links link on link.prospect_id=p.id
                       join warehouse_source_records record on record.entity_type='company' and record.entity_id=link.warehouse_company_id
                       join warehouse_sources source on source.id=record.source_id
                       where source.name=?""",
                    (MATCHUP_SOURCE,),
                ).fetchone()[0])
                app.logger.warning(
                    "EMBER_MATCHUP rebuild removed=%s seeded_urls=%s profile_pages=%s companies_seen=%s created=%s updated=%s contacts=%s removed_after=%s visible=%s failures=%s",
                    removed_before, inserted, ingest.get("profile_pages", 0),
                    ingest.get("companies_created", 0) + ingest.get("companies_updated", 0),
                    promotion.get("prospects_created", 0), promotion.get("prospects_updated", 0),
                    promotion.get("contacts_created", 0), removed_after, visible, len(ingest.get("failures", [])),
                )
                for failure in ingest.get("failures", [])[:10]:
                    app.logger.warning("EMBER_MATCHUP ingest failure url=%s error=%s",failure.get("url", ""),failure.get("error", ""))
        except Exception:
            app.logger.exception("EMBER_MATCHUP startup rebuild failed safely")

    threading.Thread(target=startup_rebuild, name="ember-matchup-rebuild", daemon=True).start()

    @app.get("/api/ember/main-prospects")
    def ember_main_prospects():
        requested = str(request.args.get("state") or "").strip().upper()
        state = requested if requested in STATE_SET else ""
        query = str(request.args.get("q") or "").strip()[:120]
        like = f"%{query.lower()}%"
        limit = min(max(int(request.args.get("limit") or 1000), 1), 5000)
        with closing(connect()) as conn:
            rows = conn.execute(
                """select distinct p.*
                   from prospects p
                   join autonomous_prospect_links link on link.prospect_id=p.id
                   join warehouse_source_records record on record.entity_type='company' and record.entity_id=link.warehouse_company_id
                   join warehouse_sources source on source.id=record.source_id
                   where source.name=?
                     and (?='' or upper(trim(coalesce(p.state,'')))=?)
                     and (?='' or lower(coalesce(p.company,'')) like ? or lower(coalesce(p.city,'')) like ? or lower(coalesce(p.nmls,'')) like ?)
                   order by coalesce(p.updated_at,p.created_at,'') desc,p.id desc limit ?""",
                (MATCHUP_SOURCE,state,state,query,like,like,like,limit),
            ).fetchall()
            items=[]
            for p in rows:
                contacts=conn.execute("select * from contacts where prospect_id=? order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id",(p["id"],)).fetchall()
                primary=contacts[0] if contacts else None
                items.append({
                    "id":p["id"],"crm_prospect_id":p["id"],"company_name":p["company"] or "","nmls_id":p["nmls"] or "",
                    "source_url":p["source_url"] or p["website"] or "https://mortgagematchup.com",
                    "phone":p["phone"] or (primary["phone"] if primary else "") or "",
                    "public_email":p["email"] or (primary["email"] if primary else "") or "",
                    "city":p["city"] or "","state":p["state"] or "","review_status":p["verification_status"] or "Verify in NMLS",
                    "pipeline_status":p["status"] or "New","opportunity_score":int(p["score"] or 90),
                    "loan_officer_count":len(contacts),"primary_contact":primary["name"] if primary else "",
                    "source":"Mortgage Matchup","record_type":"crm",
                })
        return jsonify(items=items,states=list(STATE_CODES),count=len(items),selected_state=state,source="mortgage_matchup_provenance_only")

    @app.after_request
    def inject_matchup_prospects(response):
        if response.status_code!=200 or "text/html" not in response.headers.get("Content-Type","").lower():
            return response
        try: page=response.get_data(as_text=True)
        except Exception: return response
        if "ember-matchup-prospects-v5" in page or "</body>" not in page.lower():
            return response
        script=r'''<style id="ember-matchup-prospects-v5-style">tr[data-matchup-prospect="1"] td{background:linear-gradient(90deg,#fff,#f7fbff)}.matchup-badge{display:inline-flex;margin-left:7px;padding:3px 7px;border-radius:999px;background:#4f7cff18;color:#315bb4;font-size:9px;font-weight:900}.matchup-sub{display:block;margin-top:4px;color:#637895;font-size:10px}.matchup-message td{text-align:center;padding:32px;color:#637895}</style><script id="ember-matchup-prospects-v5">(function(){const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const states=new Set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '));function root(){return document.querySelector('#prospects')||document.querySelector('[data-view="prospects"]')||[...document.querySelectorAll('.view,section,main')].find(x=>/prospect/i.test(x.id||'')||/prospect/i.test(x.querySelector('h1,h2')?.textContent||''))}function body(){return root()?.querySelector('#rows,[data-prospect-rows],table tbody')||null}function search(){return root()?.querySelector('#search,[data-prospect-search],input[type="search"]')||null}function state(){return root()?.querySelector('#state,[data-prospect-state],select')||null}function visible(){const r=root();if(!r)return false;const s=getComputedStyle(r);return s.display!=='none'&&s.visibility!=='hidden'}function row(x){const loc=[x.city,x.state].filter(Boolean).join(', ');return `<tr data-matchup-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="matchup-badge">MORTGAGE MATCHUP</span><span class="matchup-sub">${Number(x.loan_officer_count||0)} loan officers${x.nmls_id?` · Company NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${x.phone?`<a href="tel:${esc(x.phone)}">${esc(x.phone)}</a>`:''}${x.public_email?`<a href="mailto:${esc(x.public_email)}">${esc(x.public_email)}</a>`:''}<span class="matchup-sub">${esc(x.primary_contact||'Loan-officer profiles attached')}</span></td><td><span class="pill">Mortgage Matchup</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${Number(x.opportunity_score||90)}</td><td><span class="pill">${esc(x.review_status||'Verify in NMLS')}</span></td><td>${esc(x.pipeline_status||'New')}</td><td><button class="btn smallbtn" data-open-prospect="${Number(x.crm_prospect_id)}">Open</button></td></tr>`}let timer=0;async function load(){const b=body();if(!b||!visible())return;const st=states.has((state()?.value||'').toUpperCase())?state().value.toUpperCase():'';const q=search()?.value||'';b.innerHTML='<tr class="matchup-message"><td colspan="9">Loading verified Mortgage Matchup prospects…</td></tr>';try{const r=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(st)+'&q='+encodeURIComponent(q),{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();b.innerHTML=(d.items||[]).length?d.items.map(row).join(''):'<tr class="matchup-message"><td colspan="9">No verified Mortgage Matchup prospects yet. Ember is rebuilding the directory now.</td></tr>'}catch(e){b.innerHTML='<tr class="matchup-message"><td colspan="9">Mortgage Matchup prospects could not be loaded. Retrying automatically.</td></tr>'}}function bind(){if(!body())return;const q=search(),s=state();if(q&&!q.dataset.matchupBound){q.dataset.matchupBound='1';q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)})}if(s&&!s.dataset.matchupBound){s.dataset.matchupBound='1';s.addEventListener('change',load)}body().addEventListener('click',e=>{const btn=e.target.closest('[data-open-prospect]');if(!btn)return;const id=Number(btn.dataset.openProspect);if(typeof window.openProfile==='function')window.openProfile(id)});load()}const observer=new MutationObserver(()=>{if(visible()&&body())bind()});observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();setInterval(load,60000);})();</script>'''
        pos=page.lower().rfind("</body>")
        page=page[:pos]+script+page[pos:]
        response.set_data(page)
        response.headers["Content-Length"]=str(len(response.get_data()))
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
        return response

    return app


__all__=["install_ember_prospects_bridge"]
