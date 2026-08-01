"""Production WSGI entrypoint for BrokerBeacon."""
from flask import g,session
from app import app,DB
from ai_ops_api import install_ai_ops
from control_tower_ux import install_control_tower_ux
from discovery_ops_api import install_discovery_ops
from ember_automation_api import install_ember_automation
from national_data_center import install_national_data_center
from national_warehouse_api import install_national_warehouse
from sprint38_api import install_sprint38_api
from sprint39_ux import install_sprint39_ux
from state_connector_api import install_state_connectors
install_national_warehouse(app,DB);install_state_connectors(app,DB);install_discovery_ops(app,DB);install_ai_ops(app,DB);install_ember_automation(app,DB);install_sprint38_api(app,DB);install_national_data_center(app);install_control_tower_ux(app);install_sprint39_ux(app)
@app.before_request
def bridge_platform_owner_context():
 if bool(getattr(g,'is_platform_owner',False)):session['is_platform_owner']=True
 else:session.pop('is_platform_owner',None)
@app.after_request
def add_ember_owner_navigation(response):
 if not bool(getattr(g,'is_platform_owner',False)):return response
 if response.status_code!=200 or 'text/html' not in response.headers.get('Content-Type','').lower():return response
 try:body=response.get_data(as_text=True)
 except (RuntimeError,UnicodeDecodeError):return response
 if 'ember-control-tower-link' in body or '</body>' not in body.lower():return response
 enhancement=r'''<script id="ember-control-tower-link">(function(){function add(){if(document.getElementById('ember-control-tower-button'))return;const nav=document.querySelector('aside nav')||document.querySelector('aside');if(!nav)return;const b=document.createElement('button');b.id='ember-control-tower-button';b.type='button';b.innerHTML='🔥 Ember Control Tower <span style="float:right;font-size:10px;opacity:.75">ALWAYS ON</span>';b.title='Open Ember discovery, live activity, review queue, and prospect controls.';b.onclick=()=>window.location.href='/platform/control-tower';nav.appendChild(b);const badge=document.createElement('div');badge.id='platform-owner-badge';badge.textContent='Platform Owner';badge.style.cssText='margin:10px 12px;padding:6px 8px;border-radius:999px;background:#43dfa715;color:#137a55;font-size:10px;font-weight:800;text-align:center';nav.appendChild(badge)}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add()})();</script>'''
 pos=body.lower().rfind('</body>');body=body[:pos]+enhancement+body[pos:];response.set_data(body);response.headers['Content-Length']=str(len(response.get_data()));return response
__all__=['app']
