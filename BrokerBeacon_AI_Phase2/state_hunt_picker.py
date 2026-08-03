"""Add a simple state selector beside the Ember Hunt action on Control Tower."""
from __future__ import annotations

from flask import request


STATE_HUNT_SCRIPT = r'''<style id="bb-state-hunt-style">
#bb-state-hunt{display:grid;grid-template-columns:minmax(180px,1fr) minmax(120px,.45fr);gap:10px;margin:14px 0 10px}
#bb-state-hunt label{display:grid;gap:6px;font-size:12px;font-weight:800;color:#b8cae2}
#bb-state-hunt select,#bb-state-hunt input{width:100%;box-sizing:border-box;border:1px solid #ffffff24;border-radius:10px;background:#07172f;color:#fff;padding:11px 12px;font:inherit;outline:none}
#bb-state-hunt select:focus,#bb-state-hunt input:focus{border-color:#65b8ff;box-shadow:0 0 0 3px #65b8ff20}
#bb-state-hunt-note{font-size:12px;color:#9fb4cf;margin:0 0 10px}
#bb-state-hunt-status{min-height:20px;font-size:13px;font-weight:700;margin-top:8px;color:#79efc0}
@media(max-width:620px){#bb-state-hunt{grid-template-columns:1fr}}
</style>
<script id="bb-state-hunt-picker">(function(){
const states=[['AL','Alabama'],['AK','Alaska'],['AZ','Arizona'],['AR','Arkansas'],['CA','California'],['CO','Colorado'],['CT','Connecticut'],['DE','Delaware'],['FL','Florida'],['GA','Georgia'],['HI','Hawaii'],['ID','Idaho'],['IL','Illinois'],['IN','Indiana'],['IA','Iowa'],['KS','Kansas'],['KY','Kentucky'],['LA','Louisiana'],['ME','Maine'],['MD','Maryland'],['MA','Massachusetts'],['MI','Michigan'],['MN','Minnesota'],['MS','Mississippi'],['MO','Missouri'],['MT','Montana'],['NE','Nebraska'],['NV','Nevada'],['NH','New Hampshire'],['NJ','New Jersey'],['NM','New Mexico'],['NY','New York'],['NC','North Carolina'],['ND','North Dakota'],['OH','Ohio'],['OK','Oklahoma'],['OR','Oregon'],['PA','Pennsylvania'],['RI','Rhode Island'],['SC','South Carolina'],['SD','South Dakota'],['TN','Tennessee'],['TX','Texas'],['UT','Utah'],['VT','Vermont'],['VA','Virginia'],['WA','Washington'],['WV','West Virginia'],['WI','Wisconsin'],['WY','Wyoming'],['DC','District of Columbia']];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function findLaunch(){return [...document.querySelectorAll('button,a')].find(x=>/launch ember hunt/i.test((x.textContent||'').replace(/\s+/g,' ').trim()))}
function install(){
 const launch=findLaunch();if(!launch||document.getElementById('bb-state-hunt'))return;
 const saved=(localStorage.getItem('bb-ember-state')||'NC').toUpperCase();
 const wrap=document.createElement('div');wrap.id='bb-state-hunt';wrap.innerHTML=`<label>Choose state<select id="bb-ember-state">${states.map(([code,name])=>`<option value="${code}"${code===saved?' selected':''}>${name} (${code})</option>`).join('')}</select></label><label>Companies per hunt<input id="bb-ember-company-limit" type="number" min="1" max="25" value="6"></label>`;
 const note=document.createElement('div');note.id='bb-state-hunt-note';note.textContent='Choose a state, then launch. Ember will queue a safe, review-gated hunt with no automatic outreach.';
 const status=document.createElement('div');status.id='bb-state-hunt-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 launch.parentNode.insertBefore(wrap,launch);launch.parentNode.insertBefore(note,launch);launch.parentNode.insertBefore(status,launch.nextSibling);
 const select=wrap.querySelector('#bb-ember-state');select.addEventListener('change',()=>localStorage.setItem('bb-ember-state',select.value));
 launch.dataset.bbStatePicker='1';
}
async function queueHunt(button){
 const select=document.getElementById('bb-ember-state'),limit=document.getElementById('bb-ember-company-limit'),status=document.getElementById('bb-state-hunt-status');
 if(!select||!status)return false;
 const state=select.value,companyLimit=Math.max(1,Math.min(25,Number(limit&&limit.value||6)));
 localStorage.setItem('bb-ember-state',state);button.disabled=true;const old=button.textContent;button.textContent='Queuing '+state+' hunt…';status.textContent='';
 try{const r=await fetch('/api/platform/ember-queue/discovery',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({state,company_limit:companyLimit,contact_limit:250,priority:50})}),d=await r.json();if(!r.ok)throw new Error(d.error||'Unable to queue hunt');status.textContent=`${state} hunt queued successfully · Job #${esc(d.id||'')}`;button.textContent='🔥 Launch '+state+' Ember Hunt';setTimeout(()=>{button.disabled=false},1200);return true}catch(e){status.style.color='#ff9d9d';status.textContent=e.message||String(e);button.disabled=false;button.textContent=old;return false}
}
document.addEventListener('click',e=>{const b=e.target.closest('button,a');if(!b||b.dataset.bbStatePicker!=='1')return;e.preventDefault();e.stopImmediatePropagation();queueHunt(b)},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
new MutationObserver(install).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''


def install_state_hunt_picker(app):
    @app.after_request
    def add_state_hunt_picker(response):
        if request.path != "/platform/control-tower":
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            html = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "bb-state-hunt-picker" in html or "</body>" not in html.lower():
            return response
        pos = html.lower().rfind("</body>")
        html = html[:pos] + STATE_HUNT_SCRIPT + html[pos:]
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app
