"""Final demo-readiness polish for BrokerBeacon's shared application shell."""
from __future__ import annotations


STYLE = r"""
<style id="brokerbeacon-demo-ready-style">
:root{
  --bb-nav:#081a35;
  --bb-nav-2:#0d2447;
  --bb-nav-border:rgba(159,190,235,.16);
  --bb-nav-text:#eaf2ff;
  --bb-nav-muted:#91a8c8;
  --bb-accent:#5b7cff;
  --bb-accent-2:#2ed3c6;
  --bb-shadow:0 18px 45px rgba(3,15,35,.22);
}
aside{
  background:linear-gradient(180deg,var(--bb-nav) 0%,#07152b 100%)!important;
  border-right:1px solid var(--bb-nav-border)!important;
  box-shadow:12px 0 32px rgba(4,17,40,.13)!important;
}
aside nav,aside .bb-legacy-list{gap:4px!important}
aside button,aside a{
  transition:background .18s ease,border-color .18s ease,transform .18s ease,color .18s ease!important;
}
aside button:hover,aside a:hover{transform:translateX(2px)}
.bb-platform-tools{
  margin:18px 8px 8px;
  padding-top:14px;
  border-top:1px solid var(--bb-nav-border);
}
.bb-platform-tools-label{
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 4px 9px;
  color:#7893b9;
  font-size:10px;
  font-weight:850;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.bb-platform-tools-label span:last-child{
  color:#4ee0cf;
  font-size:9px;
  letter-spacing:.08em;
}
.bb-module-button{
  width:100%!important;
  min-height:58px!important;
  display:grid!important;
  grid-template-columns:34px minmax(0,1fr) auto!important;
  gap:10px!important;
  align-items:center!important;
  margin:7px 0!important;
  padding:9px 10px!important;
  text-align:left!important;
  border:1px solid rgba(147,181,232,.13)!important;
  border-radius:13px!important;
  background:linear-gradient(135deg,rgba(255,255,255,.055),rgba(255,255,255,.018))!important;
  color:var(--bb-nav-text)!important;
  box-shadow:inset 0 1px rgba(255,255,255,.04)!important;
}
.bb-module-button:hover{
  border-color:rgba(105,139,255,.48)!important;
  background:linear-gradient(135deg,rgba(91,124,255,.18),rgba(46,211,198,.07))!important;
  box-shadow:0 10px 24px rgba(3,13,31,.24),inset 0 1px rgba(255,255,255,.06)!important;
}
.bb-module-icon{
  width:34px;height:34px;border-radius:10px;
  display:grid;place-items:center;
  font-size:16px;
  background:linear-gradient(145deg,rgba(91,124,255,.28),rgba(46,211,198,.14));
  border:1px solid rgba(143,171,255,.22);
}
.bb-module-copy{min-width:0;display:block}
.bb-module-name{display:block;font-size:12px;font-weight:820;line-height:1.2;color:#f7faff}
.bb-module-desc{display:block;margin-top:3px;font-size:9px;line-height:1.25;color:var(--bb-nav-muted);white-space:normal}
.bb-module-badge{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:44px;padding:4px 6px;border-radius:999px;
  background:rgba(46,211,198,.1);border:1px solid rgba(46,211,198,.2);
  color:#72eadf;font-size:8px;font-weight:850;letter-spacing:.06em;text-transform:uppercase;
}
.bb-module-button[data-module="ember"] .bb-module-icon{background:linear-gradient(145deg,rgba(255,126,80,.28),rgba(255,184,77,.12));border-color:rgba(255,157,91,.25)}
.bb-module-button[data-module="team"] .bb-module-icon{background:linear-gradient(145deg,rgba(91,124,255,.3),rgba(115,92,255,.14))}
.bb-module-button[data-module="beacon"] .bb-module-icon{background:linear-gradient(145deg,rgba(46,211,198,.27),rgba(30,132,255,.12))}
.bb-module-button[data-module="drip"] .bb-module-icon{background:linear-gradient(145deg,rgba(191,95,255,.24),rgba(91,124,255,.13))}
#platform-owner-badge{
  margin:12px 8px 2px!important;padding:7px 9px!important;
  color:#7de7d9!important;background:rgba(46,211,198,.08)!important;
  border:1px solid rgba(46,211,198,.16)!important;
  font-size:9px!important;letter-spacing:.08em!important;text-transform:uppercase!important;
}
main,.main-content{background:linear-gradient(180deg,#f7faff 0%,#f2f6fc 100%)!important}
.panel,.card,.metric,[class*="panel"],[class*="card"]{border-color:rgba(79,110,157,.13)}
button,.btn,a.button{border-radius:10px}
table{box-shadow:0 12px 30px rgba(24,49,83,.06)}
@media(max-width:900px){.bb-platform-tools{margin-left:4px;margin-right:4px}.bb-module-desc{display:none}.bb-module-button{min-height:48px!important}}
</style>
"""

