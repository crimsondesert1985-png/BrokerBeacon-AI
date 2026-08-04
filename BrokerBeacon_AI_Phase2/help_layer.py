"""Sitewide contextual help, hover explanations, and optional coaching tips."""
from flask import request

PUBLIC_PREFIXES = ("/login", "/register", "/invite", "/password", "/static")

HELP_LAYER = r'''<style id="brokerbeacon-help-layer-style">
#bb-help-tip{position:fixed;right:18px;bottom:18px;z-index:500;width:min(360px,calc(100vw - 36px));background:#0f1d33;color:#f7fbff;border:1px solid #ffffff26;border-radius:16px;box-shadow:0 22px 60px #0008;padding:15px;display:none}
#bb-help-tip.show{display:block;animation:bbHelpIn .22s ease-out}.bb-help-head{display:flex;justify-content:space-between;gap:12px;align-items:start}.bb-help-kicker{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#7de7ff;font-weight:900}.bb-help-title{font-size:15px;font-weight:850;margin:3px 0 5px}.bb-help-copy{font-size:12px;line-height:1.5;color:#c4d2e6}.bb-help-close{border:0;background:transparent;color:white;font-size:18px;cursor:pointer}.bb-help-actions{display:flex;justify-content:space-between;gap:8px;margin-top:12px}.bb-help-actions button{border:1px solid #ffffff2a;background:#ffffff0d;color:white;border-radius:9px;padding:7px 9px;cursor:pointer;font-size:11px}
#bb-help-tooltip{position:fixed;z-index:700;max-width:300px;padding:9px 11px;border-radius:10px;background:#08111f;color:#f6f9ff;border:1px solid #ffffff24;box-shadow:0 12px 35px #0008;font-size:11px;line-height:1.45;pointer-events:none;opacity:0;transform:translateY(4px);transition:.12s}#bb-help-tooltip.show{opacity:1;transform:none}
#bb-help-toggle{position:fixed;right:18px;bottom:18px;z-index:490;border:1px solid #ffffff2b;background:#0f1d33;color:#fff;border-radius:999px;padding:8px 11px;box-shadow:0 10px 30px #0006;font-size:11px;font-weight:800;cursor:pointer}#bb-help-tip.show+#bb-help-toggle{display:none}
@keyframes bbHelpIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@media(max-width:640px){#bb-help-tip,#bb-help-toggle{right:10px;bottom:10px}}
@media(prefers-reduced-motion:reduce){#bb-help-tip.show{animation:none}#bb-help-tooltip{transition:none}}
</style>
<div id="bb-help-tooltip" role="tooltip"></div>
<div id="bb-help-tip" role="status" aria-live="polite"><div class="bb-help-head"><div><div class="bb-help-kicker">BrokerBeacon tip</div><div id="bb-help-title" class="bb-help-title"></div><div id="bb-help-copy" class="bb-help-copy"></div></div><button id="bb-help-close" class="bb-help-close" aria-label="Close tip">×</button></div><div class="bb-help-actions"><button id="bb-help-next">Next tip</button><button id="bb-help-disable">Turn tips off</button></div></div>
<button id="bb-help-toggle" type="button" aria-pressed="true" title="Turn BrokerBeacon coaching tips on or off">Tips: On</button>
<script id="brokerbeacon-help-layer">(function(){
const tooltip=document.getElementById('bb-help-tooltip'),tip=document.getElementById('bb-help-tip'),toggle=document.getElementById('bb-help-toggle');
const title=document.getElementById('bb-help-title'),copy=document.getElementById('bb-help-copy');
const tips=[
['Start with the next action','Open a prospect and use the recommended next action instead of deciding from scratch.'],
['Hover for explanations','Pause over a button, field, card, or navigation item to see what it does.'],
['Keep outreach controlled','Campaigns stay in review until you approve them. Pause or stop an enrollment at any time.'],
['Use one workspace at a time','Prospects is for finding and reviewing. Outreach is for calls, email, text, and follow-up.'],
['Record the outcome','Logging what happened keeps the pipeline and future follow-ups accurate.'],
['Missing information is actionable','A blank email or phone field means the next step is contact research, not guesswork.']
];
let tipsOn=localStorage.getItem('bbTipsOn')!=='false',index=Number(localStorage.getItem('bbTipIndex')||0)%tips.length,timer=null;
function label(el){return (el.getAttribute('aria-label')||el.dataset.help||el.title||el.placeholder||el.textContent||'').replace(/\s+/g,' ').trim().replace(/^\d+\s*/,'')}
function explanation(el){if(el.dataset.help)return el.dataset.help;const s=label(el);if(!s)return'';const l=s.toLowerCase();if(el.disabled)return s+' is currently unavailable. Another setup step, permission, or connection may be required.';if(el.matches('input,textarea'))return 'Enter '+(el.placeholder||s).replace(/[.:]$/,'').toLowerCase()+'.';if(el.matches('select'))return 'Choose the option that controls '+s.toLowerCase()+'.';if(el.matches('a'))return 'Open '+s+'.';if(/save|create|add|apply|start|activate|approve/.test(l))return s+'. This creates or activates the related item after validation.';if(/delete|remove|stop|disable/.test(l))return s+'. This is a destructive or stopping action; review before continuing.';if(/pause/.test(l))return s+'. This temporarily stops activity without deleting the item.';if(/resume/.test(l))return s+'. This continues a previously paused process.';if(/search|find|scout|watchtower/.test(l))return s+'. Use this to locate and prioritize matching prospects.';if(/email|text|sms|call|voice|outreach/.test(l))return s+'. Use this to prepare or record prospect communication.';if(/home|prospects|intelligence|settings|campaign/.test(l))return s+'. Open this workspace to manage the related BrokerBeacon tools.';return s+'. Select this to open or perform the related action.'}
function showTooltip(el){const msg=explanation(el);if(!msg)return;tooltip.textContent=msg;tooltip.classList.add('show');const r=el.getBoundingClientRect(),w=tooltip.offsetWidth,h=tooltip.offsetHeight;let left=Math.min(window.innerWidth-w-10,Math.max(10,r.left+r.width/2-w/2));let top=r.top-h-10;if(top<8)top=Math.min(window.innerHeight-h-8,r.bottom+10);tooltip.style.left=left+'px';tooltip.style.top=top+'px';el.setAttribute('aria-describedby','bb-help-tooltip')}
function hideTooltip(el){tooltip.classList.remove('show');if(el&&el.getAttribute('aria-describedby')==='bb-help-tooltip')el.removeAttribute('aria-describedby')}
function eligible(el){return el&&el.closest&&el.closest('button,a,input,select,textarea')}
const siteOwnsTooltips=typeof window.showSiteTooltip==='function';
if(!siteOwnsTooltips){document.addEventListener('mouseover',e=>{const el=eligible(e.target);if(el)showTooltip(el)});document.addEventListener('mouseout',e=>{const el=eligible(e.target);if(el)hideTooltip(el)});document.addEventListener('focusin',e=>{const el=eligible(e.target);if(el)showTooltip(el)});document.addEventListener('focusout',e=>hideTooltip(e.target))}else{tooltip.remove()}
function sync(){toggle.textContent='Tips: '+(tipsOn?'On':'Off');toggle.setAttribute('aria-pressed',String(tipsOn));localStorage.setItem('bbTipsOn',String(tipsOn));if(!tipsOn)tip.classList.remove('show')}
function showTip(force){if(!tipsOn||document.visibilityState==='hidden')return;const t=tips[index];title.textContent=t[0];copy.textContent=t[1];tip.classList.add('show');localStorage.setItem('bbTipIndex',String(index));if(!force){clearTimeout(timer);timer=setTimeout(()=>tip.classList.remove('show'),11000)}}
function next(){index=(index+1)%tips.length;showTip(true)}
toggle.onclick=()=>{tipsOn=!tipsOn;sync();if(tipsOn)showTip(true)};document.getElementById('bb-help-close').onclick=()=>tip.classList.remove('show');document.getElementById('bb-help-next').onclick=next;document.getElementById('bb-help-disable').onclick=()=>{tipsOn=false;sync()};sync();
if(tipsOn){setTimeout(()=>showTip(false),14000);setInterval(()=>{if(!tip.classList.contains('show')){index=(index+1)%tips.length;showTip(false)}},90000)}
new MutationObserver(()=>document.querySelectorAll('button,a,input,select,textarea,[role="button"]').forEach(el=>{if(!el.title&&!el.dataset.help){const x=explanation(el);if(x)el.dataset.help=x}})).observe(document.body,{childList:true,subtree:true});
})();</script>'''


def install_help_layer(app):
    @app.after_request
    def inject_help_layer(response):
        if request.path.startswith(PUBLIC_PREFIXES):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-help-layer" in body or "</body>" not in body.lower():
            return response
        pos = body.lower().rfind("</body>")
        body = body[:pos] + HELP_LAYER + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response
    return app
