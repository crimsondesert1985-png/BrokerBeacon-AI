"""Calm, decision-first national Ember progress layer."""
from __future__ import annotations


def install_sprint42_national_ux(app):
    @app.after_request
    def enhance(response):
        if response.status_code != 200 or not response.is_sequence:
            return response
        try:
            from flask import request
            if request.path != "/platform/control-tower":
                return response
            html = response.get_data(as_text=True)
            if "s42-national-autopilot" in html or "</body>" not in html.lower():
                return response
            style = r'''<style id="s42-national-autopilot">
.s42-wrap{margin:0 0 14px;padding:16px;border:1px solid #58d6ff2c;border-radius:18px;background:linear-gradient(145deg,#091c38,#07162c);box-shadow:0 14px 38px #0005}.s42-head{display:flex;justify-content:space-between;gap:16px;align-items:center}.s42-head h2{margin:0;font-size:17px}.s42-sub{color:#8fa8c8;font-size:12px;margin-top:4px}.s42-progress{height:10px;border-radius:99px;background:#ffffff0b;overflow:hidden;margin:14px 0 10px}.s42-progress i{display:block;height:100%;width:0;background:linear-gradient(90deg,#58d6ff,#45e0a8);box-shadow:0 0 18px #45e0a866;transition:.5s}.s42-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.s42-stat{padding:11px;border-radius:13px;background:#ffffff07}.s42-stat span{display:block;color:#829aba;font-size:10px;text-transform:uppercase;letter-spacing:.06em}.s42-stat b{font-size:20px}.s42-next{margin-top:11px;padding:11px;border-radius:13px;background:#ffffff06;color:#cddcf1;font-size:12px}.s42-action{border:0;border-radius:11px;padding:9px 12px;background:#ffffff0c;color:#ddecff;font-weight:800;cursor:pointer}.s42-action:hover{background:#ffffff16}@media(max-width:760px){.s42-grid{grid-template-columns:1fr 1fr}.s42-head{align-items:flex-start}}
</style>'''
            shell = r'''<section class="s42-wrap" id="s42National"><div class="s42-head"><div><h2>National Prospect Autopilot</h2><div class="s42-sub" id="s42Brief">Ember is balancing discovery across all 50 states.</div></div><button class="s42-action" id="s42Refill">Keep Queue Full</button></div><div class="s42-progress"><i id="s42Bar"></i></div><div class="s42-grid"><div class="s42-stat"><span>State coverage</span><b id="s42Coverage">0%</b></div><div class="s42-stat"><span>States reached</span><b id="s42Reached">0 / 50</b></div><div class="s42-stat"><span>Active hunts</span><b id="s42Active">0</b></div><div class="s42-stat"><span>Needs refresh</span><b id="s42Stale">0</b></div></div><div class="s42-next" id="s42Next">Choosing the next states…</div></section>'''
            script = r'''<script id="s42-national-script">(function(){const $=id=>document.getElementById(id);async function load(){try{const d=await api('/api/platform/national-autopilot'),s=d.summary||{};$('s42Coverage').textContent=(s.coverage_percent||0)+'%';$('s42Reached').textContent=(s.covered_states||0)+' / '+(s.enabled_states||50);$('s42Active').textContent=s.active_state_jobs||0;$('s42Stale').textContent=s.stale_states||0;$('s42Bar').style.width=(s.coverage_percent||0)+'%';$('s42Next').textContent=(s.next_states||[]).length?'Next focus: '+s.next_states.join(' · '):'All enabled states are in rotation.';$('s42Brief').textContent=(s.remaining_states||0)>0?'Ember is expanding coverage without interrupting your review workflow.':'All states are covered; Ember is now refreshing stale markets.'}catch(e){console.error(e)}}document.addEventListener('DOMContentLoaded',()=>{const root=document.getElementById('s41Command')||document.querySelector('main')||document.body;root.insertAdjacentHTML(root.id==='s41Command'?'afterend':'afterbegin',`__SHELL__`);$('s42Refill').onclick=async()=>{await fetch('/api/platform/national-autopilot/refill',{method:'POST'});load()};load();setInterval(load,30000)});})();</script>'''.replace('__SHELL__',shell.replace('`','\\`'))
            html=html.replace('</head>',style+'</head>')
            pos=html.lower().rfind('</body>')
            html=html[:pos]+script+html[pos:]
            response.set_data(html)
            response.headers['Content-Length']=str(len(response.get_data()))
        except Exception:
            app.logger.exception('Sprint 42 national UX enhancement failed')
        return response
    return app
