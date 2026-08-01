"""Production WSGI entrypoint for BrokerBeacon.

Registers Sprint 37 extensions and bridges the existing SaaS platform-owner
context into the extension authorization checks.
"""
from flask import g, session

from app import app, DB
from ai_ops_api import install_ai_ops
from control_tower_ux import install_control_tower_ux
from discovery_ops_api import install_discovery_ops
from ember_automation_api import install_ember_automation
from national_data_center import install_national_data_center
from national_warehouse_api import install_national_warehouse
from state_connector_api import install_state_connectors

install_national_warehouse(app, DB)
install_state_connectors(app, DB)
install_discovery_ops(app, DB)
install_ai_ops(app, DB)
install_ember_automation(app, DB)
install_national_data_center(app)
install_control_tower_ux(app)


@app.before_request
def bridge_platform_owner_context():
    """Expose the canonical SaaS owner flag to Sprint 37 extensions."""
    if bool(getattr(g, "is_platform_owner", False)):
        session["is_platform_owner"] = True
    else:
        session.pop("is_platform_owner", None)


@app.after_request
def add_ember_owner_navigation(response):
    """Add a visible Ember Control Tower entry for authenticated owners."""
    if not bool(getattr(g, "is_platform_owner", False)):
        return response
    content_type = response.headers.get("Content-Type", "")
    if response.status_code != 200 or "text/html" not in content_type.lower():
        return response
    try:
        body = response.get_data(as_text=True)
    except (RuntimeError, UnicodeDecodeError):
        return response
    if "ember-control-tower-link" in body or "</body>" not in body.lower():
        return response
    enhancement = r'''
<script id="ember-control-tower-link">
(function(){
  function addEmberLink(){
    if(document.getElementById('ember-control-tower-button')) return;
    const nav=document.querySelector('aside nav')||document.querySelector('aside');
    if(!nav) return;
    const button=document.createElement('button');
    button.id='ember-control-tower-button';
    button.type='button';
    button.innerHTML='🔥 Ember Control Tower <span style="float:right;font-size:10px;opacity:.75">ALWAYS ON</span>';
    button.title='Open Ember discovery, the National Warehouse, AI operations, and review-gated prospect controls.';
    button.addEventListener('click',function(){window.location.href='/platform/control-tower';});
    nav.appendChild(button);
    const ownerBadge=document.createElement('div');
    ownerBadge.id='platform-owner-badge';
    ownerBadge.textContent='Platform Owner';
    ownerBadge.style.cssText='margin:10px 12px;padding:6px 8px;border-radius:999px;background:#43dfa715;color:#137a55;font-size:10px;font-weight:800;text-align:center';
    nav.appendChild(ownerBadge);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',addEmberLink);
  else addEmberLink();
})();
</script>
'''
    lower = body.lower()
    position = lower.rfind("</body>")
    body = body[:position] + enhancement + body[position:]
    response.set_data(body)
    response.headers["Content-Length"] = str(len(response.get_data()))
    return response


__all__ = ["app"]
