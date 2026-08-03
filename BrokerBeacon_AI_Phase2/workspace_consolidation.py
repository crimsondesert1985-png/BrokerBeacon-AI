"""Sprint 54: consolidate BrokerBeacon into five core workspaces."""
from flask import request

PUBLIC_PREFIXES = ("/login", "/register", "/invite", "/password", "/static")

WORKSPACES = (
    {
        "id": "home",
        "label": "Home",
        "icon": "⌂",
        "description": "Priorities, alerts, metrics, and the next best action.",
        "keywords": ("home", "dashboard", "brief", "today", "priority", "overview", "boss"),
    },
    {
        "id": "prospects",
        "label": "Prospects",
        "icon": "◎",
        "description": "Find, review, score, route, and manage prospects.",
        "keywords": ("prospect", "watchtower", "scout", "search", "pipeline", "company", "route", "broker", "discovery"),
    },
    {
        "id": "outreach",
        "label": "Outreach",
        "icon": "✦",
        "description": "Call, email, text, follow up, and run campaigns.",
        "keywords": ("call", "email", "text", "voice", "template", "campaign", "follow", "outreach", "activity"),
    },
    {
        "id": "intelligence",
        "label": "Intelligence",
        "icon": "◇",
        "description": "Production data, guidelines, insights, and reports.",
        "keywords": ("intelligence", "production", "guideline", "report", "market", "insight", "executive", "analytics"),
    },
    {
        "id": "settings",
        "label": "Settings",
        "icon": "⚙",
        "description": "Integrations, billing, team access, roles, and data controls.",
        "keywords": ("setting", "integration", "billing", "team", "access", "role", "workspace", "data", "system", "admin", "owner"),
    },
)


