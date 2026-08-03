"""Make Ember discoveries the authoritative dataset for the main Prospects screen."""
from __future__ import annotations

import sqlite3
from flask import jsonify, request

from broker_company_contacts import sync_company_contacts

STATE_CODES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
)
STATE_SET = set(STATE_CODES)


def install_ember_prospects_bridge(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout=30000")
        return conn

    @app.get("/api/ember/main-prospects")
    def ember_main_prospects():
        requested = str(request.args.get("state") or "").strip().upper()
        state = requested if requested in STATE_SET else ""
        query = str(request.args.get("q") or "").strip()[:120]
        limit = min(max(int(request.args.get("limit") or 1000), 1), 5000)
        with connect() as conn:
            sync_stats = sync_company_contacts(conn, state=state)
            where = ["trim(coalesce(d.company_name,''))<>''", "d.review_status<>'Rejected'"]
            args: list[object] = []
            if state:
                where.append("upper(trim(coalesce(d.state,'')))=?")
                args.append(state)
            if query:
                like = f"%{query}%"
                where.append("(d.company_name like ? or d.person_name like ? or d.city like ? or d.state like ? or d.nmls_id like ? or d.public_email like ? or d.phone like ? or d.source_domain like ?)")
                args.extend([like] * 8)
            args.append(limit)
            rows = conn.execute(
                """
                with normalized as (
                    select d.*,
                           lower(trim(coalesce(d.company_name,''))) company_key,
                           lower(trim(coalesce(d.source_domain,''))) domain_key,
                           case when trim(coalesce(d.source_domain,''))<>''
                                then lower(trim(d.source_domain))
                                else lower(trim(d.company_name)) end group_key
                    from discovered_contacts d
                    where """ + " and ".join(where) + """
                ), ranked as (
                    select n.*,
                           row_number() over (
                               partition by upper(trim(coalesce(n.state,''))),n.group_key
                               order by case when trim(coalesce(n.person_name,''))='' then 0 else 1 end,
                                        n.confidence desc,n.id desc
                           ) company_rank
                    from normalized n
                )
                select c.id,c.company_name,c.city,upper(trim(c.state)) state,c.nmls_id,
                       c.source_url,c.source_domain,c.review_status,c.confidence,c.created_at,
                       coalesce(nullif(trim(c.phone),''),(
                           select nullif(trim(p.phone),'') from normalized p
                           where p.group_key=c.group_key and upper(trim(p.state))=upper(trim(c.state))
                             and trim(coalesce(p.phone,''))<>''
                           order by p.confidence desc,p.id desc limit 1
                       ),'') phone,
                       coalesce(nullif(trim(c.public_email),''),(
                           select nullif(trim(p.public_email),'') from normalized p
                           where p.group_key=c.group_key and upper(trim(p.state))=upper(trim(c.state))
                             and trim(coalesce(p.public_email,''))<>''
                           order by p.confidence desc,p.id desc limit 1
                       ),'') public_email,
                       coalesce((select max(a.opportunity_score) from ai_contact_insights a
                                 join normalized x on x.id=a.discovered_contact_id
                                 where x.group_key=c.group_key and upper(trim(x.state))=upper(trim(c.state))),0) opportunity_score,
                       (select count(*) from normalized p
                         where p.group_key=c.group_key and upper(trim(p.state))=upper(trim(c.state))
                           and trim(coalesce(p.person_name,''))<>'') loan_officer_count,
                       (select p.person_name from normalized p
                         where p.group_key=c.group_key and upper(trim(p.state))=upper(trim(c.state))
                           and trim(coalesce(p.person_name,''))<>''
                         order by p.confidence desc,p.id desc limit 1) primary_contact
                from ranked c
                where c.company_rank=1
                order by opportunity_score desc,c.confidence desc,c.id desc
                limit ?
                """,
                args,
            ).fetchall()
            total_contacts = conn.execute(
                "select count(*) from discovered_contacts where review_status<>'Rejected'"
            ).fetchone()[0]
            total_companies = conn.execute(
                """select count(*) from (
                     select upper(trim(state)),case when trim(coalesce(source_domain,''))<>'' then lower(trim(source_domain)) else lower(trim(company_name)) end
                     from discovered_contacts where review_status<>'Rejected' and trim(coalesce(company_name,''))<>''
                     group by 1,2)"""
            ).fetchone()[0]
        return jsonify(
            items=[dict(r) for r in rows],
            states=list(STATE_CODES),
            count=len(rows),
            selected_state=state,
            total_contacts=int(total_contacts or 0),
            total_companies=int(total_companies or 0),
            sync=sync_stats,
        )

    @app.after_request
    def inject_ember_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-authoritative-prospects" in body or "</body>" not in body.lower():
            return response
        enhancement = r'''<style id="ember-authoritative-prospects-style">
tr[data-ember-prospect="1"] td{background:linear-gradient(90deg,#fff,#f6fbff)}
tr[data-ember-prospect="1"]:hover td{background:#eef7ff}.ember-new{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#ff784918;color:#b54b20;font-size:9px;font-weight:900}.ember-lo{display:block;margin-top:4px;color:#637895;font-size:10px}.ember-empty td{text-align:center;padding:34px;color:#637895}.dark-mode tr[data-ember-prospect="1"] td{background:#12233d}
</style><script id="ember-authoritative-prospects">(function(){
const CODES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '),STATES=new Set(CODES);
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
function root(){return [...document.querySelectorAll('.view,main,section')].find(x=>x.offsetParent!==null&&/^Prospects$/i.test(text(x.querySelector('h1,h2'))))||document.querySelector('main')}
function stateSelect(r){const sels=[...r.querySelectorAll('select')];return sels.find(s=>[...s.options].some(o=>STATES.has((o.value||text(o)).toUpperCase())))||sels[0]||null}
function controls(r){return{state:stateSelect(r),search:r.querySelector('input[placeholder*="company" i],input[placeholder*="search" i]')}}
function body(r){return r.querySelector('table tbody')}
function ensureStates(sel){if(!sel)return;const current=(sel.value||'').toUpperCase();sel.innerHTML='<option value="">All States</option>'+CODES.map(s=>`<option value="${s}">${s}</option>`).join('');sel.value=STATES.has(current)?current:''}
function row(x){const score=x.opportunity_score||x.confidence||50,phone=x.phone||'',email=x.public_email||'',contact=x.primary_contact||'Primary contact not named',lo=Number(x.loan_officer_count||0),loc=[x.city,x.state].filter(Boolean).join(', '),verify=(phone||email)?'Public contact verified':'Needs verification';return `<tr data-ember-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="ember-new">EMBER</span><span class="ember-lo">${lo} loan officer${lo===1?'':'s'} attached</span></td><td class="contact-cell">${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="contact-missing">${esc(contact)}</span><div class="contact-actions">${phone?`<a class="btn smallbtn" href="tel:${esc(phone)}">☎ Call</a>`:''}${email?`<a class="btn smallbtn" href="mailto:${esc(email)}">✉ Email</a>`:''}${x.source_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.source_url)}">↗ Website</a>`:''}</div></td><td><span class="pill">Ember discovery</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${score}</td><td><span class="pill">${esc(verify)}</span></td><td>${esc(x.review_status||'Pending review')}</td><td><button class="btn smallbtn" onclick="location.href='/platform/details/contacts?q=${encodeURIComponent(x.company_name)}&state=${encodeURIComponent(x.state||'')}'">Intelligence</button></td></tr>`}
let seq=0,ctl=null,timer=0;
async function load(){const r=root(),tbody=r&&body(r);if(!r||!tbody)return;const c=controls(r);ensureStates(c.state);const state=STATES.has((c.state?.value||'').toUpperCase())?c.state.value.toUpperCase():'',q=c.search?.value||'',id=++seq;ctl?.abort();ctl=new AbortController();tbody.innerHTML='<tr class="ember-empty"><td colspan="9">Loading Ember prospects…</td></tr>';try{const res=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(state)+'&q='+encodeURIComponent(q),{signal:ctl.signal,cache:'no-store'}),data=await res.json();if(id!==seq)return;const items=(data.items||[]).filter(x=>!state||String(x.state||'').toUpperCase()===state);tbody.innerHTML=items.length?items.map(row).join(''):'<tr class="ember-empty"><td colspan="9">No Ember prospects found for this state yet.</td></tr>';r.querySelectorAll('[data-ember-count]').forEach(n=>n.textContent=items.length)}catch(e){if(e.name!=='AbortError')tbody.innerHTML='<tr class="ember-empty"><td colspan="9">Unable to load Ember prospects.</td></tr>'}}
function wire(){const r=root();if(!r)return;const c=controls(r);ensureStates(c.state);if(c.state&&!c.state.dataset.emberAuthoritative){c.state.dataset.emberAuthoritative='1';c.state.addEventListener('change',load)}if(c.search&&!c.search.dataset.emberAuthoritative){c.search.dataset.emberAuthoritative='1';c.search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)})}load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();setInterval(load,15000);
})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + enhancement + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
