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
                '.card{transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}.card:hover{transform:translateY(-3px);border-color:#58a6ff66;box-shadow:0 14px 34px #0004}'
                '.card strong{background:linear-gradient(90deg,#fff,#84baff);-webkit-background-clip:text;color:transparent}'
                '</style>',
            )
            old = "async function runCycle(){try{await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});await loadAll()}catch(e){fail(e)}}"
            new = """let huntRunning=false;async function runCycle(){
if(huntRunning)return;huntRunning=true;let b=document.getElementById('huntButton'),s=document.getElementById('huntStatus'),err=document.getElementById('error');
if(err)err.style.display='none';b.disabled=true;b.innerHTML='<span>🔥</span> Ember is hunting…';s.className='hunt-status running';s.textContent='Checking a safe North Carolina batch of public mortgage-company websites, extracting contacts, and scoring opportunities.';
try{let d=await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});let h=d.hunt||d;s.className='hunt-status success';s.textContent=`Complete. ${h.companies_seeded||0} companies checked, ${h.enrichment?.contacts_found||0} new contacts found, ${h.pending_review||0} waiting for review. No outreach was sent.`;await loadAll()}
catch(e){s.className='hunt-status failed';s.textContent='The hunt stopped safely. No outreach was sent. '+(e.message||e);fail(e)}
finally{huntRunning=false;b.disabled=false;b.innerHTML='<span>🔥</span> Launch Ember Hunt'}}"""
            html = html.replace(old, new)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Control Tower UX enhancement failed")
        return response

    return app
