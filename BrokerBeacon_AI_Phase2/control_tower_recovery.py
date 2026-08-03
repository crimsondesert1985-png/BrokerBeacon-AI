"""Late response-layer recovery for Control Tower navigation and review actions."""
from __future__ import annotations

from flask import request


RECOVERY_SCRIPT = r'''<style id="bb-control-tower-recovery-style">
#bb-prospect-drawer,#bb-prospect-backdrop{display:none!important}
#bb-review-recovery{position:fixed;inset:0;z-index:12000;display:none;background:#020916c7;backdrop-filter:blur(7px)}
#bb-review-recovery.open{display:block}#bb-review-recovery-panel{position:absolute;right:0;top:0;width:min(760px,96vw);height:100%;overflow:auto;background:#081b38;color:#f7fbff;border-left:1px solid #ffffff24;box-shadow:-30px 0 80px #0009;padding:24px}
.bbrr-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.bbrr-close{font-size:20px}.bbrr-list{display:grid;gap:10px}.bbrr-item{padding:14px;border:1px solid #ffffff1e;border-radius:13px;background:#102547;cursor:pointer}.bbrr-item:hover{border-color:#58a6ff66}.bbrr-row{display:flex;justify-content:space-between;gap:12px}.bbrr-muted{color:#a7b7cf}.bbrr-score{font-size:20px;font-weight:900;color:#75d7ff}.bbrr-empty{padding:32px;text-align:center;color:#a7b7cf}
</style><div id="bb-review-recovery"><aside id="bb-review-recovery-panel"><div class="bbrr-head"><div><div style="font-size:10px;letter-spacing:.12em;color:#75d7ff;font-weight:900">PROSPECT REVIEW</div><h2 style="margin:6px 0">Priority prospects</h2><div class="bbrr-muted">Review-ready contacts discovered by Ember.</div></div><button type="button" class="bbrr-close">✕</button></div><div id="bb-review-recovery-body" class="bbrr-list"><div class="bbrr-empty">Loading prospects…</div></div></aside></div>
<script id="bb-control-tower-recovery">(function(){
const root=document.getElementById('bb-review-recovery'),body=document.getElementById('bb-review-recovery-body');
if(!root||!body)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function closeReview(){root.classList.remove('open')}
root.querySelector('.bbrr-close').onclick=closeReview;root.onclick=e=>{if(e.target===root)closeReview()};
function showTab(id){const tab=document.getElementById(id);if(!tab)return false;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));tab.classList.add('active');tab.scrollIntoView({behavior:'smooth',block:'start'});return true}
async function openReview(mode='pending'){
 root.classList.add('open');body.innerHTML='<div class="bbrr-empty">Loading prospects…</div>';
 const params=new URLSearchParams({limit:'200'});if(mode==='pending')params.set('status','Pending review');if(mode==='high')params.set('high','1');
 try{const r=await fetch('/api/platform/sprint38/contacts?'+params.toString(),{credentials:'same-origin'}),d=await r.json();if(!r.ok)throw new Error(d.error||'Unable to load prospects');const items=d.items||[];body.innerHTML=items.length?items.map(x=>`<div class="bbrr-item" data-contact-id="${esc(x.id||'')}"><div class="bbrr-row"><div><b>${esc(x.person_name||x.canonical_person_name||'Company contact')}</b><div class="bbrr-muted">${esc(x.company_name||'Unknown company')} · ${esc(x.state||'')}</div></div><div class="bbrr-score">${esc(x.opportunity_score||0)}</div></div><div class="bbrr-muted" style="margin-top:8px">${esc(x.next_best_action||'Review this prospect.')}</div></div>`).join(''):'<div class="bbrr-empty">No matching prospects are waiting for review.</div>'}catch(e){body.innerHTML='<div class="bbrr-empty">'+esc(e.message||e)+'</div>'}
}
function routeHash(){const h=(location.hash||'').slice(1).toLowerCase();if(['review','contacts','companies'].includes(h)){openReview(h==='review'?'pending':h==='contacts'?'all':'high');return}const map={activity:'emberLive',live:'emberLive',discovery:'operations',warehouse:'warehouse',ai:'ai',autonomy:'autonomy',imports:'imports',briefing:'briefing',national:'operations'};if(map[h])showTab(map[h])}
document.addEventListener('click',e=>{
 const card=e.target.closest('.card,.s41-card');
 if(card){const cardText=(card.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();if(/pending review|high opportunity|priority review|contacts found/.test(cardText)){e.preventDefault();e.stopImmediatePropagation();location.hash='review';openReview(/high opportunity/.test(cardText)?'high':'pending');return}}
 const b=e.target.closest('button,a');if(!b)return;const text=(b.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();if(b.matches('[data-tab]')){e.preventDefault();e.stopImmediatePropagation();showTab(b.dataset.tab);location.hash=b.dataset.tab;return}if(b.id==='s41Review'||/open priority review|start review|review prospects|priority reviews/.test(text)){e.preventDefault();e.stopImmediatePropagation();location.hash='review';openReview('pending')}
},true);
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
