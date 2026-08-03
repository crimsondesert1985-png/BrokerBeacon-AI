"""Bridge Ember company discoveries into the legacy main Prospects screen."""
from __future__ import annotations

import sqlite3
from flask import jsonify, request

from broker_company_contacts import sync_company_contacts


def install_ember_prospects_bridge(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout=30000")
        return conn

    @app.get("/api/ember/main-prospects")
    def ember_main_prospects():
        state = str(request.args.get("state") or "").strip().upper()[:2]
        query = str(request.args.get("q") or "").strip()[:120]
        limit = min(max(int(request.args.get("limit") or 500), 1), 2000)
        with connect() as conn:
            sync_company_contacts(conn, state=state)
            where = ["trim(coalesce(d.person_name,''))=''", "trim(coalesce(d.company_name,''))<>''"]
            args: list[object] = []
            if state:
                where.append("upper(d.state)=?")
                args.append(state)
            if query:
                like = f"%{query}%"
                where.append("(d.company_name like ? or d.city like ? or d.state like ? or d.nmls_id like ? or d.public_email like ? or d.phone like ?)")
                args.extend([like] * 6)
            args.append(limit)
            rows = conn.execute(
                """select d.id,d.company_name,d.phone,d.public_email,d.city,d.state,d.nmls_id,
                          d.source_url,d.source_domain,d.review_status,d.confidence,d.created_at,
                          coalesce(a.opportunity_score,0) opportunity_score,
                          (select count(*) from discovered_contacts p
                            where p.source_domain=d.source_domain and trim(coalesce(p.person_name,''))<>'') loan_officer_count,
                          (select p.person_name from discovered_contacts p
                            where p.source_domain=d.source_domain and trim(coalesce(p.person_name,''))<>''
                            order by p.confidence desc,p.id desc limit 1) primary_contact
                   from discovered_contacts d
                   left join ai_contact_insights a on a.discovered_contact_id=d.id
                   where """ + " and ".join(where) +
                " order by opportunity_score desc,d.confidence desc,d.id desc limit ?",
                args,
            ).fetchall()
            states = [r[0] for r in conn.execute(
                "select distinct upper(state) from discovered_contacts where trim(coalesce(state,''))<>'' order by upper(state)"
            ).fetchall()]
        return jsonify(items=[dict(r) for r in rows], states=states, count=len(rows))

    @app.after_request
    def inject_ember_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-main-prospects-bridge" in body or "</body>" not in body.lower():
            return response
        script = r'''<style id="ember-main-prospects-bridge-style">
tr[data-ember-prospect="1"] td{background:linear-gradient(90deg,#fff,#f6fbff)}
tr[data-ember-prospect="1"]:hover td{background:#eef7ff}.ember-new{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#ff784918;color:#b54b20;font-size:9px;font-weight:900}.ember-lo{display:block;margin-top:4px;color:#637895;font-size:10px}.dark-mode tr[data-ember-prospect="1"] td{background:#12233d}.dark-mode tr[data-ember-prospect="1"]:hover td{background:#17304f}
</style><script id="ember-main-prospects-bridge">(function(){
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const txt=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
function prospectRoot(){return [...document.querySelectorAll('.view,main,section')].find(x=>x.offsetParent!==null&&/\bProspects\b/i.test(txt(x.querySelector('h1,h2'))))}
function controls(root){const sels=[...root.querySelectorAll('select')];const state=sels.find(s=>[...s.options].some(o=>/^(NC|SC|CA|TX|FL)$/.test(o.value||o.textContent.trim())))||sels[0];const search=root.querySelector('input[placeholder*="company" i],input[placeholder*="search" i]');return{state,search}}
function table(root){return root.querySelector('table tbody')}
function row(x){const score=x.opportunity_score||x.confidence||50,contact=x.primary_contact||'Primary contact not named',phone=x.phone||'',email=x.public_email||'',loc=[x.city,x.state].filter(Boolean).join(', '),verify=(email||phone)?'Public contact verified':'Needs verification';return `<tr data-ember-prospect="1" data-state="${esc(x.state)}"><td><strong data-company>${esc(x.company_name)}</strong><span class="ember-new">EMBER</span><span class="ember-lo">${x.loan_officer_count||0} loan officer${x.loan_officer_count===1?'':'s'} attached</span></td><td class="contact-cell">${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="contact-missing">${esc(contact)}</span><div class="contact-actions">${phone?`<a class="btn smallbtn" href="tel:${esc(phone)}">☎ Call</a>`:''}${email?`<a class="btn smallbtn" href="mailto:${esc(email)}">✉ Email</a>`:''}${x.source_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.source_url)}">↗ Website</a>`:''}</div></td><td><span class="pill">Ember discovery</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${score}</td><td><span class="pill">${esc(verify)}</span></td><td>${esc(x.review_status||'New')}</td><td><button class="btn smallbtn" onclick="location.href='/platform/details/contacts?q=${encodeURIComponent(x.company_name)}'">Intelligence</button></td></tr>`}
let timer=0,last='';async function load(){const root=prospectRoot(),body=root&&table(root);if(!root||!body)return;const c=controls(root),state=(c.state?.value||'').toUpperCase(),q=c.search?.value||'',key=state+'|'+q;if(key===last&&body.querySelector('[data-ember-prospect]'))return;last=key;try{const r=await fetch('/api/ember/main-prospects?limit=1000&state='+encodeURIComponent(state==='ALL'?'':state)+'&q='+encodeURIComponent(q));const d=await r.json();body.querySelectorAll('[data-ember-prospect="1"]').forEach(n=>n.remove());body.insertAdjacentHTML('beforeend',(d.items||[]).map(row).join(''));if(c.state){const existing=new Set([...c.state.options].map(o=>(o.value||o.textContent).toUpperCase()));for(const s of d.states||[]){if(!existing.has(s)){const o=document.createElement('option');o.value=s;o.textContent=s;c.state.appendChild(o)}}}root.querySelectorAll('[data-ember-count]').forEach(n=>n.textContent=d.count||0)}catch(e){console.error('Ember prospects bridge',e)}}
function wire(){const root=prospectRoot();if(!root)return;const c=controls(root);if(c.state&&!c.state.dataset.emberWired){c.state.dataset.emberWired='1';c.state.addEventListener('change',()=>{last='';load()})}if(c.search&&!c.search.dataset.emberWired){c.search.dataset.emberWired='1';c.search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{last='';load()},250)})}load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true});setInterval(wire,15000);
})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
