"""Site-wide guided workflow and progressive navigation for BrokerBeacon."""
from __future__ import annotations

from flask import g, request


FLOW_SCRIPT = r'''<style id="brokerbeacon-simple-flow-style">
#bb-simple-flow{margin:0 0 18px;padding:14px;border:1px solid #ffffff20;border-radius:16px;background:linear-gradient(135deg,#7c5cff18,#23d4fd12);box-shadow:0 16px 40px #0003}
#bb-simple-flow .bb-flow-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px}
#bb-simple-flow .bb-flow-head b{font-size:14px}#bb-simple-flow .bb-flow-head span{font-size:11px;color:#9aa5c8}
#bb-simple-flow .bb-flow-actions{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
#bb-simple-flow button{border:1px solid #ffffff20;background:#ffffff0b;color:white;border-radius:11px;padding:10px 8px;cursor:pointer;text-align:left;min-height:58px}
#bb-simple-flow button:hover{background:#ffffff18;transform:translateY(-1px)}#bb-simple-flow button strong{display:block;font-size:12px;margin-bottom:4px}#bb-simple-flow button small{display:block;color:#9aa5c8;font-size:10px;line-height:1.3}
.bb-nav-more{margin-top:8px;border-top:1px solid #ffffff17;padding-top:8px}.bb-nav-more summary{cursor:pointer;color:#9aa5c8;padding:9px 12px;list-style:none}.bb-nav-more summary::-webkit-details-marker{display:none}.bb-nav-more summary:after{content:' +';float:right}.bb-nav-more[open] summary:after{content:' −'}
@media(max-width:850px){#bb-simple-flow .bb-flow-actions{grid-template-columns:1fr 1fr}#bb-simple-flow .bb-flow-actions button:last-child{grid-column:1/-1}}
@media(max-width:520px){#bb-simple-flow .bb-flow-actions{grid-template-columns:1fr}#bb-simple-flow .bb-flow-actions button:last-child{grid-column:auto}}
</style><script id="brokerbeacon-simple-flow">(function(){
const clean=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
const choices={find:['find prospects','prospect watchtower','scout','discovery','search'],review:['priority','review queue','prospects','watchtower'],contact:['call prep','voice','contact','outreach'],follow:['pipeline','follow','tasks','today'],team:['team & access','team','users']};
function buttons(){return [...document.querySelectorAll('aside nav button,aside button')].filter(b=>!b.closest('#bb-simple-flow'))}
function openChoice(key){const terms=choices[key]||[];const hit=buttons().find(b=>terms.some(t=>clean(b.textContent).includes(t)));if(hit){hit.click();hit.scrollIntoView({behavior:'smooth',block:'nearest'});return}const paths={team:'/workspace/team',find:'/',review:'/',contact:'/',follow:'/'};location.href=paths[key]||'/'}
function explainButtons(){buttons().forEach(b=>{const label=clean(b.textContent);if(!b.title)b.title=b.disabled?'This tool is unavailable for your current role or setup.':('Open '+label+'.');if(b.disabled){b.setAttribute('aria-disabled','true');b.style.cursor='not-allowed'}})}
function simplifyNav(){const nav=document.querySelector('aside nav');if(!nav||nav.dataset.simplified)return;nav.dataset.simplified='1';const all=[...nav.children].filter(x=>x.tagName==='BUTTON');const primaryTerms=['home','today','priority','prospect','pipeline','call prep'];const advanced=all.filter(b=>!primaryTerms.some(t=>clean(b.textContent).includes(t))&&!['team & access','ember control tower'].some(t=>clean(b.textContent).includes(t)));if(advanced.length<4)return;const more=document.createElement('details');more.className='bb-nav-more';const summary=document.createElement('summary');summary.textContent='More tools';more.appendChild(summary);advanced.forEach(b=>more.appendChild(b));nav.appendChild(more)}
function addFlow(){if(document.getElementById('bb-simple-flow'))return;const main=document.querySelector('main');if(!main)return;const flow=document.createElement('section');flow.id='bb-simple-flow';flow.innerHTML='<div class="bb-flow-head"><b>Start here</b><span>Find → Review → Contact → Follow up</span></div><div class="bb-flow-actions"><button data-step="find"><strong>1. Find prospects</strong><small>Search or let Ember discover opportunities.</small></button><button data-step="review"><strong>2. Review matches</strong><small>See why each prospect matters.</small></button><button data-step="contact"><strong>3. Contact</strong><small>Prepare the message or call.</small></button><button data-step="follow"><strong>4. Follow up</strong><small>Record the result and next step.</small></button><button data-step="team"><strong>Manage access</strong><small>Invite users and control roles.</small></button></div>';flow.querySelectorAll('button').forEach(b=>b.onclick=()=>openChoice(b.dataset.step));main.prepend(flow)}
function run(){addFlow();explainButtons();simplifyNav()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();
})();</script>'''


def install_simplified_flow(app):
    """Inject the same clear workflow into authenticated HTML screens."""
    @app.after_request
    def add_simplified_flow(response):
        if not getattr(g, "user_id", None):
            return response
        if request.path.startswith(("/login", "/register", "/invite/", "/forgot-password", "/reset-password")):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-simple-flow" in body or "</body>" not in body.lower():
            return response
        pos = body.lower().rfind("</body>")
        body = body[:pos] + FLOW_SCRIPT + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app
