"""Expose only proven Mortgage Matchup prospects on BrokerBeacon's Prospects screen."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing

from flask import jsonify, request

from autonomous_prospecting import purge_invalid_ember_prospects, promote_warehouse_companies
from mortgage_matchup_ingest import ingest_matchup_results

STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
STATE_SET = set(STATE_CODES)
MATCHUP_SOURCE = "Mortgage Matchup"


def install_ember_prospects_bridge(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def startup_rebuild():
        try:
            with closing(connect()) as conn:
                removed_before = purge_invalid_ember_prospects(conn)
                ingest = ingest_matchup_results(conn, run_id=0, state="", limit=500)
                promotion = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=80)
                removed_after = purge_invalid_ember_prospects(conn)
                visible = int(conn.execute(
                    """select count(distinct p.id)
                       from prospects p
                       join autonomous_prospect_links link on link.prospect_id=p.id
                       join warehouse_source_records record
                         on record.entity_type='company' and record.entity_id=link.warehouse_company_id
                       join warehouse_sources source on source.id=record.source_id
                       where source.name=?""",
                    (MATCHUP_SOURCE,),
                ).fetchone()[0])
                app.logger.warning(
                    "EMBER_MATCHUP rebuild removed=%s ingested_profiles=%s ingested_companies=%s "
                    "created=%s updated=%s contacts=%s removed_after=%s visible=%s failures=%s",
                    removed_before,
                    ingest.get("profile_pages", 0),
                    ingest.get("companies_created", 0) + ingest.get("companies_updated", 0),
                    promotion.get("prospects_created", 0),
                    promotion.get("prospects_updated", 0),
                    promotion.get("contacts_created", 0),
                    removed_after,
                    visible,
                    len(ingest.get("failures", [])),
                )
                for failure in ingest.get("failures", [])[:10]:
                    app.logger.warning(
                        "EMBER_MATCHUP ingest failure url=%s error=%s",
                        failure.get("url", ""), failure.get("error", ""),
                    )
        except Exception:
            app.logger.exception("EMBER_MATCHUP startup rebuild failed safely")

    # Run after Gunicorn has completed import so startup is not blocked by network I/O.
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
                   join warehouse_source_records record
                     on record.entity_type='company' and record.entity_id=link.warehouse_company_id
                   join warehouse_sources source on source.id=record.source_id
                   where source.name=?
                     and (?='' or upper(trim(coalesce(p.state,'')))=?)
                     and (?='' or lower(coalesce(p.company,'')) like ?
                              or lower(coalesce(p.city,'')) like ?
                              or lower(coalesce(p.nmls,'')) like ?)
                   order by coalesce(p.updated_at,p.created_at,'') desc,p.id desc limit ?""",
                (MATCHUP_SOURCE, state, state, query, like, like, like, limit),
            ).fetchall()
            items = []
            for prospect in rows:
                contacts = conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id""",
                    (prospect["id"],),
                ).fetchall()
                primary = contacts[0] if contacts else None
                items.append({
                    "id": prospect["id"],
                    "crm_prospect_id": prospect["id"],
                    "company_name": prospect["company"] or "",
                    "nmls_id": prospect["nmls"] or "",
                    "source_url": prospect["source_url"] or prospect["website"] or "https://mortgagematchup.com",
                    "phone": prospect["phone"] or (primary["phone"] if primary else "") or "",
                    "public_email": prospect["email"] or (primary["email"] if primary else "") or "",
                    "city": prospect["city"] or "",
                    "state": prospect["state"] or "",
                    "review_status": prospect["verification_status"] or "Verify in NMLS",
                    "pipeline_status": prospect["status"] or "New",
                    "opportunity_score": int(prospect["score"] or 90),
                    "loan_officer_count": len(contacts),
                    "primary_contact": primary["name"] if primary else "",
                    "source": "Mortgage Matchup",
                    "record_type": "crm",
                })
        return jsonify(
            items=items,
            states=list(STATE_CODES),
            count=len(items),
            selected_state=state,
            source="mortgage_matchup_provenance_only",
        )

    @app.after_request
    def inject_matchup_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            page = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-matchup-prospects-v3" in page or "</body>" not in page.lower():
            return response
        script = r'''<style id="ember-matchup-prospects-v3-style">
tr[data-matchup-prospect="1"] td{background:linear-gradient(90deg,#fff,#f7fbff)}
.matchup-badge{display:inline-flex;margin-left:7px;padding:3px 7px;border-radius:999px;background:#4f7cff18;color:#315bb4;font-size:9px;font-weight:900}
.matchup-sub{display:block;margin-top:4px;color:#637895;font-size:10px}
.matchup-message td{text-align:center;padding:32px;color:#637895}
</style><script id="ember-matchup-prospects-v3">(function(){
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const stateCodes=new Set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '));
function root(){return document.querySelector('#prospects')||document.querySelector('[data-view="prospects"]')||[...document.querySelectorAll('.view,section,main')].find(x=>/prospect/i.test(x.id||'')||/prospect/i.test(x.querySelector('h1,h2')?.textContent||''))}
function tableBody(){const r=root();return r?.querySelector('#rows,[data-prospect-rows],table tbody')||null}
function searchBox(){const r=root();return r?.querySelector('#search,[data-prospect-search],input[type="search"]')||null}
function stateBox(){const r=root();return r?.querySelector('#state,[data-prospect-state],select')||null}
function visible(){const r=root();if(!r)return false;const s=getComputedStyle(r);return s.display!=='none'&&s.visibility!=='hidden'}
function row(x){const loc=[x.city,x.state].filter(Boolean).join(', ');const phone=x.phone||'',email=x.public_email||'';return `<tr data-matchup-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="matchup-badge">MORTGAGE MATCHUP</span><span class="matchup-sub">${Number(x.loan_officer_count||0)} loan officer${Number(x.loan_officer_count||0)===1?'':'s'}${x.nmls_id?` · Company NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="matchup-sub">${esc(x.primary_contact||'Loan-officer profiles attached below')}</span></td><td><span class="pill">Mortgage Matchup</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${Number(x.opportunity_score||90)}</td><td><span class="pill">${esc(x.review_status||'Verify in NMLS')}</span></td><td>${esc(x.pipeline_status||'New')}</td><td><button class="btn smallbtn" data-open-prospect="${Number(x.crm_prospect_id)}">Open</button></td></tr>`}
let seq=0,timer=0,lastKey='';
async function load(force=false){const body=tableBody();if(!body||!visible())return;const state=stateBox();const search=searchBox();const st=stateCodes.has((state?.value||'').toUpperCase())?state.value.toUpperCase():'';const q=search?.value||'';const key=st+'|'+q;if(!force&&key===lastKey&&body.querySelector('[data-matchup-prospect="1"]'))return;lastKey=key;const id=++seq;body.innerHTML='<tr class="matchup-message"><td colspan="9">Loading verified Mortgage Matchup prospects…</td></tr>';try{const response=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(st)+'&q='+encodeURIComponent(q),{cache:'no-store',credentials:'same-origin'});if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();if(id!==seq)return;body.innerHTML=(data.items||[]).length?data.items.map(row).join(''):'<tr class="matchup-message"><td colspan="9">No verified Mortgage Matchup prospects for this filter yet. Ember is continuing the directory build.</td></tr>';}catch(error){body.innerHTML='<tr class="matchup-message"><td colspan="9">Mortgage Matchup prospects could not be loaded. The service will retry automatically.</td></tr>';}}
function bind(){const search=searchBox(),state=stateBox(),body=tableBody();if(!body)return;if(search&&!search.dataset.matchupBound){search.dataset.matchupBound='1';search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>load(true),250)})}if(state&&!state.dataset.matchupBound){state.dataset.matchupBound='1';state.addEventListener('change',()=>load(true))}body.addEventListener('click',event=>{const button=event.target.closest('[data-open-prospect]');if(!button)return;const id=Number(button.dataset.openProspect);if(typeof window.openProfile==='function')window.openProfile(id);else location.href='/#prospects';});load(true)}
const observer=new MutationObserver(()=>{if(visible()&&tableBody())bind()});observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
setInterval(()=>load(true),60000);
})();</script>'''
        position = page.lower().rfind("</body>")
        page = page[:position] + script + page[position:]
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
