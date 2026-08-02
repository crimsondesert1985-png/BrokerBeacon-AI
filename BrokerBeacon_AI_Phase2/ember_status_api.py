"""Owner-visible health endpoint and guided source setup center for Ember."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, render_template_string, session

from source_resilience import source_health


def build_guidance(*, worker_healthy: bool, stale: bool, sources: dict) -> dict:
    """Turn system state into one clear next step for the owner."""
    providers = list(sources.get("configured_providers") or [])
    paused = list(sources.get("paused_states") or [])
    if not providers:
        return {
            "stage": "connect",
            "label": "Connect a discovery source",
            "message": "Ember is ready to work, but it needs one search provider before it can find new prospects.",
            "action": "Add one supported provider key in Render, then refresh this page.",
            "tone": "attention",
        }
    if not worker_healthy:
        reason = "The worker heartbeat is stale." if stale else "The worker is reporting a failure."
        return {
            "stage": "restore",
            "label": "Restore Ember",
            "message": reason,
            "action": "Review the latest run and worker logs before starting another discovery cycle.",
            "tone": "attention",
        }
    if paused:
        return {
            "stage": "monitor",
            "label": "Discovery is protecting itself",
            "message": f"Ember is healthy. {len(paused)} state{' is' if len(paused) == 1 else 's are'} temporarily paused after repeated empty searches.",
            "action": "Let Ember continue with available states; paused states will return automatically.",
            "tone": "working",
        }
    return {
        "stage": "discover",
        "label": "Ready to find prospects",
        "message": f"Ember is healthy and connected through {', '.join(providers)}.",
        "action": "Run discovery, review the strongest matches, and promote only verified prospects.",
        "tone": "ready",
    }


SETUP_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BrokerBeacon Source Setup</title><style>
:root{--bg:#07101f;--panel:#101d35;--line:#ffffff1c;--text:#f7fbff;--muted:#9fb0cb;--cyan:#25d5ff;--violet:#8568ff;--green:#48e0a4;--yellow:#ffd166}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#8568ff44,transparent 30%),radial-gradient(circle at 100% 0,#25d5ff22,transparent 28%),var(--bg);color:var(--text);font:15px Inter,Segoe UI,Arial,sans-serif}.wrap{max-width:1080px;margin:auto;padding:32px 18px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center}.eyebrow{color:var(--cyan);font-size:11px;font-weight:900;letter-spacing:.14em;text-transform:uppercase}h1{font-size:clamp(30px,6vw,54px);margin:7px 0 8px}.muted{color:var(--muted);line-height:1.6}.btn{border:1px solid var(--line);background:#ffffff0c;color:white;padding:11px 14px;border-radius:11px;cursor:pointer;text-decoration:none}.btn:hover{background:#ffffff18}.primary{border:0;background:linear-gradient(135deg,var(--violet),#4fa8ff)}.hero,.card{background:#101d35dd;border:1px solid var(--line);border-radius:19px;box-shadow:0 22px 60px #0006}.hero{padding:24px;margin:22px 0}.status{display:grid;grid-template-columns:74px 1fr auto;gap:18px;align-items:center}.orb{width:68px;height:68px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,var(--violet),var(--cyan));font-size:28px;box-shadow:0 0 35px #25d5ff44}.status h2{margin:0 0 6px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card{padding:19px}.card h3{margin:0 0 8px}.providers{display:grid;gap:9px;margin-top:14px}.provider{display:flex;justify-content:space-between;gap:10px;padding:11px;border:1px solid var(--line);border-radius:11px;background:#ffffff07}.pill{font-size:11px;padding:5px 8px;border-radius:999px;background:#ffffff10;color:var(--muted)}.on{background:#48e0a417;color:#8bf2ca}.steps{counter-reset:s}.step{display:grid;grid-template-columns:34px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}.step:last-child{border:0}.step:before{counter-increment:s;content:counter(s);width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#8568ff2b;color:#c8bcff;font-weight:900}.states{max-height:310px;overflow:auto}.state{display:grid;grid-template-columns:55px 1fr auto;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}code{color:#a9edff}.empty{padding:24px;text-align:center;color:var(--muted)}.footer{text-align:center;color:var(--muted);font-size:11px;margin-top:22px}@media(max-width:760px){.grid{grid-template-columns:1fr}.top,.status{grid-template-columns:1fr;display:grid}.status .btn{width:100%;text-align:center}}
</style></head><body><main class="wrap"><div class="top"><div><div class="eyebrow">Platform Owner · Guided Setup</div><h1>Make Ember useful.</h1><div class="muted">One screen that shows what is working, what is blocked, and exactly what to do next.</div></div><a class="btn" href="/">Back to BrokerBeacon</a></div>
<section class="hero"><div class="status"><div class="orb" id="orb">…</div><div><div class="eyebrow" id="stage">Checking</div><h2 id="headline">Reading Ember health</h2><div class="muted" id="message">This takes a moment.</div></div><button class="btn primary" id="refresh" onclick="loadHealth()">Refresh status</button></div></section>
<div class="grid"><section class="card"><h3>Discovery connections</h3><div class="muted">Connect any one provider. BrokerBeacon never displays or returns the secret value.</div><div class="providers" id="providers"></div><div style="margin-top:14px" class="muted"><b>Next action:</b> <span id="action">Checking…</span></div></section>
<section class="card"><h3>Simple setup flow</h3><div class="steps"><div class="step"><div><b>Choose one provider</b><div class="muted">Brave, Tavily, Firecrawl, SerpAPI, or Google CSE.</div></div></div><div class="step"><div><b>Add its environment variable in Render</b><div class="muted">Use the exact variable names shown here. Secret values stay hidden.</div></div></div><div class="step"><div><b>Refresh and verify</b><div class="muted">This screen changes from blocked to ready when Ember can search.</div></div></div><div class="step"><div><b>Review before promotion</b><div class="muted">Discovery does not enable outreach or automatically promote prospects to CRM.</div></div></div></div></section>
<section class="card"><h3>State protection</h3><div class="muted">States with repeated empty searches pause automatically instead of wasting requests.</div><div class="states" id="states"></div></section>
<section class="card"><h3>Safety controls</h3><div class="provider"><span>Automatic outreach</span><span class="pill">Off</span></div><div class="provider"><span>Automatic CRM promotion</span><span class="pill">Off</span></div><div class="provider"><span>Human verification</span><span class="pill on">Required</span></div><div class="provider"><span>Secret values exposed</span><span class="pill">Never</span></div></section></div><div class="footer">BrokerBeacon standard: Intuitive · Flashy · Informative · Simple</div></main>
<script>
const providerVars={brave:['BRAVE_SEARCH_API_KEY'],tavily:['TAVILY_API_KEY'],firecrawl:['FIRECRAWL_API_KEY'],serpapi:['SERPAPI_API_KEY'],google:['GOOGLE_CSE_API_KEY','GOOGLE_CSE_ID']};
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function loadHealth(){const b=document.getElementById('refresh');b.disabled=true;b.textContent='Checking…';try{const r=await fetch('/api/platform/ember-health',{credentials:'same-origin'});if(!r.ok)throw new Error(r.status===403?'Platform owner access is required.':'Health check failed.');const d=await r.json(),g=d.guidance||{};document.getElementById('stage').textContent=(g.stage||'status').toUpperCase();document.getElementById('headline').textContent=g.label||'Ember status';document.getElementById('message').textContent=g.message||'';document.getElementById('action').textContent=g.action||'';document.getElementById('orb').textContent=d.discovery_ready?'✓':(d.healthy?'!':'×');const configured=new Set((d.sources&&d.sources.configured_providers)||[]);document.getElementById('providers').innerHTML=Object.entries(providerVars).map(([name,vars])=>`<div class="provider"><div><b>${esc(name[0].toUpperCase()+name.slice(1))}</b><div class="muted">${vars.map(v=>`<code>${esc(v)}</code>`).join(' + ')}</div></div><span class="pill ${configured.has(name)?'on':''}">${configured.has(name)?'Connected':'Not connected'}</span></div>`).join('');const states=(d.sources&&d.sources.states)||[];document.getElementById('states').innerHTML=states.length?states.map(s=>`<div class="state"><b>${esc(s.state)}</b><span class="muted">${s.paused_until?'Paused after '+esc(s.zero_yield_streak)+' empty runs':'Available · last yield '+esc(s.last_companies)+' companies / '+esc(s.last_contacts)+' contacts'}</span><span class="pill ${s.paused_until?'':'on'}">${s.paused_until?'Paused':'Ready'}</span></div>`).join(''):'<div class="empty">No state history yet. Ember will populate this after discovery runs.</div>';}catch(e){document.getElementById('headline').textContent='Status unavailable';document.getElementById('message').textContent=e.message;document.getElementById('action').textContent='Return to BrokerBeacon and confirm you are signed in as platform owner.';}finally{b.disabled=false;b.textContent='Refresh status'}}loadHealth();
</script></body></html>'''


def install_ember_status_api(app, db_path):
    bp = Blueprint("ember_status", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout=30000")
        return conn

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner")):
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    def snapshot():
        with connect() as conn:
            conn.execute("""create table if not exists ember_worker_heartbeat(
                worker_key text primary key,status text not null,message text not null default '',last_seen_at text not null,
                last_cycle_started_at text not null default '',last_cycle_finished_at text not null default '',
                last_run_id integer,last_state text not null default '',last_error text not null default '')""")
            heartbeat = conn.execute("select * from ember_worker_heartbeat where worker_key in ('always-on-web','always-on') order by last_seen_at desc limit 1").fetchone()
            latest = conn.execute("select id,state,status,created_at,finished_at,detail_json from ember_automation_runs order by id desc limit 1").fetchone() if conn.execute("select count(*) from sqlite_master where type='table' and name='ember_automation_runs'").fetchone()[0] else None
            sources = source_health(conn)
        heartbeat_dict = dict(heartbeat) if heartbeat else None
        latest_dict = dict(latest) if latest else None
        stale = True
        if heartbeat_dict:
            try:
                stale = (datetime.now() - datetime.fromisoformat(heartbeat_dict["last_seen_at"])).total_seconds() > 420
            except (ValueError, TypeError):
                stale = True
        worker_healthy = bool(heartbeat_dict and not stale and heartbeat_dict.get("status") != "Failed")
        guidance = build_guidance(worker_healthy=worker_healthy, stale=stale, sources=sources)
        return dict(worker=heartbeat_dict,latest_run=latest_dict,healthy=worker_healthy,stale=stale,sources=sources,
                    discovery_ready=bool(worker_healthy and sources.get("search_ready")),guidance=guidance,
                    outreach_enabled=False,crm_promotion_enabled=False)

    @bp.get("/api/platform/ember-health")
    @owner_required
    def health():
        return jsonify(**snapshot())

    @bp.get("/platform/source-setup")
    @owner_required
    def source_setup():
        return render_template_string(SETUP_HTML)

    app.register_blueprint(bp)
    return bp
