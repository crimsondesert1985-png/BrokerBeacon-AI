"""Sprint 39 visual operations layer for the Ember Command Center."""
from __future__ import annotations

def install_sprint39_ux(app):
 @app.after_request
 def enhance(response):
  if response.status_code!=200 or not response.is_sequence:return response
  try:
   from flask import request
   if request.path!='/platform/control-tower':return response
   html=response.get_data(as_text=True)
   marker='<section id="operations" class="tab">'
   block='''<section id="emberLive" class="tab"><div class="grid"><div class="panel"><div class="head"><div><h2>Live Ember activity</h2><p class="muted">What Ember has discovered, queued, and completed.</p></div><button onclick="loadSprint39()">Refresh</button></div><div id="emberActivity" class="s39-feed"><div class="empty">Loading activity…</div></div></div><div class="panel"><h2>Crawler health</h2><div id="emberHealth" class="empty">Loading health…</div><h3 style="margin-top:18px">State progress</h3><div id="emberStates" class="empty">Loading states…</div></div></div><div class="panel" style="margin-top:14px"><h2>Today's priority prospects</h2><p class="muted">The strongest review-ready contacts across Ember's approved states.</p><div id="emberPriorities" class="s39-priorities"><div class="empty">Loading priorities…</div></div></div></section>'''
   html=html.replace(marker,block+marker)
   html=html.replace('<button data-tab="operations">Discovery</button>','<button data-tab="emberLive">Live Activity</button><button data-tab="operations">Discovery</button>')
   html=html.replace('</style>','.s39-feed{display:grid;gap:9px;max-height:520px;overflow:auto}.s39-event{display:grid;grid-template-columns:12px 1fr auto;gap:10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:#081b38}.s39-dot{width:9px;height:9px;border-radius:50%;background:#58a6ff;margin-top:5px}.s39-event.success .s39-dot{background:#4bd19b}.s39-event.error .s39-dot{background:#ff7d93}.s39-time{font-size:10px;color:var(--muted)}.s39-priorities{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.s39-priority{padding:14px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(135deg,#102547,#0b1d39);cursor:pointer}.s39-priority:hover{border-color:#58a6ff77;transform:translateY(-2px)}.s39-state{display:grid;grid-template-columns:40px 1fr 90px;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}@media(max-width:900px){.s39-priorities{grid-template-columns:1fr}}</style>')
   script=r'''<script id="sprint39-ops">
function s39time(v){if(!v)return'';try{return new Date(v).toLocaleString()}catch(_){return v}}
async function loadSprint39(){try{let d=await api('/api/platform/sprint39/overview');emberActivity.innerHTML=d.activity.length?d.activity.map(x=>`<div class="s39-event ${x.severity||''}"><span class="s39-dot"></span><div><b>${esc(x.title)}</b><div class="muted">${esc(x.detail||'')}${x.company_name?' · '+esc(x.company_name):''}</div></div><span class="s39-time">${esc(s39time(x.created_at))}</span></div>`).join(''):'<div class="empty">Ember has not logged activity yet.</div>';let h=d.health||{};emberHealth.innerHTML=`<div class="cards" style="grid-template-columns:repeat(3,1fr)"><div class="card"><span class="muted">Status</span><strong style="font-size:18px">${esc(h.status||'Unknown')}</strong></div><div class="card"><span class="muted">Completed 24h</span><strong>${h.completed_24h||0}</strong></div><div class="card"><span class="muted">Failures 24h</span><strong>${h.failures_24h||0}</strong></div></div><div class="muted">Queue: ${esc(JSON.stringify(h.queue||{}))}</div>`;emberStates.innerHTML=d.states.length?d.states.map(x=>`<div class="s39-state"><b>${esc(x.state)}</b><div><div class="bar"><i style="width:${Math.min(100,(x.companies_processed||0)*4+4)}%"></i></div><span class="muted">${x.companies_processed||0} companies · ${x.contacts_found||0} contacts</span></div><span class="s39-time">${esc(s39time(x.last_run_at))}</span></div>`).join(''):'<div class="empty">State cursors initialize after the next scheduled hunt.</div>';emberPriorities.innerHTML=d.priorities.length?d.priorities.map(x=>`<div class="s39-priority" onclick="openContact(${x.id})"><div class="s38-row"><div><b>${esc(x.person_name||'Company contact')}</b><div class="muted">${esc(x.company_name||'')} · ${esc(x.state||'')}</div></div><div class="s38-score">${x.opportunity_score||0}</div></div><p class="muted">${esc(x.next_best_action||'Review this prospect.')}</p></div>`).join(''):'<div class="empty">No pending priorities yet.</div>'}catch(e){if(window.fail)fail(e)}}
document.addEventListener('DOMContentLoaded',()=>{loadSprint39();setInterval(loadSprint39,60000)});
</script>'''
   pos=html.lower().rfind('</body>');html=html[:pos]+script+html[pos:]
   response.set_data(html);response.headers['Content-Length']=str(len(response.get_data()))
  except Exception:app.logger.exception('Sprint 39 UX enhancement failed')
  return response
 return app
