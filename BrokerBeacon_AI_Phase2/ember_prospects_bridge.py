"""Expose credible mortgage brokerage companies on the main Prospects screen."""
from __future__ import annotations

import re
import sqlite3
import urllib.parse
from contextlib import closing
from flask import jsonify, request

STATE_CODES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
)
STATE_SET = set(STATE_CODES)
BROKER_MARKERS = ("mortgage", "home loan", "home loans", "lending", "funding", "financial", "capital", "finance")
ENTITY_SUFFIXES = ("llc", "inc", "incorporated", "corp", "corporation", "company", "co", "group", "partners", "services", "associates")
BAD_MARKERS = (
    "license guide", "licensing guide", "get a license", "license requirements", "license search", "license lookup",
    "mortgage broker license", "mortgage licensing", "search for mortgage", "state licensing", "directory",
    "best mortgage", "best local", "top loan officers", "mortgage lenders and loan officers", "search results",
    "privacy policy", "terms of use", "customer service", "customer support", "contact us", "about us",
    "wholesale mortgage", "wholesale lending", "wholesale mortgages", "mortgages available", "loans available",
    "become a broker", "broker portal", "third party originator", "training", "school", "course",
    "home builder", "title company", "title services", "realtor", "realty", "insurance agency",
    "department of", "division of", "commissioner of banks", "regulator", "government",
)
BAD_PREFIXES = ("find ", "best ", "top ", "state ", "customer ", "how to ", "what is ", "learn ", "online ", "directory ", "search ")
BLOCKED_DOMAINS = {
    "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "nc.gov", "nccob.gov", "linkedin.com",
    "facebook.com", "instagram.com", "youtube.com", "bankrate.com", "nerdwallet.com", "investopedia.com",
    "forbes.com", "wikipedia.org", "indeed.com", "yelp.com", "bbb.org",
}


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _blocked_domain(domain: str) -> bool:
    return bool(domain and (domain.endswith((".gov", ".edu")) or domain in BLOCKED_DOMAINS or any(domain.endswith("." + d) for d in BLOCKED_DOMAINS)))


