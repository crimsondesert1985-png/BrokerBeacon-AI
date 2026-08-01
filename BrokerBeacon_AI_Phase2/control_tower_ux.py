"""Small response-layer UX upgrade for the Sprint 37 Control Tower."""
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
            html = html.replace(
                '<div id="focus" class="muted">Loading…</div><button class="primary" style="margin-top:14px" onclick="runCycle()">Run one guarded growth cycle</button>',
                '<div id="focus" class="muted">Review the strongest pending prospects, then launch another safe North Carolina batch.</div>'
                '<div id="huntStatus" class="hunt-status">Ready. Outreach is locked until you approve a prospect.</div>'
                '<button id="huntButton" class="primary hunt-button" onclick="runCycle()">Launch Ember Hunt</button>'
            )
            html = html.replace(
                '</style>',
                '.hunt-status{margin:14px 0;padding:12px;border-radius:10px;background:#081b38;border:1px solid var(--line);color:var(--muted);line-height:1.45}'
                '.hunt-status.running{color:#bfe0ff;border-color:#58a6ff66}.hunt-status.success{color:#b7f5d8;border-color:#4bd19b66}.hunt-status.failed{color:#ffd0d8;border-color:#ff7d9366}'
                '.hunt-button{width:100%;margin-top:2px;font-weight:800}.hunt-button:disabled{opacity:.65;cursor:wait}'
                '.card{transition:transform .15s ease,border-color .15s ease}.card:hover{transform:translateY(-2px);border-color:#58a6ff55}'
                '</style>'
            )
            old = "async function runCycle(){try{await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});await loadAll()}catch(e){fail(e)}}"
            new = """let huntRunning=false;async function runCycle(){
if(huntRunning)return;huntRunning=true;let b=document.getElementById('huntButton'),s=document.getElementById('huntStatus'),err=document.getElementById('error');
if(err)err.style.display='none';b.disabled=true;b.textContent='Ember is hunting…';s.className='hunt-status running';s.textContent='Checking a small North Carolina batch of public mortgage-company websites. This normally takes under 30 seconds.';
try{let d=await api('/api/platform/ai-ops/run-cycle',{method:'POST',body:'{}'});let h=d.hunt||d;s.className='hunt-status success';s.textContent=`Complete. ${h.companies_seeded||0} companies checked, ${h.enrichment?.contacts_found||0} new contacts found, ${h.pending_review||0} waiting for review. No outreach was sent.`;await loadAll()}
catch(e){s.className='hunt-status failed';s.textContent='The hunt stopped safely. No outreach was sent. '+(e.message||e);fail(e)}
finally{huntRunning=false;b.disabled=false;b.textContent='Launch Ember Hunt'}}"""
            html = html.replace(old, new)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Control Tower UX enhancement failed")
        return response

    return app
