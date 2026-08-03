"""Production WSGI entrypoint for BrokerBeacon."""
from flask import g, session

from app import app, DB
from ai_ops_api import install_ai_ops
from control_tower_ux import install_control_tower_ux
from discovery_ops_api import install_discovery_ops
from drip_campaigns import install_drip_campaigns
from ember_automation_api import install_ember_automation
from ember_queue_api import install_ember_queue_api
from ember_status_api import install_ember_status_api
from ember_worker import install_ember_worker
from founder_briefing import install_founder_briefing
from national_autopilot_api import install_national_autopilot_api
from national_data_center import install_national_data_center
from national_warehouse_api import install_national_warehouse
from prospect_flow import install_prospect_flow
from role_management import install_role_management
from simplified_flow import install_simplified_flow
from sprint38_api import install_sprint38_api
from sprint39_api import install_sprint39_api
from sprint39_ux import install_sprint39_ux
from sprint41_ux import install_sprint41_ux
from sprint41_drilldown_ux import install_sprint41_drilldown_ux
from sprint42_national_ux import install_sprint42_national_ux
from state_connector_api import install_state_connectors
from workspace_consolidation import install_workspace_consolidation

install_national_warehouse(app, DB)
install_state_connectors(app, DB)
install_discovery_ops(app, DB)
install_ai_ops(app, DB)
install_ember_automation(app, DB)
install_ember_status_api(app, DB)
install_ember_queue_api(app, DB)
install_sprint38_api(app, DB)
install_sprint39_api(app, DB)
install_national_autopilot_api(app, DB)
install_role_management(app, DB)
install_founder_briefing(app, DB)
install_national_data_center(app)
install_control_tower_ux(app)
install_sprint39_ux(app)
install_sprint41_ux(app)
install_sprint41_drilldown_ux(app)
install_sprint42_national_ux(app)
install_simplified_flow(app)
install_prospect_flow(app, DB)
install_drip_campaigns(app, DB)
install_workspace_consolidation(app)
install_ember_worker(app, DB)


@app.before_request
def bridge_platform_owner_context():
    if bool(getattr(g, "is_platform_owner", False)):
        session["is_platform_owner"] = True
    else:
        session.pop("is_platform_owner", None)


@app.after_request
def add_role_aware_navigation(response):
    is_platform_owner = bool(getattr(g, "is_platform_owner", False))
    can_manage_team = is_platform_owner or getattr(g, "membership_role", None) in {"Owner", "Manager"}
    if not is_platform_owner and not can_manage_team:
        return response
    if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
        return response
    try:
        body = response.get_data(as_text=True)
    except (RuntimeError, UnicodeDecodeError):
        return response
    if "brokerbeacon-role-aware-navigation" in body or "</body>" not in body.lower():
        return response
    enhancement = f'''<script id="brokerbeacon-role-aware-navigation">(function(){{function add(){{const nav=document.querySelector('aside nav')||document.querySelector('aside');if(!nav)return;const make=(id,label,title,path,badge)=>{{if(document.getElementById(id))return;const b=document.createElement('button');b.id=id;b.type='button';b.innerHTML=label+(badge?'<span style="float:right;font-size:10px;opacity:.75">'+badge+'</span>':'');b.title=title;b.onclick=()=>window.location.href=path;nav.appendChild(b)}};{'''make('ember-control-tower-button','🔥 Ember Control Tower','Open national discovery, live activity, review queue, and prospect controls.','/platform/control-tower','ALWAYS ON');''' if is_platform_owner else ''}{'''make('team-access-button','👥 Team & Access','Invite users and control what each person can see and change.','/workspace/team','SIMPLE');''' if can_manage_team else ''}{'''if(!document.getElementById('platform-owner-badge')){const badge=document.createElement('div');badge.id='platform-owner-badge';badge.textContent='Platform Owner';badge.style.cssText='margin:10px 12px;padding:6px 8px;border-radius:999px;background:#43dfa715;color:#137a55;font-size:10px;font-weight:800;text-align:center';nav.appendChild(badge)}''' if is_platform_owner else ''}}}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add()}})();</script>'''
    pos = body.lower().rfind("</body>")
    body = body[:pos] + enhancement + body[pos:]
    response.set_data(body)
    response.headers["Content-Length"] = str(len(response.get_data()))
    return response


__all__ = ["app"]
