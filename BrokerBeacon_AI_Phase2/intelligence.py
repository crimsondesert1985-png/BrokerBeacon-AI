"""Explainable opportunity scoring, product matching, and next-best-action logic."""
import json
from datetime import datetime, timedelta

def _parse_date(value):
    if not value:return None
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=None)
    except Exception:return None

def _weights(conn):
    return {r['key']:int(r['weight']) for r in conn.execute('select key,weight from scoring_settings')}

def _latest_activity(conn,pid):
    vals=[]
    for sql in [
        'select max(created_at) from sales_actions where prospect_id=?',
        'select max(created_at) from memories where prospect_id=?',
        'select max(created_at) from outreach where prospect_id=?',
        'select max(received_at) from inbound_messages where prospect_id=?']:
        try:
            v=conn.execute(sql,(pid,)).fetchone()[0]
            if v: vals.append(v)
        except Exception:pass
    parsed=[_parse_date(v) for v in vals if _parse_date(v)]
    return max(parsed) if parsed else None

def score_prospect(conn,p):
    w=_weights(conn); reasons=[]; raw=0; confidence=45
    text=' '.join(str(p.get(k) or '') for k in ('signal','specialties','product_fit','ai_summary','verification_status')).lower()
    if 'verified' in str(p.get('verification_status') or '').lower(): raw+=w['base_verified'];reasons.append((w['base_verified'],'Verified source data'));confidence+=10
    if any(x in text for x in ('newly licensed','new broker','new account')):raw+=w['recently_licensed'];reasons.append((w['recently_licensed'],'New or recently licensed brokerage signal'));confidence+=8
    roster=conn.execute('select count(*) from contacts where prospect_id=?',(p['id'],)).fetchone()[0]
    if roster>=2:
        pts=min(w['team_size'],max(4,roster*2));raw+=pts;reasons.append((pts,f'{roster} known contacts / loan officers'));confidence+=min(12,roster)
    gov_terms=('fha','va','usda','dpa','down payment','first-time','government')
    if any(x in text for x in gov_terms):raw+=w['government_fit'];reasons.append((w['government_fit'],'Strong government or first-time-buyer fit'))
    niche_terms=('heloc','jumbo','renovation','niche','equity')
    if any(x in text for x in niche_terms):raw+=w['niche_fit'];reasons.append((w['niche_fit'],'HELOC, jumbo, renovation, or niche-product fit'))
    stage=str(p.get('status') or 'New')
    stage_factor={'Replied':1.0,'Meeting':1.0,'Contacted':.55,'Approved':.4,'New':.2}.get(stage,.2)
    pts=round(w['engagement']*stage_factor);raw+=pts
    if pts:reasons.append((pts,f'Relationship stage: {stage}'))
    latest=_latest_activity(conn,p['id']);days=(datetime.now()-latest).days if latest else 90
    if 21<=days<=120:
        pts=min(w['staleness'],4+(days//21)*2);raw+=pts;reasons.append((pts,f'{days} days since last recorded touch'))
    due=conn.execute("select count(*) from memories where prospect_id=? and follow_up_date<>'' and follow_up_date<=date('now')",(p['id'],)).fetchone()[0]
    if due:raw+=w['followup_due'];reasons.append((w['followup_due'],'Follow-up is due or overdue'))
    score=max(0,min(100,raw+28));confidence=max(45,min(95,confidence+(8 if p.get('email') or p.get('phone') else 0)))
    tier='Hot' if score>=80 else 'Warm' if score>=65 else 'Developing' if score>=50 else 'Research'
    products=[]
    for product in conn.execute('select * from product_catalog where is_active=1 order by category,name'):
        hits=[k.strip() for k in product['keywords'].split(',') if k.strip() and k.strip().lower() in text]
        if hits:products.append({'id':product['id'],'name':product['name'],'category':product['category'],'strength':min(100,45+len(hits)*15),'talking_point':product['talking_point'],'matched':hits})
    products.sort(key=lambda x:-x['strength'])
    if stage in ('Replied','Meeting'):action='Call today and advance the active conversation.'
    elif due:action='Complete the overdue follow-up today.'
    elif score>=80:action='Call today; lead with '+(products[0]['name'] if products else 'scenario support')+'.'
    elif score>=65:action='Send a personalized email, then schedule a call within two business days.'
    elif days>=45:action='Run a reactivation touch and verify current decision-makers.'
    else:action='Add one verified research detail before outreach.'
    return {'prospect_id':p['id'],'company':p['company'],'city':p.get('city'),'state':p.get('state'),'status':stage,'score':score,'tier':tier,'confidence':confidence,'reasons':[{'points':x[0],'reason':x[1]} for x in sorted(reasons,reverse=True)],'next_action':action,'products':products[:4],'days_inactive':days}

def intelligence_dashboard(conn):
    prospects=[dict(r) for r in conn.execute('select * from prospects')]
    scored=[score_prospect(conn,p) for p in prospects]
    scored.sort(key=lambda x:(-x['score'],-x['confidence'],x['company']))
    return {'summary':{'hot':sum(x['tier']=='Hot' for x in scored),'warm':sum(x['tier']=='Warm' for x in scored),'due_today':sum('overdue' in x['next_action'].lower() for x in scored),'product_matches':sum(bool(x['products']) for x in scored)},'opportunities':scored,'products':[dict(r) for r in conn.execute('select * from product_catalog order by category,name')],'settings':[dict(r) for r in conn.execute('select * from scoring_settings order by rowid')]}

def save_snapshots(conn,items,now):
    for x in items:
        conn.execute('insert into opportunity_snapshots(prospect_id,score,tier,confidence,reasons_json,next_action,product_matches_json,created_at) values(?,?,?,?,?,?,?,?)',(x['prospect_id'],x['score'],x['tier'],x['confidence'],json.dumps(x['reasons']),x['next_action'],json.dumps(x['products']),now))
        conn.execute('update prospects set score=?,next_best_action=?,score_reasons=?,product_fit=?,updated_at=? where id=?',(x['score'],x['next_action'],json.dumps([r['reason'] for r in x['reasons']]),', '.join(p['name'] for p in x['products']),now,x['prospect_id']))
