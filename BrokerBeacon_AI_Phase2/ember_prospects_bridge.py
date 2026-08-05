"""Expose Ember-created CRM prospects reliably on the main Prospects screen."""
from __future__ import annotations

import re
import sqlite3
import urllib.parse
from contextlib import closing
from flask import jsonify, request

STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
STATE_SET = set(STATE_CODES)
BLOCKED_DOMAINS = {
    "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "linkedin.com",
    "facebook.com", "instagram.com", "youtube.com", "bankrate.com", "nerdwallet.com",
    "investopedia.com", "forbes.com", "wikipedia.org", "indeed.com", "yelp.com",
}


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _value(row, key, default=""):
    try:
        return row[key] if key in row.keys() and row[key] is not None else default
    except Exception:
        return default


def _safe_company(name: str, website: str = "") -> bool:
    name = (name or "").strip()
    normalized = _normalize(name)
    domain = _domain(website)
    if len(name) < 3 or len(normalized.split()) > 14:
        return False
    if domain in BLOCKED_DOMAINS or any(domain.endswith("." + d) for d in BLOCKED_DOMAINS):
        return False
    bad = ("privacy policy", "terms of use", "license guide", "search results", "customer support")
    return not any(term in normalized for term in bad)


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
        like = f"%{query.lower()}%"
        items, seen = [], set()
        with closing(connect()) as conn:
            prospect_cols = _columns(conn, "prospects")
            if prospect_cols:
                rows = conn.execute(
                    """select * from prospects
                       where (?='' or upper(trim(coalesce(state,'')))=?)
                         and (?='' or lower(coalesce(company,'')) like ? or lower(coalesce(city,'')) like ?
                              or lower(coalesce(nmls,'')) like ?)
                       order by coalesce(updated_at,created_at,'') desc,id desc limit ?""",
                    (state, state, query, like, like, like, limit * 3),
                ).fetchall()
                for row in rows:
                    company = str(_value(row, "company")).strip()
                    website = str(_value(row, "website") or _value(row, "source_url")).strip()
                    if not _safe_company(company, website):
                        continue
                    row_state = str(_value(row, "state")).strip().upper()
                    nmls = str(_value(row, "nmls")).strip()
                    key = ("crm", int(_value(row, "id", 0)))
                    if key in seen:
                        continue
                    seen.add(key)
                    contact_count = conn.execute("select count(*) from contacts where prospect_id=?", (row["id"],)).fetchone()[0] if _columns(conn, "contacts") else 0
                    primary = conn.execute(
                        "select name,email,phone from contacts where prospect_id=? order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id limit 1",
                        (row["id"],),
                    ).fetchone() if contact_count else None
                    phone = str(_value(row, "phone") or (primary["phone"] if primary else "") or "")
                    email = str(_value(row, "email") or (primary["email"] if primary else "") or "")
                    score = int(_value(row, "score", 0) or 0) or (85 if nmls else 65)
                    source_name = str(_value(row, "source_name") or _value(row, "signal") or "")
                    items.append({
                        "id": row["id"], "crm_prospect_id": row["id"], "company_name": company,
                        "nmls_id": nmls, "source_url": website, "source_domain": _domain(website),
                        "phone": phone, "public_email": email, "city": _value(row, "city"),
                        "state": row_state, "review_status": _value(row, "verification_status", "Needs review"),
                        "pipeline_status": _value(row, "status", "New"), "confidence": score,
                        "opportunity_score": score, "loan_officer_count": int(contact_count),
                        "primary_contact": str(primary["name"] if primary else ""),
                        "source": source_name or "CRM prospect", "record_type": "crm",
                    })
                    if len(items) >= limit:
                        break

            if len(items) < limit and _columns(conn, "warehouse_companies"):
                rows = conn.execute(
                    """select * from warehouse_companies
                       where trim(coalesce(legal_name,''))<>''
                         and (?='' or upper(trim(state))=?)
                         and (?='' or lower(legal_name) like ? or lower(city) like ? or lower(nmls_id) like ?)
                       order by updated_at desc,id desc limit ?""",
                    (state, state, query, like, like, like, limit * 4),
                ).fetchall()
                for row in rows:
                    company = str(row["legal_name"] or "").strip()
                    website = str(row["website"] or "").strip()
                    if not _safe_company(company, website):
                        continue
                    nmls = str(row["nmls_id"] or "").strip()
                    duplicate = False
                    for item in items:
                        if nmls and item.get("nmls_id") == nmls:
                            duplicate = True
                            break
                        if _normalize(item.get("company_name", "")) == _normalize(company) and item.get("state", "") == str(row["state"] or "").upper():
                            duplicate = True
                            break
                    if duplicate:
                        continue
                    key = ("warehouse", row["id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    score = 80 if nmls else 55
                    items.append({
                        "id": f"w{row['id']}", "warehouse_company_id": row["id"], "company_name": company,
                        "nmls_id": nmls, "source_url": website, "source_domain": _domain(website),
                        "phone": row["phone"] or "", "public_email": row["public_email"] or "",
                        "city": row["city"] or "", "state": str(row["state"] or "").upper(),
                        "review_status": row["verification_status"] or "Needs review",
                        "pipeline_status": "New", "confidence": score, "opportunity_score": score,
                        "loan_officer_count": 0, "primary_contact": "", "source": "Ember warehouse",
                        "record_type": "warehouse",
                    })
                    if len(items) >= limit:
                        break
        return jsonify(items=items, states=list(STATE_CODES), count=len(items), selected_state=state, source="crm_first_ember_bridge")

    @app.after_request
    def inject_ember_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            page = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-crm-prospects" in page or "</body>" not in page.lower():
            return response
        script = r'''<style id="ember-crm-prospects-style">
tr[data-ember-prospect="1"] td{background:linear-gradient(90deg,#fff,#f6fbff)}.ember-badge{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#ff784918;color:#b54b20;font-size:9px;font-weight:900}.ember-sub{display:block;margin-top:4px;color:#637895;font-size:10px}.ember-empty td{text-align:center;padding:34px;color:#637895}
</style><script id="ember-crm-prospects">(function(){
const CODES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '),STATES=new Set(CODES);
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function root(){return document.querySelector('#prospects')||document.querySelector('[data-view="prospects"]')||[...document.querySelectorAll('.view,section')].find(x=>/prospect/i.test(x.id||'')||/prospect/i.test(x.querySelector('h1,h2')?.textContent||''))}
function body(){const r=root();return r?.querySelector('#rows,tbody,[data-prospect-rows]')||document.querySelector('#rows')}
function search(){const r=root();return r?.querySelector('#search,input[type="search"],[data-prospect-search]')}
function state(){const r=root();return r?.querySelector('#state,select[data-prospect-state]')}
function ensureState(){const s=state();if(!s)return null;if(!s.dataset.emberBound){const current=(s.value||'').toUpperCase();s.innerHTML='<option value="">All States</option>'+CODES.map(v=>`<option value="${v}">${v}</option>`).join('');s.value=STATES.has(current)?current:'';s.dataset.emberBound='1';s.addEventListener('change',()=>load(true))}return s}
function selected(){const s=ensureState();return STATES.has((s?.value||'').toUpperCase())?s.value.toUpperCase():''}
function row(x){const phone=x.phone||'',email=x.public_email||'',loc=[x.city,x.state].filter(Boolean).join(', '),badge=x.record_type==='crm'?'EMBER CRM':'EMBER';const detail=x.crm_prospect_id?`openProfile(${Number(x.crm_prospect_id)})`:`location.href='/platform/control-tower'`;return `<tr data-ember-prospect="1" data-state="${esc(x.state||'')}"><td><strong>${esc(x.company_name)}</strong><span class="ember-badge">${badge}</span><span class="ember-sub">${Number(x.loan_officer_count||0)} contacts${x.nmls_id?` · NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="ember-sub">${esc(x.primary_contact||'Contact research pending')}</span></td><td><span class="pill">${esc(x.source||'Ember')}</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${Number(x.opportunity_score||0)}</td><td><span class="pill">${esc(x.review_status||'Needs review')}</span></td><td>${esc(x.pipeline_status||'New')}</td><td><button class="btn smallbtn" onclick="${detail}">Open</button></td></tr>`}
let seq=0,timer=0;
async function load(force=false){const b=body(),q=search(),s=ensureState();if(!b||!s)return;const id=++seq,st=selected(),term=q?.value||'';b.innerHTML='<tr class="ember-empty"><td colspan="9">Loading Ember prospects…</td></tr>';try{const res=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(st)+'&q='+encodeURIComponent(term),{cache:'no-store'}),data=await res.json();if(id!==seq)return;b.innerHTML=(data.items||[]).length?data.items.map(row).join(''):'<tr class="ember-empty"><td colspan="9">No matching prospects yet. Ember is still searching.</td></tr>'}catch(e){b.innerHTML='<tr class="ember-empty"><td colspan="9">Unable to load prospects.</td></tr>'}}
function wire(){if(!body())return;ensureState();const q=search();if(q&&!q.dataset.emberBound){q.dataset.emberBound='1';q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>load(true),250)})}window.loadEmberProspects=load;load(true)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();setInterval(()=>load(true),300000);
})();</script>'''
        pos = page.lower().rfind("</body>")
        page = page[:pos] + script + page[pos:]
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
