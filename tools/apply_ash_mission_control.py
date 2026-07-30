from pathlib import Path

APP = Path('BrokerBeacon_AI_Phase2/app.py')
text = APP.read_text(encoding='utf-8')

text = text.replace('BUILD_VERSION = "12.0"\nBUILD_NAME = "BROKER DNA"', 'BUILD_VERSION = "12.2"\nBUILD_NAME = "ASH MISSION CONTROL"')
text = text.replace('VERSION 12.0 · BROKER DNA', 'VERSION 12.2 · ASH MISSION CONTROL')
text = text.replace('Projected pipeline potential</span><strong id="mcPotential">$0</strong><small>Model-based, not recorded revenue', '12-month modeled opportunity</span><strong id="mcPotential">$0</strong><small>Modeled from stored account signals')

css = '''
/* v12.2 Ash Mission Control */
.mission-value{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;background:#e8f0fe;color:#174b91;font-size:10px;font-weight:900;margin-left:6px}.dark-mode .mission-value{background:#17345f;color:#d9e8ff}.mission-impact{margin-top:5px;color:#50637f;font-size:11px}.dark-mode .mission-impact{color:#aebed4}
'''
if '/* v12.2 Ash Mission Control */' not in text:
    text = text.replace('</style></head>', css + '</style></head>')

old_js = """<div class="priority-title"><b>${esc(p.company)}</b><span class="health ${p.health.toLowerCase().replace(' ','-')}">${esc(p.health)}</span></div><div class="reason">${esc(p.reason)}</div><small class="muted">${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.status)} · ${p.days_inactive>=999?'No activity logged':p.days_inactive+' days since activity'}</small>"""
new_js = """<div class="priority-title"><b>${esc(p.company)}</b><span class="health ${p.health.toLowerCase().replace(' ','-')}">${esc(p.health)}</span><span class="mission-value">${money(p.modeled_annual_volume||0)} modeled</span></div><div class="reason">${esc(p.reason)}</div><div class="mission-impact">Expected path: ${esc(p.expected_path||'Complete the next best action')}</div><small class="muted">${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.status)} · ${p.days_inactive>=999?'No activity logged':p.days_inactive+' days since activity'}</small>"""
if old_js in text:
    text = text.replace(old_js, new_js)
else:
    raise SystemExit('Mission Control priority renderer anchor not found')

old_backend = """    top=ranked[:5]
    avg_loan=settings.get('average_loan_amount',260000)
    projected_apps=max(1,round(len(top)*settings.get('meeting_to_application_rate',.35))) if top else 0
    projected_pipeline=projected_apps*avg_loan
    strongest=max(products,key=lambda x:x['count'])['name'] if products else 'scenario support'
    lead=top[0] if top else None
    brief=(f"Start with {lead['company']}. {lead['reason']} " if lead else "Start with the highest-ranked account. ") + f"There are {len(alerts)} new-account alerts, {len(at_risk)} relationships at risk, and {replies_attention} replies needing attention. The strongest product lane in the current database is {strongest}."
    recommendations=[]
    for x in top[:3]: recommendations.append({'title':f"{x['company']} · {x['health']}",'detail':x['reason']})
    return jsonify(metrics={'priority_calls':len(top),'new_alerts':len(alerts),'at_risk':len(at_risk),'meetings_week':meetings,'meeting_opportunities':min(4,max(0,len([x for x in top if x['score']>=75]))),'application_opportunities':projected_apps,'projected_pipeline_potential':projected_pipeline,'replies_attention':replies_attention},priorities=top,new_alerts=alerts,at_risk=at_risk[:6],products=products,health=health,recommendations=recommendations,goals={'completed':actions_week,'target':50,'percent':min(100,round(actions_week/50*100))},campaigns={'active':active,'queued':camps.get('Queued',0),'sent':camps.get('Sent',0),'failed':camps.get('Failed',0)},brief=brief)
"""
new_backend = """    top=ranked[:5]
    avg_loan=settings.get('average_loan_amount',260000)
    meeting_rate=max(0,min(1,settings.get('meeting_to_application_rate',.35)))
    funding_rate=max(0,min(1,settings.get('application_to_funding_rate',.55)))
    revenue_bps=max(0,settings.get('revenue_bps',35))
    for item in top:
        score_factor=max(.15,min(.95,float(item.get('score') or 0)/100))
        health_factor={'Healthy':1.0,'Cooling':.78,'At Risk':.58}.get(item.get('health'),.7)
        status_factor={'New':.55,'Contacted':.68,'Replied':.82,'Meeting':.92,'Approved':1.0}.get(item.get('status'),.6)
        expected_fundings=score_factor*health_factor*status_factor*meeting_rate*funding_rate
        item['modeled_annual_volume']=round(expected_fundings*avg_loan*12)
        item['modeled_annual_revenue']=round(item['modeled_annual_volume']*(revenue_bps/10000))
        item['expected_path']='Call → conversation → application → funded loan' if item.get('health')=='At Risk' else 'Personalized outreach → conversation → live scenario'
    projected_apps=max(1,round(len(top)*meeting_rate)) if top else 0
    projected_pipeline=sum(int(x.get('modeled_annual_volume') or 0) for x in top)
    projected_revenue=sum(int(x.get('modeled_annual_revenue') or 0) for x in top)
    strongest=max(products,key=lambda x:x['count'])['name'] if products else 'scenario support'
    lead=top[0] if top else None
    brief=(f"Start with {lead['company']}. {lead['reason']} " if lead else "Start with the highest-ranked account. ") + f"Completing today's five priority actions represents approximately ${projected_pipeline:,.0f} in modeled 12-month funded volume and ${projected_revenue:,.0f} in modeled lender revenue. These are planning estimates, not recorded or guaranteed results. There are {len(alerts)} new-account alerts, {len(at_risk)} relationships at risk, and {replies_attention} replies needing attention. The strongest product lane in the current database is {strongest}."
    recommendations=[]
    for x in top[:3]: recommendations.append({'title':f"{x['company']} · {x['health']}",'detail':f"{x['reason']} Modeled 12-month volume: ${x['modeled_annual_volume']:,.0f}."})
    return jsonify(metrics={'priority_calls':len(top),'new_alerts':len(alerts),'at_risk':len(at_risk),'meetings_week':meetings,'meeting_opportunities':min(4,max(0,len([x for x in top if x['score']>=75]))),'application_opportunities':projected_apps,'projected_pipeline_potential':projected_pipeline,'projected_revenue_potential':projected_revenue,'replies_attention':replies_attention},priorities=top,new_alerts=alerts,at_risk=at_risk[:6],products=products,health=health,recommendations=recommendations,goals={'completed':actions_week,'target':50,'percent':min(100,round(actions_week/50*100))},campaigns={'active':active,'queued':camps.get('Queued',0),'sent':camps.get('Sent',0),'failed':camps.get('Failed',0)},brief=brief,methodology='Modeled opportunity uses stored account score, relationship health, status, configured conversion assumptions, average loan amount, and revenue basis points. It is not recorded production or guaranteed revenue.')
"""
if old_backend not in text:
    raise SystemExit('Mission Control backend anchor not found')
text = text.replace(old_backend, new_backend)
APP.write_text(text, encoding='utf-8')
print('Ash Mission Control 12.2 applied')

# Workflow trigger marker: 2026-07-30
