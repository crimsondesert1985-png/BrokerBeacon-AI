"""Bridge Ember company discoveries into the legacy main Prospects screen."""
from __future__ import annotations

import sqlite3
from flask import jsonify, request

from broker_company_contacts import sync_company_contacts

STATE_CODES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
}


def install_ember_prospects_bridge(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout=30000")
        return conn

    @app.get("/api/ember/main-prospects")
    def ember_main_prospects():
        raw_state = str(request.args.get("state") or "").strip().upper()
        state = raw_state if raw_state in STATE_CODES else ""
        query = str(request.args.get("q") or "").strip()[:120]
        limit = min(max(int(request.args.get("limit") or 500), 1), 2000)
        with connect() as conn:
            sync_company_contacts(conn, state=state)
            filters = ["trim(coalesce(d.company_name,''))<>''"]
            args: list[object] = []
            if state:
                filters.append("upper(trim(coalesce(d.state,'')))=?")
                args.append(state)
            if query:
                like = f"%{query}%"
                filters.append(
                    "(d.company_name like ? or d.city like ? or d.state like ? or d.nmls_id like ? "
                    "or d.public_email like ? or d.phone like ? or d.source_domain like ?)"
                )
                args.extend([like] * 7)
            args.append(limit)
            rows = conn.execute(
                """
                with company_rows as (
                    select d.*,
                           lower(trim(coalesce(d.company_name,''))) company_key,
                           lower(trim(coalesce(d.source_domain,''))) domain_key,
                           row_number() over (
                               partition by upper(trim(coalesce(d.state,''))),
                                            case when trim(coalesce(d.source_domain,''))<>''
                                                 then lower(trim(d.source_domain))
                                                 else lower(trim(d.company_name)) end
                               order by case when trim(coalesce(d.person_name,''))='' then 0 else 1 end,
                                        d.confidence desc,d.id desc
                           ) company_rank
                    from discovered_contacts d
                    where """ + " and ".join(filters) + """
                ),
                selected as (
                    select * from company_rows where company_rank=1
                )
                select d.id,d.company_name,
                       coalesce(nullif(trim(d.phone),''),(
                           select nullif(trim(p.phone),'') from discovered_contacts p
                           where trim(coalesce(p.person_name,''))<>''
                             and upper(trim(coalesce(p.state,'')))=upper(trim(coalesce(d.state,'')))
                             and ((d.domain_key<>'' and lower(trim(coalesce(p.source_domain,'')))=d.domain_key)
                                  or lower(trim(coalesce(p.company_name,'')))=d.company_key)
                             and trim(coalesce(p.phone,''))<>''
                           order by p.confidence desc,p.id desc limit 1
                       ),'') phone,
                       coalesce(nullif(trim(d.public_email),''),(
                           select nullif(trim(p.public_email),'') from discovered_contacts p
                           where trim(coalesce(p.person_name,''))<>''
                             and upper(trim(coalesce(p.state,'')))=upper(trim(coalesce(d.state,'')))
                             and ((d.domain_key<>'' and lower(trim(coalesce(p.source_domain,'')))=d.domain_key)
                                  or lower(trim(coalesce(p.company_name,'')))=d.company_key)
                             and trim(coalesce(p.public_email,''))<>''
                           order by p.confidence desc,p.id desc limit 1
                       ),'') public_email,
                       d.city,d.state,d.nmls_id,d.source_url,d.source_domain,d.review_status,d.confidence,d.created_at,
                       coalesce((select max(a.opportunity_score) from ai_contact_insights a
                                 where a.discovered_contact_id=d.id),0) opportunity_score,
                       (select count(distinct p.id) from discovered_contacts p
                         where trim(coalesce(p.person_name,''))<>''
                           and upper(trim(coalesce(p.state,'')))=upper(trim(coalesce(d.state,'')))
                           and ((d.domain_key<>'' and lower(trim(coalesce(p.source_domain,'')))=d.domain_key)
                                or lower(trim(coalesce(p.company_name,'')))=d.company_key)) loan_officer_count,
                       (select p.person_name from discovered_contacts p
                         where trim(coalesce(p.person_name,''))<>''
                           and upper(trim(coalesce(p.state,'')))=upper(trim(coalesce(d.state,'')))
                           and ((d.domain_key<>'' and lower(trim(coalesce(p.source_domain,'')))=d.domain_key)
                                or lower(trim(coalesce(p.company_name,'')))=d.company_key)
                         order by p.confidence desc,p.id desc limit 1) primary_contact
                from selected d
                order by opportunity_score desc,d.confidence desc,d.id desc
                limit ?
                """,
                args,
            ).fetchall()
            states = [r[0] for r in conn.execute(
                """select distinct upper(trim(state)) from discovered_contacts
                   where upper(trim(coalesce(state,''))) in (%s)
                   order by upper(trim(state))""" % ",".join("?" for _ in STATE_CODES),
                tuple(sorted(STATE_CODES)),
            ).fetchall()]
        return jsonify(items=[dict(r) for r in rows], states=states, count=len(rows), state=state)

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
const STATES=new Set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '));
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const txt=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
function prospectRoot(){return [...document.querySelectorAll('.view,main,section')].find(x=>x.offsetParent!==null&&/^Prospects$/i.test(txt(x.querySelector('h1,h2'))))||document.querySelector('main')}
function stateSelect(root){return [...root.querySelectorAll('select')].map(s=>({s,vals:[...s.options].map(o=>(o.value||txt(o)).trim().toUpperCase())})).filter(x=>x.vals.filter(v=>STATES.has(v)).length>=2).sort((a,b)=>b.vals.filter(v=>STATES.has(v)).length-a.vals.filter(v=>STATES.has(v)).length)[0]?.s||null}
function controls(root){return{state:stateSelect(root),search:root.querySelector('input[placeholder*="company" i],input[placeholder*="search" i]')}}
function table(root){return root.querySelector('table tbody')}
function row(x){const score=x.opportunity_score||x.confidence||50,contact=x.primary_contact||'Primary contact not named',phone=x.phone||'',email=x.public_email||'',loc=[x.city,x.state].filter(Boolean).join(', '),verify=(email||phone)?'Public contact verified':'Needs verification',lo=Number(x.loan_officer_count||0);return `<tr data-ember-prospect="1" data-state="${esc(x.state)}"><td><strong data-company>${esc(x.company_name)}</strong><span class="ember-new">EMBER</span><span class="ember-lo">${lo} loan officer${lo===1?'':'s'} attached</span></td><td class="contact-cell">${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="contact-missing">${esc(contact)}</span><div class="contact-actions">${phone?`<a class="btn smallbtn" href="tel:${esc(phone)}">☎ Call</a>`:''}${email?`<a class="btn smallbtn" href="mailto:${esc(email)}">✉ Email</a>`:''}${x.source_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.source_url)}">↗ Website</a>`:''}</div></td><td><span class="pill">Ember discovery</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${score}</td><td><span class="pill">${esc(verify)}</span></td><td>${esc(x.review_status||'New')}</td><td><button class="btn smallbtn" onclick="location.href='/platform/details/contacts?q=${encodeURIComponent(x.company_name)}&state=${encodeURIComponent(x.state||'')}'">Intelligence</button></td></tr>`}
let timer=0,last='',seq=0,controller=null;
function removeInjected(body){body?.querySelectorAll('[data-ember-prospect="1"]').forEach(n=>n.remove())}
async function load(force=false){const root=prospectRoot(),body=root&&table(root);if(!root||!body)return;const c=controls(root),selected=(c.state?.value||txt(c.state?.selectedOptions?.[0])||'').trim().toUpperCase(),state=STATES.has(selected)?selected:'',q=c.search?.value||'',key=state+'|'+q;if(!force&&key===last&&body.querySelector('[data-ember-prospect]'))return;last=key;const requestId=++seq;controller?.abort();controller=new AbortController();removeInjected(body);try{const r=await fetch('/api/ember/main-prospects?limit=1000&state='+encodeURIComponent(state)+'&q='+encodeURIComponent(q),{signal:controller.signal,cache:'no-store'});const d=await r.json();if(requestId!==seq)return;const current=(c.state?.value||txt(c.state?.selectedOptions?.[0])||'').trim().toUpperCase(),currentState=STATES.has(current)?current:'';if(currentState!==state)return;const items=(d.items||[]).filter(x=>!state||String(x.state||'').toUpperCase()===state);body.insertAdjacentHTML('beforeend',items.map(row).join(''));if(c.state){const existing=new Set([...c.state.options].map(o=>(o.value||txt(o)).toUpperCase()));for(const s of d.states||[]){if(STATES.has(s)&&!existing.has(s)){const o=document.createElement('option');o.value=s;o.textContent=s;c.state.appendChild(o)}}}root.querySelectorAll('[data-ember-count]').forEach(n=>n.textContent=items.length)}catch(e){if(e.name!=='AbortError')console.error('Ember prospects bridge',e)}}
function wire(){const root=prospectRoot();if(!root)return;const c=controls(root),body=table(root);if(c.state&&!c.state.dataset.emberWired){c.state.dataset.emberWired='1';c.state.addEventListener('change',()=>{last='';removeInjected(body);load(true)})}if(c.search&&!c.search.dataset.emberWired){c.search.dataset.emberWired='1';c.search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{last='';load(true)},250)})}load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true});setInterval(()=>load(true),15000);
})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