def _workspace_script():
    config = repr(WORKSPACES)
    return f'''<style id="brokerbeacon-workspace-consolidation-style">
.bb-core-nav{{display:grid;gap:7px;margin:8px 0 12px}}
.bb-core-btn{{display:grid!important;grid-template-columns:30px 1fr auto;align-items:center;gap:9px;width:100%;padding:11px 12px!important;border:1px solid transparent!important;border-radius:12px!important;background:transparent!important;color:inherit!important;text-align:left!important;cursor:pointer}}
.bb-core-btn:hover,.bb-core-btn.active{{background:rgba(23,78,166,.12)!important;border-color:rgba(23,78,166,.2)!important}}
.bb-core-icon{{display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:rgba(23,78,166,.12);font-size:15px}}
.bb-core-copy b{{display:block;font-size:12px}}.bb-core-copy small{{display:block;margin-top:2px;font-size:9px;line-height:1.25;opacity:.68}}
.bb-core-count{{font-size:9px;opacity:.55}}
.bb-legacy-tools{{margin-top:8px;border-top:1px solid rgba(127,145,173,.2);padding-top:8px}}
.bb-legacy-tools summary{{cursor:pointer;padding:9px 10px;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;opacity:.72}}
.bb-legacy-tools .bb-legacy-list{{display:grid;gap:3px;padding:2px 4px 8px}}
.bb-legacy-tools .bb-legacy-list>button{{font-size:11px!important;padding:8px 9px!important;margin:0!important}}
.bb-workspace-strip{{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 14px;padding:9px;border:1px solid rgba(127,145,173,.22);border-radius:13px;background:rgba(255,255,255,.64);backdrop-filter:blur(8px)}}
.bb-workspace-strip button{{border:0;border-radius:999px;padding:8px 11px;background:transparent;color:#27405f;font-weight:750;cursor:pointer}}
.bb-workspace-strip button.active,.bb-workspace-strip button:hover{{background:#174ea6;color:#fff}}
body.dark-mode .bb-workspace-strip{{background:rgba(15,29,52,.78);border-color:#2b405f}}body.dark-mode .bb-workspace-strip button{{color:#dce9f8}}
@media(max-width:900px){{.bb-workspace-strip{{position:sticky;top:0;z-index:30;overflow-x:auto;flex-wrap:nowrap}}.bb-workspace-strip button{{white-space:nowrap}}}}
</style>
<script id="brokerbeacon-workspace-consolidation">(function(){{
const workspaces={config};
const clean=s=>(s||'').replace(/\\s+/g,' ').trim().toLowerCase();
function buttons(){{return [...document.querySelectorAll('aside nav button, aside button')].filter(b=>!b.closest('.bb-core-nav')&&!b.closest('.bb-legacy-tools'));}}
function classify(button){{const hay=clean(button.textContent+' '+button.title+' '+button.id);let best=workspaces[0],score=-1;for(const w of workspaces){{let s=0;for(const k of w.keywords)if(hay.includes(k))s++;if(s>score){{best=w;score=s}}}}return best;}}
function activateOriginal(workspace){{const candidates=buttons().filter(b=>classify(b).id===workspace.id);const preferred=candidates.find(b=>!b.disabled&&b.offsetParent!==null)||candidates.find(b=>!b.disabled);if(preferred){{preferred.click();return true}}if(workspace.id==='settings'){{const team=document.getElementById('team-access-button');if(team){{team.click();return true}}window.location.href='/workspace/team';return true}}return false;}}
function setActive(id){{document.querySelectorAll('.bb-core-btn,.bb-workspace-strip button').forEach(b=>b.classList.toggle('active',b.dataset.workspace===id));localStorage.setItem('bb-workspace',id);}}
function openWorkspace(id){{const w=workspaces.find(x=>x.id===id)||workspaces[0];setActive(w.id);activateOriginal(w);}}
function build(){{const nav=document.querySelector('aside nav')||document.querySelector('aside');if(!nav||document.querySelector('.bb-core-nav'))return;const originals=buttons();if(originals.length<2)return;const counts={{}};originals.forEach(b=>{{const id=classify(b).id;counts[id]=(counts[id]||0)+1;b.dataset.bbWorkspace=id;}});
const core=document.createElement('div');core.className='bb-core-nav';core.innerHTML=workspaces.map(w=>`<button type="button" class="bb-core-btn" data-workspace="${{w.id}}" title="${{w.description}}"><span class="bb-core-icon">${{w.icon}}</span><span class="bb-core-copy"><b>${{w.label}}</b><small>${{w.description}}</small></span><span class="bb-core-count">${{counts[w.id]||0}}</span></button>`).join('');
const details=document.createElement('details');details.className='bb-legacy-tools';details.innerHTML='<summary>More tools</summary><div class="bb-legacy-list"></div>';const legacy=details.querySelector('.bb-legacy-list');originals.forEach(b=>legacy.appendChild(b));nav.prepend(details);nav.prepend(core);
core.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>openWorkspace(b.dataset.workspace)));
const main=document.querySelector('main');if(main&&!document.querySelector('.bb-workspace-strip')){{const strip=document.createElement('div');strip.className='bb-workspace-strip';strip.setAttribute('aria-label','Core workspaces');strip.innerHTML=workspaces.map(w=>`<button type="button" data-workspace="${{w.id}}" title="${{w.description}}">${{w.icon}} ${{w.label}}</button>`).join('');strip.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>openWorkspace(b.dataset.workspace)));main.prepend(strip)}}
const saved=localStorage.getItem('bb-workspace')||'home';setActive(saved);
const observer=new MutationObserver(()=>{{buttons().forEach(b=>{{if(!b.dataset.bbWorkspace)b.dataset.bbWorkspace=classify(b).id}})}});observer.observe(nav,{{childList:true,subtree:true}});
}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',build);else build();
}})();</script>'''


def install_workspace_consolidation(app):
    """Inject five-workspace navigation while preserving every legacy action."""

    @app.after_request
    def add_workspace_consolidation(response):
        if request.path.startswith(PUBLIC_PREFIXES):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-workspace-consolidation" in body or "</body>" not in body.lower():
            return response
        pos = body.lower().rfind("</body>")
        body = body[:pos] + _workspace_script() + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response
