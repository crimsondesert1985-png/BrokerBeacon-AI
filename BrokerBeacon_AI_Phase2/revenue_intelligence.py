"""Sprint 3 funnel reporting, outcome tracking, and campaign attribution."""
from datetime import datetime, timedelta

FUNNEL_STAGES = ['New','Contacted','Replied','Meeting','Approved']
OUTCOME_STAGES = ['Application','Submitted','Funded','Lost']

def _scalar(conn, sql, params=(), default=0):
    row=conn.execute(sql,params).fetchone()
    return (row[0] if row and row[0] is not None else default)

def _settings(conn):
    return {r['key']:float(r['value']) for r in conn.execute('select key,value from revenue_settings')}

def _attributed_campaign(conn, prospect_id, event_at):
    row=conn.execute('''select c.id,c.name,cr.sent_at from campaign_recipients cr
        join campaigns c on c.id=cr.campaign_id
        where cr.prospect_id=? and cr.status in ('Sent','Delivered') and cr.sent_at<>'' and cr.sent_at<=?
        order by cr.sent_at desc limit 1''',(prospect_id,event_at)).fetchone()
    if not row:return None
    try:
        sent=datetime.fromisoformat(row['sent_at']); event=datetime.fromisoformat(event_at)
        if event-sent>timedelta(days=90):return None
    except Exception:return None
    return {'id':row['id'],'name':row['name']}

def executive_dashboard(conn, days=90):
    settings=_settings(conn)
    total=_scalar(conn,'select count(*) from prospects')
    pipeline={stage:_scalar(conn,'select count(*) from prospects where status=?',(stage,)) for stage in FUNNEL_STAGES}
    outcomes={stage:_scalar(conn,'select count(*) from revenue_events where event_type=? and event_at>=datetime(\'now\',?)',(stage,f'-{days} days')) for stage in OUTCOME_STAGES}
    funded_volume=float(_scalar(conn,"select coalesce(sum(amount),0) from revenue_events where event_type='Funded' and event_at>=datetime('now',?)",(f'-{days} days',)))
    funded_units=outcomes['Funded']
    applications=outcomes['Application']
    projected_apps=max(applications, round(pipeline['Meeting']*settings.get('meeting_to_application_rate',0.35),1))
    projected_units=round(projected_apps*settings.get('application_to_funding_rate',0.55),1)
    projected_volume=round(projected_units*settings.get('average_loan_amount',325000),2)
    projected_revenue=round(projected_volume*(settings.get('revenue_bps',35)/10000),2)
    actual_revenue=round(funded_volume*(settings.get('revenue_bps',35)/10000),2)
    contacted=max(1,pipeline['Contacted']+pipeline['Replied']+pipeline['Meeting']+pipeline['Approved'])
    replies=pipeline['Replied']+pipeline['Meeting']+pipeline['Approved']
    meetings=pipeline['Meeting']+pipeline['Approved']
    conversion={
        'contact_to_reply':round(replies/contacted*100,1),
        'reply_to_meeting':round(meetings/max(replies,1)*100,1),
        'meeting_to_application':round(applications/max(meetings,1)*100,1),
        'application_to_funding':round(funded_units/max(applications,1)*100,1),
    }
    campaigns=[]
    for c in conn.execute('select id,name,channel,status,created_at from campaigns order by id desc'):
        stats=dict(conn.execute('''select count(*) total,
          sum(case when status in ('Sent','Delivered') then 1 else 0 end) sent,
          sum(case when opened_at<>'' then 1 else 0 end) opened,
          sum(case when clicked_at<>'' then 1 else 0 end) clicked,
          sum(case when replied_at<>'' then 1 else 0 end) replied
          from campaign_recipients where campaign_id=?''',(c['id'],)).fetchone())
        attributed=[dict(r) for r in conn.execute('select event_type,amount,event_at,prospect_id from revenue_events where attributed_campaign_id=?',(c['id'],))]
        campaigns.append({**dict(c),**{k:int(v or 0) for k,v in stats.items()},
            'applications':sum(x['event_type']=='Application' for x in attributed),
            'fundings':sum(x['event_type']=='Funded' for x in attributed),
            'funded_volume':sum(float(x['amount'] or 0) for x in attributed)})
    top=[dict(r) for r in conn.execute('''select p.id,p.company,p.city,p.state,p.status,p.score,
      coalesce(sum(case when e.event_type='Funded' then e.amount else 0 end),0) funded_volume,
      sum(case when e.event_type='Application' then 1 else 0 end) applications,
      sum(case when e.event_type='Funded' then 1 else 0 end) fundings
      from prospects p left join revenue_events e on e.prospect_id=p.id
      group by p.id order by funded_volume desc,p.score desc limit 10''')]
    trend=[dict(r) for r in conn.execute('''select substr(event_at,1,7) month,
      sum(case when event_type='Application' then 1 else 0 end) applications,
      sum(case when event_type='Funded' then 1 else 0 end) fundings,
      sum(case when event_type='Funded' then amount else 0 end) funded_volume
      from revenue_events where event_at>=datetime('now','-12 months') group by substr(event_at,1,7) order by month''')]
    recent=[dict(r) for r in conn.execute('''select e.*,p.company,c.name campaign_name from revenue_events e
      join prospects p on p.id=e.prospect_id left join campaigns c on c.id=e.attributed_campaign_id
      order by e.event_at desc,e.id desc limit 20''')]
    return {'period_days':days,'total_prospects':total,'pipeline':pipeline,'outcomes':outcomes,
      'funded_volume':funded_volume,'funded_units':funded_units,'actual_revenue':actual_revenue,
      'projected_volume':projected_volume,'projected_revenue':projected_revenue,
      'conversion':conversion,'campaigns':campaigns,'top_accounts':top,'trend':trend,
      'recent_events':recent,'settings':settings}

def log_revenue_event(conn, data, now):
    pid=int(data.get('prospect_id') or 0); event_type=str(data.get('event_type') or '').strip()
    if event_type not in OUTCOME_STAGES: raise ValueError('Invalid outcome type')
    if not conn.execute('select 1 from prospects where id=?',(pid,)).fetchone(): raise ValueError('Prospect not found')
    amount=max(0,float(data.get('amount') or 0)); event_at=str(data.get('event_at') or now)
    campaign=_attributed_campaign(conn,pid,event_at)
    conn.execute('''insert into revenue_events(prospect_id,event_type,amount,loan_count,notes,event_at,attributed_campaign_id,attribution_method,created_at)
      values(?,?,?,?,?,?,?,?,?)''',(pid,event_type,amount,int(data.get('loan_count') or 1),str(data.get('notes') or ''),event_at,
      campaign['id'] if campaign else None,'Most recent sent campaign within 90 days' if campaign else 'No qualifying campaign',now))
    stage_map={'Application':'Meeting','Submitted':'Approved','Funded':'Approved'}
    if event_type in stage_map:conn.execute('update prospects set status=?,updated_at=? where id=?',(stage_map[event_type],now,pid))
    return {'attributed_campaign':campaign}
