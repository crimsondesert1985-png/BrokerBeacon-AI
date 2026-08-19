"""One-click prospect workflow for BrokerBeacon.

A lightweight workflow layer that works across prospect tables and cards without
requiring every older screen to be rewritten at once.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from html import escape

from flask import g, jsonify, request


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _key(value: str) -> str:
    return hashlib.sha256((value or "").strip().lower().encode("utf-8")).hexdigest()[:24]


def install_prospect_flow(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.execute(
            """create table if not exists prospect_workflow_events(
                id integer primary key,
                workspace_id integer not null default 0,
                user_id integer not null default 0,
                prospect_key text not null,
                prospect_name text not null,
                action text not null,
                channel text default '',
                stage text not null,
                outcome text default '',
                follow_up_at text default '',
                note text default '',
                created_at text not null
            )"""
        )
        conn.execute(
            "create index if not exists idx_prospect_flow_lookup on prospect_workflow_events(workspace_id,prospect_key,id desc)"
        )

    @app.get("/api/prospect-flow/status/<prospect_key>")
    def prospect_flow_status(prospect_key):
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        with connect() as conn:
            row = conn.execute(
                """select prospect_name,action,channel,stage,outcome,follow_up_at,note,created_at
                   from prospect_workflow_events where workspace_id=? and prospect_key=?
                   order by id desc limit 1""",
                (workspace_id, prospect_key),
            ).fetchone()
        return jsonify(item=dict(row) if row else None)

    @app.post("/api/prospect-flow/action")
    def prospect_flow_action():
        data = request.get_json(silent=True) or {}
        name = (data.get("prospect_name") or "").strip()[:180]
        action = (data.get("action") or "").strip().lower()
        channel = (data.get("channel") or "").strip().lower()[:30]
        outcome = (data.get("outcome") or "").strip()[:120]
        note = (data.get("note") or "").strip()[:1000]
        allowed = {"review", "contact", "follow_up", "complete"}
        if not name or action not in allowed:
            return jsonify(error="Prospect name and valid action are required"), 400
        stage_map = {
            "review": "Qualified",
            "contact": "Contacted",
            "follow_up": "Follow Up",
            "complete": "Won / Complete",
        }
        follow_up_at = ""
        if action == "follow_up":
            days = max(1, min(int(data.get("days") or 3), 30))
            follow_up_at = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        user_id = int(getattr(g, "user_id", 0) or 0)
        prospect_key = _key(name)
        with connect() as conn:
            conn.execute(
                """insert into prospect_workflow_events
                   (workspace_id,user_id,prospect_key,prospect_name,action,channel,stage,outcome,follow_up_at,note,created_at)
                   values(?,?,?,?,?,?,?,?,?,?,?)""",
                (workspace_id, user_id, prospect_key, name, action, channel,
                 stage_map[action], outcome, follow_up_at, note, _now()),
            )
        return jsonify(
            ok=True,
            prospect_key=prospect_key,
            stage=stage_map[action],
            follow_up_at=follow_up_at,
        ), 201

    @app.after_request
    def inject_prospect_flow(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-prospect-flow" in body or "</body>" not in body.lower():
            return response
        script = PROSPECT_FLOW_SCRIPT
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


PROSPECT_FLOW_SCRIPT = r'''<style id="brokerbeacon-prospect-flow-style">
#bb-prospect-drawer{position:fixed;top:0;right:0;width:min(430px,100vw);height:100vh;z-index:350;background:#0c1730;color:#f6f8ff;border-left:1px solid #ffffff22;box-shadow:-30px 0 70px #0008;transform:translateX(105%);transition:.22s;display:flex;flex-direction:column}#bb-prospect-drawer.open{transform:none}
#bb-prospect-backdrop{position:fixed;inset:0;z-index:340;background:#02050db8;display:none}#bb-prospect-backdrop.open{display:block}
.bbpf-head{padding:20px;background:linear-gradient(135deg,#10244a,#253d7b);display:flex;justify-content:space-between;gap:14px}.bbpf-head h2{margin:4px 0 5px;font-size:21px}.bbpf-kicker{font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:#76e6ff;font-weight:900}.bbpf-close{border:1px solid #ffffff33;background:#ffffff12;color:white;border-radius:9px;padding:8px 10px;cursor:pointer;height:38px}
.bbpf-body{padding:16px;overflow:auto;display:grid;gap:12px}.bbpf-card{padding:14px;border:1px solid #ffffff1d;border-radius:14px;background:#ffffff08}.bbpf-card h3{margin:0 0 7px;font-size:13px}.bbpf-reason{color:#bac6de;line-height:1.5;font-size:12px}.bbpf-stage{display:inline-flex;padding:5px 8px;border-radius:999px;background:#43dfa718;color:#88efc7;font-size:10px;font-weight:800}.bbpf-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.bbpf-actions button{border:1px solid #ffffff20;border-radius:11px;padding:11px;background:#ffffff0b;color:white;cursor:pointer;text-align:left}.bbpf-actions button:hover{background:#ffffff18}.bbpf-actions button.primary{background:linear-gradient(135deg,#7c5cff,#438df2);border:0}.bbpf-actions button strong,.bbpf-actions button small{display:block}.bbpf-actions button small{color:#b9c4da;margin-top:4px;font-size:10px}.bbpf-note{width:100%;min-height:70px}.bbpf-footer{padding:12px 16px;border-top:1px solid #ffffff17;color:#7f8da9;font-size:9px;text-align:center}
#bb-contact-prep-panel{margin:0 0 18px;padding:16px;border:1px solid #ffffff20;border-radius:16px;background:linear-gradient(135deg,#142648,#0d1932);box-shadow:0 16px 40px #0003;color:#f6f8ff}#bb-contact-prep-panel .bbcp-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}#bb-contact-prep-panel h2{margin:0 0 4px;font-size:19px}#bb-contact-prep-panel .bbcp-meta{font-size:11px;color:#9eabc6}#bb-contact-prep-panel .bbcp-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}#bb-contact-prep-panel .bbcp-card{border:1px solid #ffffff1d;border-radius:13px;background:#ffffff08;padding:13px;min-width:0}#bb-contact-prep-panel .bbcp-card h3{margin:0 0 8px;font-size:13px}#bb-contact-prep-panel .bbcp-draft{white-space:pre-wrap;line-height:1.45;font-size:12px;color:#d5def0;overflow-wrap:anywhere;min-height:150px}#bb-contact-prep-panel .bbcp-subject{font-size:11px;color:#9fc8ff;margin:0 0 8px;overflow-wrap:anywhere}#bb-contact-prep-panel .bbcp-copy{margin-top:10px;width:100%;border:1px solid #ffffff20;border-radius:9px;padding:8px;background:#ffffff0b;color:white;cursor:pointer}#bb-contact-prep-panel .bbcp-copy:hover{background:#ffffff18}#bb-contact-prep-panel .bbcp-close{border:1px solid #ffffff25;background:#ffffff0b;color:white;border-radius:9px;padding:7px 10px;cursor:pointer}
tr[data-bbpf],.card[data-bbpf],.priority-card[data-bbpf],.production-company[data-bbpf],.person-card[data-bbpf]{cursor:pointer}tr[data-bbpf]:hover,.card[data-bbpf]:hover,.priority-card[data-bbpf]:hover,.production-company[data-bbpf]:hover{outline:2px solid #7c5cff55;outline-offset:-2px}.bbpf-chip{display:inline-flex;margin-left:7px;padding:3px 6px;border-radius:999px;background:#7c5cff18;color:#8cecff;font-size:9px;vertical-align:middle}@media(max-width:900px){#bb-contact-prep-panel .bbcp-grid{grid-template-columns:1fr}}@media(max-width:520px){.bbpf-actions{grid-template-columns:1fr}}
</style><div id="bb-prospect-backdrop"></div><aside id="bb-prospect-drawer" aria-label="Prospect next action"><div class="bbpf-head"><div><div class="bbpf-kicker">One-click prospect workflow</div><h2 id="bbpf-name">Prospect</h2><div id="bbpf-meta" class="bbpf-reason"></div></div><button class="bbpf-close" aria-label="Close">✕</button></div><div class="bbpf-body"><div class="bbpf-card"><h3>Why this prospect matters</h3><div id="bbpf-reason" class="bbpf-reason">Review the available signal, contact information, and score before reaching out.</div></div><div class="bbpf-card"><h3>Recommended next action</h3><div id="bbpf-recommend" class="bbpf-reason"></div><div style="margin-top:9px"><span id="bbpf-stage" class="bbpf-stage">New</span></div></div><div class="bbpf-actions"><button id="bbpf-review"><strong>Mark reviewed</strong><small>Qualify and log the review.</small></button><button id="bbpf-contact" class="primary"><strong>Open contact prep</strong><small>Draft email, call, and text outreach.</small></button><button id="bbpf-follow"><strong>Follow up in 3 days</strong><small>Create the next step automatically.</small></button><button id="bbpf-complete"><strong>Complete</strong><small>Mark the workflow finished.</small></button></div><div class="bbpf-card"><h3>Optional note</h3><textarea id="bbpf-note" class="bbpf-note" placeholder="Add context once; it will be saved with the action."></textarea></div></div><div class="bbpf-footer">Built with purpose. Quietly dedicated to Aiden.</div></aside><script id="brokerbeacon-prospect-flow">(function(){
const drawer=document.getElementById('bb-prospect-drawer'),backdrop=document.getElementById('bb-prospect-backdrop');let current=null;
const text=e=>(e&&e.textContent||'').replace(/\s+/g,' ').trim();const hash=async s=>{const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s.trim().toLowerCase()));return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,24)};
const clean=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
function candidateName(el){const marked=el.querySelector('[data-company],[data-prospect-name]');if(marked)return text(marked);const cells=[...el.querySelectorAll('td,h3,h4,strong,b')].map(text).filter(x=>x.length>2&&x.length<180);return cells[0]||text(el).slice(0,180)}
function enrich(){document.querySelectorAll('tbody tr,.priority-card,.production-company,.card').forEach(el=>{if(el.closest('#bb-prospect-drawer')||el.closest('#bb-contact-prep-panel')||el.dataset.bbpf)return;const name=candidateName(el);if(!name||/no results|empty|dashboard|metric/i.test(name))return;el.dataset.bbpf='1';el.title=el.title||'Open the one-click prospect workflow.';el.addEventListener('click',ev=>{if(ev.target.closest('a,button,input,select,textarea'))return;open(el,name)})})}
function details(el,name){const raw=text(el);const email=(raw.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)||[])[0]||'';const phone=(raw.match(/(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}/)||[])[0]||'';const score=(raw.match(/(?:score|priority)\s*[: ]\s*(\d{1,3})/i)||[])[1]||'';return{name,email,phone,score,raw,el}}
async function open(el,name){current=details(el,name);document.getElementById('bbpf-name').textContent=current.name;document.getElementById('bbpf-meta').textContent=[current.email,current.phone,current.score&&('Score '+current.score)].filter(Boolean).join(' · ')||'Prospect details';document.getElementById('bbpf-reason').textContent=current.score?'A visible priority score of '+current.score+' makes this prospect worth reviewing now.':'This prospect is in your active workspace and ready for a clear next decision.';document.getElementById('bbpf-recommend').textContent='Open contact prep to review ready-to-use email, call, and text drafts before outreach.';document.getElementById('bbpf-contact').querySelector('strong').textContent='Open contact prep';document.getElementById('bbpf-note').value='';document.getElementById('bbpf-stage').textContent='New';drawer.classList.add('open');backdrop.classList.add('open');try{const k=await hash(current.name),r=await fetch('/api/prospect-flow/status/'+k),j=await r.json();if(j.item)document.getElementById('bbpf-stage').textContent=j.item.stage||'New'}catch(e){}}
function close(){drawer.classList.remove('open');backdrop.classList.remove('open')}backdrop.onclick=close;drawer.querySelector('.bbpf-close').onclick=close;
async function log(action,channel='',outcome='',days=3){if(!current)return;const note=document.getElementById('bbpf-note').value;const r=await fetch('/api/prospect-flow/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prospect_name:current.name,action,channel,outcome,note,days})});const j=await r.json();if(!r.ok)throw new Error(j.error||'Unable to save action');document.getElementById('bbpf-stage').textContent=j.stage;const toast=document.querySelector('.toast');if(toast){toast.textContent=j.stage+(j.follow_up_at?' · follow-up scheduled':'');toast.style.display='block';setTimeout(()=>toast.style.display='none',2200)}return j}
function contactDrafts(p){const name=(p.name||'your company').trim();return{subject:'Quick support for '+name,email:'Hi there,\n\nI wanted to introduce myself and offer to be a resource for '+name+'. If you have a wholesale mortgage scenario that needs a second look, onboarding questions, or a file you are trying to place, I am happy to help work through the next step.\n\nIf useful, send over the basics of what you are working on and I will help you think through the options.\n\nBest,\n[Your Name]',call:'Hi, this is [Your Name] with [Lender]. I wanted to introduce myself and offer to be a resource for '+name+'. If you have a wholesale mortgage scenario you are trying to place, or any onboarding questions, I am happy to help. What are you working on right now?',sms:'Hi, this is [Your Name] with [Lender]. Wanted to introduce myself and offer help with any wholesale mortgage scenarios or onboarding questions for '+name+'. Happy to be a resource. What are you working on right now?'}}
function copyDraft(value,button){navigator.clipboard.writeText(value).then(()=>{const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1400)}).catch(()=>{})}
function renderContactPrep(p){const main=document.querySelector('main');if(!main||!p||!p.name)return false;let panel=document.getElementById('bb-contact-prep-panel');if(panel)panel.remove();const d=contactDrafts(p);panel=document.createElement('section');panel.id='bb-contact-prep-panel';panel.innerHTML='<div class="bbcp-head"><div><h2>Contact prep · '+p.name.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))+'</h2><div class="bbcp-meta">'+([p.email,p.phone].filter(Boolean).join(' · ')||'Use the best verified contact channel')+'</div></div><button class="bbcp-close">Close</button></div><div class="bbcp-grid"><div class="bbcp-card"><h3>Email draft</h3><div class="bbcp-subject">Subject: '+d.subject+'</div><div class="bbcp-draft"></div><button class="bbcp-copy" data-copy="email">Copy email</button></div><div class="bbcp-card"><h3>Call opener</h3><div class="bbcp-draft"></div><button class="bbcp-copy" data-copy="call">Copy call script</button></div><div class="bbcp-card"><h3>Text draft</h3><div class="bbcp-draft"></div><button class="bbcp-copy" data-copy="sms">Copy text</button></div></div>';const drafts=panel.querySelectorAll('.bbcp-draft');drafts[0].textContent=d.email;drafts[1].textContent=d.call;drafts[2].textContent=d.sms;panel.querySelector('.bbcp-close').onclick=()=>panel.remove();panel.querySelectorAll('.bbcp-copy').forEach(b=>b.onclick=()=>copyDraft(b.dataset.copy==='email'?('Subject: '+d.subject+'\n\n'+d.email):d[b.dataset.copy],b));main.prepend(panel);panel.scrollIntoView({behavior:'smooth',block:'start'});sessionStorage.removeItem('bb-contact-prep');return true}
function findContactScreenControl(){const controls=[...document.querySelectorAll('aside nav button,aside button,nav button,a')].filter(el=>!el.closest('#bb-prospect-drawer')&&!el.closest('#bb-contact-prep-panel'));return controls.find(el=>/call prep/.test(clean(el.textContent+' '+(el.title||''))))||controls.find(el=>/contact|outreach/.test(clean(el.textContent+' '+(el.title||''))))}
function openContactPrep(){if(!current)return;const payload={name:current.name,email:current.email,phone:current.phone,score:current.score};sessionStorage.setItem('bb-contact-prep',JSON.stringify(payload));close();const target=findContactScreenControl();if(target){target.click();setTimeout(()=>renderContactPrep(payload),250);setTimeout(()=>renderContactPrep(payload),800)}else{renderContactPrep(payload)}}
function restoreContactPrep(){try{const raw=sessionStorage.getItem('bb-contact-prep');if(!raw)return;const payload=JSON.parse(raw);setTimeout(()=>renderContactPrep(payload),350)}catch(e){sessionStorage.removeItem('bb-contact-prep')}}
document.getElementById('bbpf-review').onclick=()=>log('review','','Reviewed');document.getElementById('bbpf-follow').onclick=()=>log('follow_up','','Follow-up scheduled',3);document.getElementById('bbpf-complete').onclick=()=>log('complete','','Workflow complete');document.getElementById('bbpf-contact').onclick=openContactPrep;
new MutationObserver(enrich).observe(document.body,{childList:true,subtree:true});enrich();restoreContactPrep();
})();</script>'''
