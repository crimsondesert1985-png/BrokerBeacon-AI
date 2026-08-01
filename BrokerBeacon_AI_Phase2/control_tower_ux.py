"""Polished response-layer UX for the Ember Control Tower."""
from __future__ import annotations


def install_control_tower_ux(app):
    @app.after_request
    def enhance_control_tower(response):
        if response.status_code != 200 or not response.is_sequence:
            return response
        try:
            from flask import request
            if request.path != "/platform/control-tower":
                return response
            html = response.get_data(as_text=True)
            html = html.replace("Scout Control Tower", "Ember Command Center")
            html = html.replace(
                "One command center for discovery, the national warehouse, AI agents, bounded autonomy, and system health.",
                "Ember continuously finds, verifies, scores, and queues mortgage prospects while you stay in control of outreach.",
            )
            html = html.replace(
                '<div id="focus" class="muted">Loading…</div><button class="primary" style="margin-top:14px" onclick="runCycle()">Run one guarded growth cycle</button>',
                '<div class="always-on"><span class="live-dot"></span><b>Always-on prospecting enabled</b><small>Scheduled North Carolina hunts run automatically. Every prospect waits for your review.</small></div>'
                '<div id="focus" class="muted">Review the strongest pending prospects, then launch an extra safe batch whenever you want.</div>'
                '<div id="huntStatus" class="hunt-status">Ready. Outreach is locked until you approve a prospect.</div>'
                '<button id="huntButton" class="primary hunt-button" onclick="runCycle()"><span>🔥</span> Launch Ember Hunt</button>',
            )
            html = html.replace(
                '</style>',
                '@keyframes emberPulse{0%,100%{box-shadow:0 0 0 0 #ff784966}50%{box-shadow:0 0 0 10px #ff784900}}'
                '@keyframes emberGlow{0%,100%{filter:drop-shadow(0 0 5px #ff784955)}50%{filter:drop-shadow(0 0 18px #ffb347aa)}}'
                'body:before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 86% 5%,#ff6b3522,transparent 30%),radial-gradient(circle at 10% 90%,#4b8cff18,transparent 32%)}'
                'h1{font-size:34px;background:linear-gradient(90deg,#fff,#9bc7ff,#ffb56b);-webkit-background-clip:text;color:transparent;animation:emberGlow 3s ease-in-out infinite}'
                '.always-on{display:grid;grid-template-columns:18px 1fr;gap:2px 9px;padding:12px 14px;margin:10px 0 14px;border:1px solid #4bd19b66;background:linear-gradient(135deg,#4bd19b16,#58a6ff12);border-radius:12px}'
                '.always-on small{grid-column:2;color:var(--muted);line-height:1.4}.live-dot{width:11px;height:11px;margin-top:3px;border-radius:50%;background:#4bd19b;animation:emberPulse 1.8s infinite}'
                '.hunt-status{margin:14px 0;padding:12px;border-radius:10px;background:#081b38;border:1px solid var(--line);color:var(--muted);line-height:1.45}'
                '.hunt-status.running{color:#bfe0ff;border-color:#58a6ff66}.hunt-status.success{color:#b7f5d8;border-color:#4bd19b66}.hunt-status.failed{color:#ffd0d8;border-color:#ff7d9366}'
                '.hunt-button{width:100%;margin-top:2px;padding:14px;font-size:15px;font-weight:900;background:linear-gradient(120deg,#ff5f38,#ff9a3c,#276ee8);background-size:200% 200%;border:0;box-shadow:0 12px 30px #ff6f3533;transition:.2s}'
                '.hunt-button:hover{transform:translateY(-2px) scale(1.01);background-position:100% 50%}.hunt-button:disabled{opacity:.65;cursor:wait;transform:none}'
                '.card{transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}.card:hover{transform:translateY(-3px);border-color:#58a6ff66;box-shadow:0 14px 34px #0004}.card.actionable{cursor:pointer;position:relative}.card.actionable:after{content:"Open →";position:absolute;right:14px;bottom:12px;font-size:10px;color:#8ec5ff;opacity:.8}'
                '.card strong{background:linear-gradient(90deg,#fff,#84baff);-webkit-background-clip:text;color:transparent}'
                '.s38-drawer{position:fixed;inset:0;display:none;z-index:999;background:#020916b8;backdrop-filter:blur(7px)}.s38-drawer.open{display:block}.s38-panel{position:absolute;right:0;top:0;height:100%;width:min(760px,96vw);background:#081b38;border-left:1px solid #ffffff24;box-shadow:-30px 0 80px #0008;padding:24px;overflow:auto}.s38-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:18px}.s38-close{font-size:20px;background:#ffffff0c}.s38-list{display:grid;gap:10px}.s38-item{padding:14px;border:1px solid #ffffff1e;border-radius:13px;background:#102547;cursor:pointer;transition:.18s}.s38-item:hover{transform:translateX(-3px);border-color:#58a6ff66}.s38-row{display:flex;justify-content:space-between;gap:12px}.s38-score{font-size:20px;font-weight:900;color:#75d7ff}.s38-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.s38-actions button{flex:1}.s38-source{color:#8ec5ff;text-decoration:none}.s38-empty{padding:34px;text-align:center;color:var(--muted)}.s38-chip{display:inline-block;padding:4px 7px;border-radius:999px;background:#58a6ff1c;color:#bfe0ff;font-size:10px;margin:3px 4px 0 0}'
                '</style>',
            )
            old = "async function runCycle(){try{await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});await loadAll()}catch(e){fail(e)}}"
            new = """let huntRunning=false;async function runCycle(){
if(huntRunning)return;huntRunning=true;let b=document.getElementById('huntButton'),s=document.getElementById('huntStatus'),err=document.getElementById('error');
if(err)err.style.display='none';b.disabled=true;b.innerHTML='<span>🔥</span> Ember is hunting…';s.className='hunt-status running';s.textContent='Checking a safe North Carolina batch of public mortgage-company websites, extracting contacts, and scoring opportunities.';
try{let d=await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});let h=d.hunt||d;s.className='hunt-status success';s.textContent=`Complete. ${h.companies_seeded||0} companies checked, ${h.enrichment?.contacts_found||0} new contacts found, ${h.pending_review||0} waiting for review. No outreach was sent.`;await loadAll();openCompanies()}
catch(e){s.className='hunt-status failed';s.textContent='The hunt stopped safely. No outreach was sent. '+(e.message||e);fail(e)}
finally{huntRunning=false;b.disabled=false;b.innerHTML='<span>🔥</span> Launch Ember Hunt'}}"""
            html = html.replace(old, new)
            drawer = '''<div id="s38Drawer" class="s38-drawer" onclick="if(event.target===this)closeS38()"><aside class="s38-panel"><div class="s38-head"><div><div class="pill">SPRINT 38 · INTERACTIVE REVIEW</div><h2 id="s38Title">Details</h2><div id="s38Subtitle" class="muted"></div></div><button class="s38-close" onclick="closeS38()">✕</button></div><div id="s38Body" class="s38-list"><div class="s38-empty">Loading…</div></div></aside></div>'''
            script = r'''<script id="sprint38-interactions">
function s38e(v){return esc(v)}
function openS38(title,subtitle){s38Title.textContent=title;s38Subtitle.textContent=subtitle||'';s38Body.innerHTML='<div class="s38-empty">Loading…</div>';s38Drawer.classList.add('open')}
function closeS38(){s38Drawer.classList.remove('open')}
function switchTab(id){let b=document.querySelector(`[data-tab="${id}"]`);if(b)b.click()}
function contactCard(x){let name=x.person_name||x.canonical_person_name||'Company contact';return `<div class="s38-item" onclick="openContact(${x.id})"><div class="s38-row"><div><b>${s38e(name)}</b><div class="muted">${s38e(x.company_name||'Unknown company')} · ${s38e(x.city||'')}${x.state?' · '+s38e(x.state):''}</div></div><div class="s38-score">${x.opportunity_score||0}</div></div><div>${x.role?`<span class="s38-chip">${s38e(x.role)}</span>`:''}${x.review_status?`<span class="s38-chip">${s38e(x.review_status)}</span>`:''}${x.public_email?'<span class="s38-chip">Email found</span>':''}${x.phone?'<span class="s38-chip">Phone found</span>':''}</div></div>`}
async function openContacts(mode){let high=mode==='high',status=mode==='pending'?'Pending review':'';openS38(high?'High-opportunity prospects':status?'Pending review queue':'Discovered contacts',high?'Ember score 75 or higher':status?'Approve, reject, or inspect every prospect':'All contacts found by Ember');try{let d=await api(`/api/platform/sprint38/contacts?limit=200${high?'&high=1':''}${status?'&status='+encodeURIComponent(status):''}`);s38Body.innerHTML=d.items.length?d.items.map(contactCard).join(''):'<div class="s38-empty">No matching prospects yet.</div>'}catch(e){s38Body.innerHTML=`<div class="s38-empty">${s38e(e.message)}</div>`}}
async function openCompanies(){openS38('Companies Ember checked','Open any company to see its public source and discovered contacts');try{let d=await api('/api/platform/sprint38/companies?state=NC&limit=200');s38Body.innerHTML=d.items.length?d.items.map(x=>`<div class="s38-item" onclick='openCompany(${JSON.stringify(x.company_name)})'><div class="s38-row"><div><b>${s38e(x.company_name)}</b><div class="muted">${s38e(x.city||'')}${x.state?' · '+s38e(x.state):''}</div></div><div class="s38-score">${x.contact_count||0}</div></div><div><span class="s38-chip">${x.pending_count||0} pending</span><span class="s38-chip">Top score ${x.top_score||0}</span></div></div>`).join(''):'<div class="s38-empty">No company records are available yet. Ember may have found contacts from previously seeded websites; run another hunt to add more company results.</div>'}catch(e){s38Body.innerHTML=`<div class="s38-empty">${s38e(e.message)}</div>`}}
async function openCompany(name){openS38(name,'Company detail and discovered contacts');try{let d=await api('/api/platform/sprint38/companies/detail?name='+encodeURIComponent(name)),c=d.company;s38Body.innerHTML=`<div class="panel"><div class="s38-row"><div><b>${s38e(c.company_name)}</b><div class="muted">${s38e(c.city||'')} · ${s38e(c.state||'')}</div></div>${c.source_url?`<a class="s38-source" target="_blank" rel="noopener" href="${s38e(c.source_url)}">Open website ↗</a>`:''}</div></div>${d.contacts.length?d.contacts.map(contactCard).join(''):'<div class="s38-empty">No contacts found for this company yet.</div>'}`;}catch(e){s38Body.innerHTML=`<div class="s38-empty">${s38e(e.message)}</div>`}}
async function openContact(id){openS38('Prospect detail','Why Ember surfaced this record and what you can do next');try{let x=await api('/api/platform/sprint38/contacts/'+id),reasons=[];try{reasons=JSON.parse(x.reasons_json||'[]')}catch(_){ }s38Body.innerHTML=`<div class="panel"><div class="s38-row"><div><h2>${s38e(x.person_name||'Company contact')}</h2><div class="muted">${s38e(x.company_name||'')} · ${s38e(x.role||'')}</div></div><div class="s38-score">${x.opportunity_score||0}</div></div><p>${s38e(x.next_best_action||'Verify the public information and decide whether to approve this prospect.')}</p><div>${reasons.map(r=>`<span class="s38-chip">${s38e(r)}</span>`).join('')}</div><table><tbody><tr><th>Email</th><td>${x.public_email?`<a class="s38-source" href="mailto:${s38e(x.public_email)}">${s38e(x.public_email)}</a>`:'Not found'}</td></tr><tr><th>Phone</th><td>${s38e(x.phone||'Not found')}</td></tr><tr><th>NMLS</th><td>${s38e(x.nmls_id||'Not found')}</td></tr><tr><th>Status</th><td>${s38e(x.review_status)}</td></tr><tr><th>Source</th><td>${x.source_url?`<a class="s38-source" target="_blank" rel="noopener" href="${s38e(x.source_url)}">View public source ↗</a>`:'Unavailable'}</td></tr></tbody></table><div class="s38-actions"><button class="primary" onclick="reviewContact(${id},'approve')">Approve</button><button onclick="reviewContact(${id},'favorite')">Favorite</button><button class="danger" onclick="reviewContact(${id},'reject')">Reject</button></div><p class="muted">Approval updates the review queue only. No outreach is sent automatically.</p></div>`}catch(e){s38Body.innerHTML=`<div class="s38-empty">${s38e(e.message)}</div>`}}
async function reviewContact(id,action){try{await api(`/api/platform/sprint38/contacts/${id}/review`,{method:'POST',body:JSON.stringify({action})});await loadAll();openContact(id)}catch(e){fail(e)}}
function wireSprint38(){[['briefCompanies',openCompanies],['briefContacts',()=>openContacts('all')],['briefPending',()=>openContacts('pending')],['briefHigh',()=>openContacts('high')],['briefDupes',()=>switchTab('warehouse')]].forEach(([id,fn])=>{let n=document.getElementById(id),c=n&&n.closest('.card');if(c){c.classList.add('actionable');c.onclick=fn;c.title='Click to open details'}})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wireSprint38);else wireSprint38();
</script>'''
            lower = html.lower()
            pos = lower.rfind('</body>')
            html = html[:pos] + drawer + script + html[pos:]
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Control Tower UX enhancement failed")
        return response

    return app