def _looks_like_company(name: str, website: str, nmls_id: str) -> bool:
    name = (name or "").strip()
    normalized = _normalize(name)
    words = normalized.split()
    domain = _domain(website)
    if len(name) < 4 or len(words) > 8 or normalized.startswith(BAD_PREFIXES):
        return False
    if any(marker in normalized for marker in BAD_MARKERS) or _blocked_domain(domain):
        return False
    if re.search(r"\b(in|near|serving|available|guide|license|licensing|requirements|search)\b", normalized):
        return False
    industry = any(marker in normalized for marker in BROKER_MARKERS)
    entity = any(re.search(rf"\b{re.escape(suffix)}\b", normalized) for suffix in ENTITY_SUFFIXES)
    valid_nmls = bool(re.fullmatch(r"\d{4,12}", re.sub(r"\D+", "", nmls_id or "")))
    real_domain = bool(domain and "." in domain and not _blocked_domain(domain))
    return industry and (entity or (real_domain and valid_nmls))


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
        with closing(connect()) as conn:
            rows = conn.execute(
                """select id,legal_name,nmls_id,website,phone,public_email,city,upper(trim(state)) state,
                          verification_status,created_at,updated_at
                   from warehouse_companies
                   where trim(coalesce(legal_name,''))<>''
                     and (?='' or upper(trim(state))=?)
                     and (?='' or lower(legal_name) like ? or lower(city) like ? or lower(nmls_id) like ?)
                   order by updated_at desc,id desc limit ?""",
                (state, state, query, like, like, like, limit * 8),
            ).fetchall()
            items, seen = [], set()
            for row in rows:
                company = str(row["legal_name"] or "").strip()
                website = str(row["website"] or "").strip()
                nmls = str(row["nmls_id"] or "").strip()
                if not _looks_like_company(company, website, nmls):
                    continue
                domain = _domain(website)
                key = (str(row["state"] or ""), domain or _normalize(company))
                if key in seen:
                    continue
                seen.add(key)
                contacts = conn.execute(
                    """select person_name,phone,public_email,source_url,source_domain,confidence
                       from discovered_contacts
                       where review_status<>'Rejected' and upper(trim(coalesce(state,'')))=?
                         and ((?<>'' and lower(trim(coalesce(source_domain,'')))=?)
                              or lower(trim(coalesce(company_name,'')))=lower(?))
                       order by confidence desc,id desc""",
                    (row["state"], domain, domain, company),
                ).fetchall()
                named = [c for c in contacts if str(c["person_name"] or "").strip()]
                best = contacts[0] if contacts else None
                phone = str(row["phone"] or (best["phone"] if best else "") or "")
                email = str(row["public_email"] or (best["public_email"] if best else "") or "")
                source_url = website or str((best["source_url"] if best else "") or "")
                score = (90 if nmls else 75) + (5 if phone or email else 0)
                items.append({
                    "id": row["id"], "company_name": company, "nmls_id": nmls, "source_url": source_url,
                    "source_domain": domain, "phone": phone, "public_email": email, "city": row["city"],
                    "state": row["state"], "review_status": row["verification_status"] or "Needs review",
                    "confidence": score, "opportunity_score": score, "loan_officer_count": len(named),
                    "primary_contact": str(named[0]["person_name"] if named else ""),
                })
                if len(items) >= limit:
                    break
        return jsonify(items=items, states=list(STATE_CODES), count=len(items), selected_state=state, source="credible_warehouse_brokerages")

    @app.after_request
    def inject_ember_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            page = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-deterministic-prospects" in page or "</body>" not in page.lower():
            return response
        script = r'''<style id="ember-deterministic-prospects-style">
#ember-state-filter{min-width:110px}tr[data-ember-prospect="1"] td{background:linear-gradient(90deg,#fff,#f6fbff)}.ember-badge{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#ff784918;color:#b54b20;font-size:9px;font-weight:900}.ember-sub{display:block;margin-top:4px;color:#637895;font-size:10px}.ember-empty td{text-align:center;padding:34px;color:#637895}
</style><script id="ember-deterministic-prospects">(function(){
const CODES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '),STATES=new Set(CODES),HOURLY=3600000;
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
function root(){return document.querySelector('#prospects')}
function searchBox(r){return r?.querySelector('#search')}
function tbody(r){return r?.querySelector('#rows')}
function ensureStateControl(){const r=root(),state=r?.querySelector('#state');if(!state)return null;if(!state.dataset.emberAuthoritative){const current=(state.value||'').toUpperCase();state.innerHTML='<option value="">All States</option>'+CODES.map(s=>`<option value="${s}">${s}</option>`).join('');state.value=STATES.has(current)?current:'';state.dataset.emberAuthoritative='1';state.setAttribute('aria-label','Prospect state');state.onchange=null;state.addEventListener('change',()=>loadEmber(true))}return state}
function selectedState(){const s=ensureStateControl();return STATES.has((s?.value||'').toUpperCase())?s.value.toUpperCase():''}
function row(x){const phone=x.phone||'',email=x.public_email||'',contact=x.primary_contact||'Primary contact not named',lo=Number(x.loan_officer_count||0),loc=[x.city,x.state].filter(Boolean).join(', '),score=x.opportunity_score||75;return `<tr data-ember-prospect="1" data-state="${esc(x.state||'')}"><td><strong>${esc(x.company_name)}</strong><span class="ember-badge">EMBER</span><span class="ember-sub">${lo} loan officer${lo===1?'':'s'} attached${x.nmls_id?` Â· NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="ember-sub">${esc(contact)}</span><div class="contact-actions">${phone?`<a class="btn smallbtn" href="tel:${esc(phone)}">â˜Ž Call</a>`:''}${email?`<a class="btn smallbtn" href="mailto:${esc(email)}">âœ‰ Email</a>`:''}${x.source_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.source_url)}">â†— Website</a>`:''}</div></td><td><span class="pill">Validated brokerage</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${score}</td><td><span class="pill">${esc(x.review_status||'Needs review')}</span></td><td>Pending review</td><td><button class="btn smallbtn" onclick="location.href='/platform/details/contacts?q=${encodeURIComponent(x.company_name)}&state=${encodeURIComponent(x.state||'')}'">Intelligence</button></td></tr>`}
let seq=0,ctl=null,timer=0,lastKey='';
async function load(force=false){const r=root(),body=tbody(r),q=searchBox(r),sel=ensureStateControl();if(!r||!body||!sel)return;const state=selectedState(),term=q?.value||'',key=state+'|'+term;if(!force&&key===lastKey)return;lastKey=key;const id=++seq;ctl?.abort();ctl=new AbortController();body.innerHTML='<tr class="ember-empty"><td colspan="9">Loading selected stateâ€¦</td></tr>';try{const res=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(state)+'&q='+encodeURIComponent(term),{signal:ctl.signal,cache:'no-store'}),data=await res.json();if(id!==seq||String(data.selected_state||'')!==state||selectedState()!==state)return;const items=(data.items||[]).filter(x=>!state||String(x.state||'').toUpperCase()===state);body.innerHTML=items.length?items.map(row).join(''):'<tr class="ember-empty"><td colspan="9">No validated mortgage brokerages found for this state yet.</td></tr>'}catch(e){if(e.name!=='AbortError')body.innerHTML='<tr class="ember-empty"><td colspan="9">Unable to load validated brokerages.</td></tr>'}}
const loadEmber=load;
function wire(){const r=root(),q=searchBox(r);if(!r||!q||!tbody(r))return;ensureStateControl();if(!q.dataset.emberSearchBound){q.dataset.emberSearchBound='1';q.oninput=null;q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>loadEmber(true),250)})}window.load=loadEmber;loadEmber(true)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();setInterval(()=>loadEmber(true),HOURLY);
})();</script>'''
        pos = page.lower().rfind("</body>")
        page = page[:pos] + script + page[pos:]
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]

