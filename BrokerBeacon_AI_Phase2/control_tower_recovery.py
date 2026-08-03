"""Late response-layer recovery for Control Tower navigation and review actions."""
from __future__ import annotations

from flask import request


RECOVERY_SCRIPT = r'''<style id="bb-control-tower-recovery-style">
#bb-prospect-drawer,#bb-prospect-backdrop{display:none!important}
#bb-review-recovery{position:fixed;inset:0;z-index:12000;display:none;background:#020916c7;backdrop-filter:blur(7px)}
#bb-review-recovery.open{display:block}#bb-review-recovery-panel{position:absolute;right:0;top:0;width:min(820px,98vw);height:100%;overflow:auto;background:#081b38;color:#f7fbff;border-left:1px solid #ffffff24;box-shadow:-30px 0 80px #0009;padding:24px}
.bbrr-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.bbrr-close{font-size:20px}.bbrr-list{display:grid;gap:10px}.bbrr-item{padding:16px;border:1px solid #ffffff1e;border-radius:13px;background:#102547;cursor:pointer;transition:.16s ease}.bbrr-item:hover{border-color:#58a6ff88;transform:translateY(-1px);background:#132b51}.bbrr-row{display:flex;justify-content:space-between;gap:12px}.bbrr-muted{color:#a7b7cf}.bbrr-score{font-size:20px;font-weight:900;color:#75d7ff}.bbrr-empty{padding:32px;text-align:center;color:#a7b7cf}.bbrr-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.bbrr-tag{font-size:12px;padding:4px 8px;border-radius:999px;background:#ffffff12;color:#c8ddf6}.bbrr-tag.good{background:#1fc98b22;color:#79efc0}.bbrr-tag.warn{background:#ffbe5520;color:#ffd28a}.bbrr-detail{display:grid;gap:14px}.bbrr-section{padding:16px;border:1px solid #ffffff1e;border-radius:14px;background:#102547}.bbrr-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.bbrr-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#78a7d8}.bbrr-value{margin-top:4px;word-break:break-word}.bbrr-actions{display:flex;gap:10px;flex-wrap:wrap;position:sticky;bottom:0;padding:14px 0;background:linear-gradient(transparent,#081b38 28%)}.bbrr-btn{border:0;border-radius:10px;padding:11px 16px;font-weight:800;cursor:pointer}.bbrr-btn.approve{background:#1fc98b;color:#03251b}.bbrr-btn.reject{background:#ff6b6b;color:#2c0707}.bbrr-btn.pending{background:#ffffff18;color:#fff}.bbrr-back{background:none;border:0;color:#75d7ff;padding:0;cursor:pointer;font-weight:800}.bbrr-link{color:#79c4ff;text-decoration:none}.bbrr-link:hover{text-decoration:underline}@media(max-width:620px){.bbrr-grid{grid-template-columns:1fr}}
</style><div id="bb-review-recovery"><aside id="bb-review-recovery-panel"><div class="bbrr-head"><div><div style="font-size:10px;letter-spacing:.12em;color:#75d7ff;font-weight:900">PROSPECT REVIEW</div><h2 id="bbrr-title" style="margin:6px 0">Priority prospects</h2><div id="bbrr-subtitle" class="bbrr-muted">Accurate, review-ready contacts discovered by Ember.</div></div><button type="button" class="bbrr-close">✕</button></div><div id="bb-review-recovery-body" class="bbrr-list"><div class="bbrr-empty">Loading prospects…</div></div></aside></div>
<script id="bb-control-tower-recovery">(function(){
const root=document.getElementById('bb-review-recovery'),body=document.getElementById('bb-review-recovery-body'),title=document.getElementById('bbrr-title'),subtitle=document.getElementById('bbrr-subtitle');
if(!root||!body)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clean=v=>String(v??'').trim();
function closeReview(){root.classList.remove('open')}
root.querySelector('.bbrr-close').onclick=closeReview;root.onclick=e=>{if(e.target===root)closeReview()};
function showTab(id){const tab=document.getElementById(id);if(!tab)return false;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));tab.classList.add('active');tab.scrollIntoView({behavior:'smooth',block:'start'});return true}
function usefulName(x){const n=clean(x.person_name||x.canonical_person_name);return n&&!/^company contact$/i.test(n)?n:'Company contact'}
function completeness(x){return [x.phone,x.public_email,x.source_url,x.role,x.person_name].filter(v=>clean(v)).length}
function dedupe(items){const seen=new Set();return items.filter(x=>{const key=[clean(x.company_name).toLowerCase(),usefulName(x).toLowerCase(),clean(x.public_email).toLowerCase(),clean(x.phone).replace(/\D/g,'')].join('|');if(seen.has(key))return false;seen.add(key);return completeness(x)>=2||usefulName(x)!=='Company contact';})}
function tag(text,kind=''){return `<span class="bbrr-tag ${kind}">${esc(text)}</span>`}
function card(x){const name=usefulName(x),company=clean(x.company_name)||'Unknown company',state=clean(x.state),score=Number(x.opportunity_score||0),details=[];if(clean(x.role))details.push(tag(x.role,'good'));if(clean(x.public_email))details.push(tag('Email found','good'));if(clean(x.phone))details.push(tag('Phone found','good'));if(clean(x.source_url))details.push(tag('Source linked','good'));if(!clean(x.public_email)&&!clean(x.phone))details.push(tag('Contact details incomplete','warn'));return `<article class="bbrr-item" tabindex="0" role="link" data-contact-id="${esc(x.id||'')}" aria-label="Verify ${esc(name)} at ${esc(company)}"><div class="bbrr-row"><div><b>${esc(name)}</b><div class="bbrr-muted">${esc(company)}${state?' · '+esc(state):''}</div></div><div class="bbrr-score" title="Opportunity score">${score}</div></div><div class="bbrr-tags">${details.join('')}</div><div class="bbrr-muted" style="margin-top:10px">${esc(clean(x.next_best_action)||'Open the verification record and confirm the public evidence.')}</div><div style="margin-top:10px;color:#79c4ff;font-weight:800">Open verification →</div></article>`}
async function openReview(mode='pending'){
 root.classList.add('open');title.textContent='Priority prospects';subtitle.textContent='Accurate, review-ready contacts discovered by Ember.';body.className='bbrr-list';body.innerHTML='<div class="bbrr-empty">Loading prospects…</div>';
 const params=new URLSearchParams({limit:'200'});if(mode==='pending')params.set('status','Pending review');if(mode==='high')params.set('high','1');
 try{const r=await fetch('/api/platform/sprint38/contacts?'+params.toString(),{credentials:'same-origin'}),d=await r.json();if(!r.ok)throw new Error(d.error||'Unable to load prospects');const items=dedupe(d.items||[]).sort((a,b)=>(Number(b.opportunity_score||0)-Number(a.opportunity_score||0))||(completeness(b)-completeness(a)));body.innerHTML=items.length?items.map(card).join(''):'<div class="bbrr-empty">No complete, non-duplicate prospects are waiting for review.</div>'}catch(e){body.innerHTML='<div class="bbrr-empty">'+esc(e.message||e)+'</div>'}
}
function field(label,value,link){if(!clean(value))return '';const shown=esc(value);return `<div><div class="bbrr-label">${esc(label)}</div><div class="bbrr-value">${link?`<a class="bbrr-link" target="_blank" rel="noopener" href="${esc(link)}">${shown}</a>`:shown}</div></div>`}
async function openVerification(id){
 if(!id)return;root.classList.add('open');title.textContent='Verify prospect';subtitle.textContent='Confirm the public evidence before approval.';body.className='bbrr-detail';body.innerHTML='<div class="bbrr-empty">Loading verification record…</div>';location.hash='verify-contact-'+id;
 try{const r=await fetch('/api/platform/sprint38/contacts/'+encodeURIComponent(id),{credentials:'same-origin'}),x=await r.json();if(!r.ok)throw new Error(x.error||'Unable to load record');let reasons=[];try{reasons=JSON.parse(x.reasons_json||'[]')}catch(_){reasons=[]}const source=clean(x.source_url);body.innerHTML=`<button class="bbrr-back" type="button">← Back to priority prospects</button><section class="bbrr-section"><div class="bbrr-row"><div><h2 style="margin:0 0 4px">${esc(usefulName(x))}</h2><div class="bbrr-muted">${esc(clean(x.canonical_company_name||x.company_name)||'Unknown company')} · ${esc(clean(x.state))}</div></div><div class="bbrr-score">${esc(x.opportunity_score||0)}</div></div><div class="bbrr-tags">${clean(x.review_status)?tag(x.review_status):''}${clean(x.ai_confidence)?tag('Confidence '+x.ai_confidence):''}${clean(x.product_fit)?tag(x.product_fit,'good'):''}</div></section><section class="bbrr-section"><h3 style="margin-top:0">Contact and identity</h3><div class="bbrr-grid">${field('Name',x.canonical_person_name||x.person_name)}${field('Role',x.role)}${field('Company',x.canonical_company_name||x.company_name)}${field('State',x.state)}${field('Phone',x.phone,x.phone?'tel:'+String(x.phone).replace(/[^+\d]/g,''):'')}${field('Public email',x.public_email,x.public_email?'mailto:'+x.public_email:'')}</div></section><section class="bbrr-section"><h3 style="margin-top:0">Public evidence</h3><div class="bbrr-grid">${field('Source website',source,source)}${field('Source domain',x.source_domain)}${field('Discovery method',x.discovery_method||x.source_type)}${field('Last observed',x.updated_at||x.created_at)}</div>${source?'':'<div class="bbrr-tag warn" style="margin-top:12px">No source URL is attached. Keep pending or reject until evidence is found.</div>'}</section><section class="bbrr-section"><h3 style="margin-top:0">AI review guidance</h3><div>${esc(clean(x.next_best_action)||'Verify the source, identity, and contact information.')}</div>${reasons.length?'<ul>'+reasons.map(r=>'<li>'+esc(typeof r==='string'?r:JSON.stringify(r))+'</li>').join('')+'</ul>':''}</section><div class="bbrr-actions"><button class="bbrr-btn approve" data-review-action="approve">Approve verified record</button><button class="bbrr-btn pending" data-review-action="pending">Keep pending</button><button class="bbrr-btn reject" data-review-action="reject">Reject record</button></div>`;body.querySelector('.bbrr-back').onclick=()=>{location.hash='review';openReview('pending')}}catch(e){body.innerHTML='<div class="bbrr-empty">'+esc(e.message||e)+'</div>'}
}
async function review(id,action,button){button.disabled=true;const old=button.textContent;button.textContent='Saving…';try{const r=await fetch('/api/platform/sprint38/contacts/'+encodeURIComponent(id)+'/review',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})}),d=await r.json();if(!r.ok)throw new Error(d.error||'Unable to save review');location.hash='review';await openReview('pending')}catch(e){button.disabled=false;button.textContent=old;alert(e.message||e)}}
function routeHash(){const h=(location.hash||'').slice(1).toLowerCase();const m=h.match(/^verify-contact-(\d+)$/);if(m){openVerification(m[1]);return}if(['review','contacts','companies'].includes(h)){openReview(h==='review'?'pending':h==='contacts'?'all':'high');return}const map={activity:'emberLive',live:'emberLive',discovery:'operations',warehouse:'warehouse',ai:'ai',autonomy:'autonomy',imports:'imports',briefing:'briefing',national:'operations'};if(map[h])showTab(map[h])}
document.addEventListener('click',e=>{
 const item=e.target.closest('.bbrr-item[data-contact-id]');if(item){e.preventDefault();e.stopImmediatePropagation();openVerification(item.dataset.contactId);return}
 const action=e.target.closest('[data-review-action]');if(action){e.preventDefault();const m=(location.hash||'').match(/verify-contact-(\d+)/);if(m)review(m[1],action.dataset.reviewAction,action);return}
 const cardEl=e.target.closest('.card,.s41-card');if(cardEl){const cardText=(cardEl.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();if(/pending review|high opportunity|priority review|contacts found/.test(cardText)){e.preventDefault();e.stopImmediatePropagation();location.hash='review';openReview(/high opportunity/.test(cardText)?'high':'pending');return}}
 const b=e.target.closest('button,a');if(!b)return;const text=(b.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();if(b.matches('[data-tab]')){e.preventDefault();e.stopImmediatePropagation();showTab(b.dataset.tab);location.hash=b.dataset.tab;return}if(b.id==='s41Review'||/open priority review|start review|review prospects|priority reviews/.test(text)){e.preventDefault();e.stopImmediatePropagation();location.hash='review';openReview('pending')}
},true);
document.addEventListener('keydown',e=>{const item=e.target.closest&&e.target.closest('.bbrr-item[data-contact-id]');if(item&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openVerification(item.dataset.contactId)}});
window.addEventListener('hashchange',routeHash);routeHash();
})();</script>'''


def install_control_tower_recovery(app):
    """Append the recovery script after every other Control Tower enhancement."""
    @app.after_request
    def recover_control_tower(response):
        if request.path != "/platform/control-tower":
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            html = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "bb-control-tower-recovery" in html or "</body>" not in html.lower():
            return response
        pos = html.lower().rfind("</body>")
        html = html[:pos] + RECOVERY_SCRIPT + html[pos:]
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app
