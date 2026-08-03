"""Expose only plausible mortgage brokerage companies on the main Prospects screen."""
from __future__ import annotations

import re
import sqlite3
import urllib.parse
from flask import jsonify, request

STATE_CODES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
)
STATE_SET = set(STATE_CODES)

BROKER_MARKERS = (
    "mortgage", "home loan", "home loans", "lending", "funding", "financial",
    "capital", "finance", "loan company", "mortgage group", "mortgage llc",
)
BAD_NAME_MARKERS = (
    "state licensing", "state licenses", "important information", "customer service",
    "customer support", "find the best", "best mortgage", "best local", "top loan officers",
    "mortgage lenders and loan officers", "serving new york", "serving north carolina",
    "for 2026", "verified", "directory", "search results", "privacy policy", "terms of use",
    "login", "sign in", "contact us", "about us", "home loans & mortgages",
    "home builder", "custom homes", "real estate attorney", "title company", "title services",
    "realtor", "realty", "roofing", "insurance agency", "property management", "apartments",
    "county government", "city government", "linkedin", "facebook", "instagram", "capes school",
)
BAD_PREFIXES = (
    "find ", "best ", "top ", "state ", "customer ", "mortgage lenders and ",
    "how to ", "what is ", "learn ", "online ", "directory ",
)
BLOCKED_DOMAINS = {
    "nmlsconsumeraccess.org", "consumerfinance.gov", "hud.gov", "linkedin.com", "facebook.com",
    "instagram.com", "youtube.com", "bankrate.com", "nerdwallet.com", "investopedia.com",
    "forbes.com", "wikipedia.org", "indeed.com", "yelp.com", "bbb.org",
}


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _looks_like_company(name: str, website: str, nmls_id: str) -> bool:
    name = (name or "").strip()
    lower = name.lower()
    words = re.findall(r"[a-z0-9]+", lower)
    domain = _domain(website)
    if not name or len(name) < 4 or len(words) > 9:
        return False
    if lower.startswith(BAD_PREFIXES) or any(marker in lower for marker in BAD_NAME_MARKERS):
        return False
    if domain in BLOCKED_DOMAINS or any(domain.endswith("." + item) for item in BLOCKED_DOMAINS):
        return False
    if re.search(r"\b(in|near|serving)\s+[A-Z][a-z]+", name):
        return False
    if name.endswith(("?", ":", ".")):
        return False
    has_broker_name = any(marker in lower for marker in BROKER_MARKERS)
    has_entity_suffix = bool(re.search(r"\b(llc|inc|corp|corporation|company|group|partners|services)\b", lower))
    has_real_domain = bool(domain and "." in domain)
    # NMLS alone is not enough; page titles often contain an NMLS number.
    return has_broker_name and (has_entity_suffix or has_real_domain or bool(str(nmls_id or "").strip()))


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
        with connect() as conn:
            rows = conn.execute(
                """select id,legal_name,nmls_id,website,phone,public_email,city,upper(trim(state)) state,
                          verification_status,created_at,updated_at
                   from warehouse_companies
                   where trim(coalesce(legal_name,''))<>''
                     and (?='' or upper(trim(state))=?)
                     and (?='' or lower(legal_name) like ? or lower(city) like ? or lower(nmls_id) like ?)
                   order by updated_at desc,id desc limit ?""",
                (state, state, query, like, like, like, limit * 5),
            ).fetchall()
            items = []
            seen = set()
            for row in rows:
                company = str(row["legal_name"] or "").strip()
                website = str(row["website"] or "").strip()
                nmls = str(row["nmls_id"] or "").strip()
                if not _looks_like_company(company, website, nmls):
                    continue
                key = (str(row["state"] or ""), _domain(website) or _normalize(company))
                if key in seen:
                    continue
                seen.add(key)
                domain = _domain(website)
                contacts = conn.execute(
                    """select person_name,phone,public_email,source_url,source_domain,confidence
                       from discovered_contacts
                       where review_status<>'Rejected'
                         and upper(trim(coalesce(state,'')))=?
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
                score = 90 if nmls else 75
                if phone or email:
                    score += 5
                items.append({
                    "id": row["id"], "company_name": company, "nmls_id": nmls,
                    "source_url": source_url, "source_domain": domain, "phone": phone,
                    "public_email": email, "city": row["city"], "state": row["state"],
                    "review_status": row["verification_status"] or "Needs review",
                    "confidence": score, "opportunity_score": score,
                    "loan_officer_count": len(named),
                    "primary_contact": str(named[0]["person_name"] if named else ""),
                    "warehouse_company_id": row["id"],
                })
                if len(items) >= limit:
                    break
        return jsonify(items=items, states=list(STATE_CODES), count=len(items), selected_state=state, source="validated_warehouse_companies")

    @app.after_request
    def inject_ember_prospects(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            page = response.get_data(as_text=True)
        except Exception:
            return response
        if "ember-strict-prospects" in page or "</body>" not in page.lower():
            return response
        enhancement = r'''<style id="ember-strict-prospects-style">
tr[data-ember-prospect="1"] td{background:linear-gradient(90deg,#fff,#f6fbff)}.ember-badge{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#ff784918;color:#b54b20;font-size:9px;font-weight:900}.ember-sub{display:block;margin-top:4px;color:#637895;font-size:10px}.ember-empty td{text-align:center;padding:34px;color:#637895}
</style><script id="ember-strict-prospects">(function(){
const CODES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(' '),STATES=new Set(CODES);
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
function root(){return [...document.querySelectorAll('.view,main,section')].find(x=>x.offsetParent!==null&&/^Prospects$/i.test(text(x.querySelector('h1,h2'))))||document.querySelector('main')}
function searchBox(r){return r.querySelector('input[placeholder*="company" i],input[placeholder*="search" i]')}
function stateSelect(r){const q=searchBox(r),sels=[...r.querySelectorAll('select')];if(q){const qr=q.getBoundingClientRect();const near=sels.filter(s=>{const x=s.getBoundingClientRect();return x.left>qr.right-10&&Math.abs(x.top-qr.top)<35}).sort((a,b)=>a.getBoundingClientRect().left-b.getBoundingClientRect().left);if(near[0])return near[0]}return sels.find(s=>[...s.options].some(o=>STATES.has((o.value||text(o)).toUpperCase())))||sels[0]||null}
function tbody(r){return r.querySelector('table tbody')}
function ensureStates(sel){if(!sel)return;const current=(sel.value||'').toUpperCase();if(sel.dataset.strictStates!=='1'){sel.innerHTML='<option value="">All States</option>'+CODES.map(s=>`<option value="${s}">${s}</option>`).join('');sel.dataset.strictStates='1'}sel.value=STATES.has(current)?current:''}
function row(x){const phone=x.phone||'',email=x.public_email||'',contact=x.primary_contact||'Primary contact not named',lo=Number(x.loan_officer_count||0),loc=[x.city,x.state].filter(Boolean).join(', '),score=x.opportunity_score||75;return `<tr data-ember-prospect="1"><td><strong>${esc(x.company_name)}</strong><span class="ember-badge">EMBER</span><span class="ember-sub">${lo} loan officer${lo===1?'':'s'} attached${x.nmls_id?` · NMLS ${esc(x.nmls_id)}`:''}</span></td><td>${phone?`<a href="tel:${esc(phone)}">${esc(phone)}</a>`:''}${email?`<a href="mailto:${esc(email)}">${esc(email)}</a>`:''}<span class="ember-sub">${esc(contact)}</span><div class="contact-actions">${phone?`<a class="btn smallbtn" href="tel:${esc(phone)}">☎ Call</a>`:''}${email?`<a class="btn smallbtn" href="mailto:${esc(email)}">✉ Email</a>`:''}${x.source_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.source_url)}">↗ Website</a>`:''}</div></td><td><span class="pill">Validated brokerage</span></td><td>${esc(loc)}</td><td><span class="pill">Broker</span></td><td class="score">${score}</td><td><span class="pill">${esc(x.review_status||'Needs review')}</span></td><td>Pending review</td><td><button class="btn smallbtn" onclick="location.href='/platform/details/contacts?q=${encodeURIComponent(x.company_name)}&state=${encodeURIComponent(x.state||'')}'">Intelligence</button></td></tr>`}
let seq=0,ctl=null,timer=0,painting=false,observer=null;
async function load(){const r=root(),body=r&&tbody(r);if(!r||!body)return;const sel=stateSelect(r),q=searchBox(r);ensureStates(sel);const state=STATES.has((sel?.value||'').toUpperCase())?sel.value.toUpperCase():'',term=q?.value||'',id=++seq;ctl?.abort();ctl=new AbortController();painting=true;body.innerHTML='<tr class="ember-empty"><td colspan="9">Loading validated brokerages…</td></tr>';painting=false;try{const res=await fetch('/api/ember/main-prospects?limit=5000&state='+encodeURIComponent(state)+'&q='+encodeURIComponent(term),{signal:ctl.signal,cache:'no-store'}),data=await res.json();if(id!==seq)return;const items=(data.items||[]).filter(x=>!state||String(x.state||'').toUpperCase()===state);painting=true;body.innerHTML=items.length?items.map(row).join(''):'<tr class="ember-empty"><td colspan="9">No validated mortgage brokerages found for this state yet.</td></tr>';painting=false}catch(e){if(e.name!=='AbortError'){painting=true;body.innerHTML='<tr class="ember-empty"><td colspan="9">Unable to load validated brokerages.</td></tr>';painting=false}}}
function wire(){const r=root(),body=r&&tbody(r);if(!r||!body)return;const sel=stateSelect(r),q=searchBox(r);ensureStates(sel);if(sel&&!sel.dataset.strictBound){sel.dataset.strictBound='1';sel.addEventListener('change',load)}if(q&&!q.dataset.strictBound){q.dataset.strictBound='1';q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)})}if(!observer){observer=new MutationObserver(()=>{if(!painting&&body.querySelector('tr:not([data-ember-prospect="1"]):not(.ember-empty)'))load()});observer.observe(body,{childList:true})}load()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();setInterval(load,15000);
})();</script>'''
        pos = page.lower().rfind("</body>")
        page = page[:pos] + enhancement + page[pos:]
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_ember_prospects_bridge"]