SCRIPT = r"""
<script id="brokerbeacon-demo-ready-script">
(function(){
  const modules={
    'ember-control-tower-button':{key:'ember',icon:'🔥',name:'Ember Control Tower',desc:'Discovery, enrichment and prospect operations',badge:'Live',href:'/platform/control-tower'},
    'team-access-button':{key:'team',icon:'👥',name:'Team & Access',desc:'Users, roles and workspace permissions',badge:'Manage',href:'/workspace/team'},
    'beaconmatch-button':{key:'beacon',icon:'✦',name:'BeaconMatch',desc:'Scenario intelligence and opportunity matching',badge:'AI',href:'/intelligence/scenario-rescue'},
    'drip-campaigns-button':{key:'drip',icon:'◫',name:'Drip Campaigns',desc:'Approved follow-up sequences and enrollment',badge:'Outreach',href:'/outreach/campaigns'}
  };
  function navRoot(){return document.querySelector('.bb-legacy-list')||document.querySelector('aside nav')||document.querySelector('aside')}
  function ensureButton(id,cfg,root){
    let b=document.getElementById(id);
    if(!b){b=document.createElement('button');b.id=id;b.type='button';root.appendChild(b)}
    b.classList.add('bb-module-button');b.dataset.module=cfg.key;
    b.innerHTML='<span class="bb-module-icon">'+cfg.icon+'</span><span class="bb-module-copy"><span class="bb-module-name">'+cfg.name+'</span><span class="bb-module-desc">'+cfg.desc+'</span></span><span class="bb-module-badge">'+cfg.badge+'</span>';
    b.onclick=function(e){e.preventDefault();location.href=cfg.href};
    return b;
  }
  function polish(){
    const root=navRoot();if(!root)return;
    let group=document.querySelector('.bb-platform-tools');
    if(!group){
      group=document.createElement('div');group.className='bb-platform-tools';
      group.innerHTML='<div class="bb-platform-tools-label"><span>Platform tools</span><span>Demo ready</span></div>';
      const owner=document.getElementById('platform-owner-badge');
      root.insertBefore(group,owner||null);
    }
    Object.keys(modules).forEach(function(id){const b=ensureButton(id,modules[id],root);if(b.parentElement!==group)group.appendChild(b)});
    const owner=document.getElementById('platform-owner-badge');if(owner&&owner.previousElementSibling!==group)root.insertBefore(group,owner);
    document.querySelectorAll('button,a').forEach(function(el){
      const t=(el.textContent||'').trim();
      if(t==='Add Prospect')el.setAttribute('title','Create a prospect manually');
      if(t==='Export CSV')el.setAttribute('title','Export the current prospect view');
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',polish);else polish();
  new MutationObserver(function(){clearTimeout(window.__bbDemoPolish);window.__bbDemoPolish=setTimeout(polish,80)}).observe(document.documentElement,{childList:true,subtree:true});
})();
</script>
"""


def install_demo_ready_ux(app):
    @app.after_request
    def demo_ready_shell(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-demo-ready-script" in body or "</body>" not in body.lower():
            return response
        head_pos = body.lower().find("</head>")
        if head_pos >= 0:
            body = body[:head_pos] + STYLE + body[head_pos:]
        body_pos = body.lower().rfind("</body>")
        body = body[:body_pos] + SCRIPT + body[body_pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    app.logger.warning("DEMO_READY_UX installed shared navigation and presentation polish")
    return app


__all__ = ["install_demo_ready_ux"]
