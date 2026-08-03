"""Sprint 38/39 interactive prospect review, activity, health, and drill-down APIs."""
from __future__ import annotations
import sqlite3
from datetime import datetime,timedelta
from functools import wraps
from flask import Blueprint,g,jsonify,request,session
from ai_intelligence import initialize as init_ai
from broker_company_contacts import company_team, sync_company_contacts
from public_search_connector import initialize as init_public
from website_enrichment import initialize as init_enrichment
from ember_activity import initialize as init_ember

def install_sprint38_api(app,db_path):
 bp=Blueprint('sprint38',__name__)
 def connect():
  conn=sqlite3.connect(db_path,timeout=30);conn.row_factory=sqlite3.Row;conn.execute('pragma foreign_keys=on');conn.execute('pragma busy_timeout=30000');return conn
 with connect() as conn:init_public(conn);init_enrichment(conn);init_ai(conn);init_ember(conn);sync_company_contacts(conn)
 def is_owner():return bool(getattr(g,'is_platform_owner',False) or session.get('is_platform_owner'))
 def owner_required(fn):
  @wraps(fn)
  def wrapped(*args,**kwargs):
   if not is_owner():return jsonify(error='Platform owner access required'),403
   return fn(*args,**kwargs)
  return wrapped
 @bp.get('/api/platform/sprint38/contacts')
 @owner_required
 def contacts():
  status=(request.args.get('status') or '').strip();state=(request.args.get('state') or '').strip().upper()[:2];high_only=(request.args.get('high') or '') in {'1','true','yes'};limit=min(max(int(request.args.get('limit') or 100),1),500)
  where,args=["trim(coalesce(d.person_name,''))=''","d.role='Mortgage Brokerage'"],[]
  if status:where.append('d.review_status=?');args.append(status)
  if state:where.append('d.state=?');args.append(state)
  if high_only:where.append('coalesce(a.opportunity_score,0)>=75')
  args.append(limit)
  sql=f"""select d.*,coalesce(a.opportunity_score,0) opportunity_score,coalesce(a.confidence,d.confidence) ai_confidence,coalesce(a.product_fit,'') product_fit,coalesce(a.next_best_action,'') next_best_action,coalesce(a.reasons_json,'[]') reasons_json,coalesce(a.reviewed_status,d.review_status) ai_review_status,(select count(*) from discovered_contacts t where t.source_domain=d.source_domain and trim(coalesce(t.person_name,''))<>'' and t.review_status<>'Rejected') team_count from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id where {' and '.join(where)} order by opportunity_score desc,d.confidence desc,d.id desc limit ?"""
  with connect() as conn:sync_company_contacts(conn,state);rows=[dict(r) for r in conn.execute(sql,args)]
  return jsonify(items=rows,count=len(rows))
 @bp.get('/api/platform/sprint38/contacts/<int:contact_id>')
 @owner_required
 def contact_detail(contact_id):
  with connect() as conn:
   row=conn.execute("""select d.*,coalesce(a.opportunity_score,0) opportunity_score,coalesce(a.confidence,d.confidence) ai_confidence,coalesce(a.product_fit,'') product_fit,coalesce(a.next_best_action,'') next_best_action,coalesce(a.reasons_json,'[]') reasons_json,coalesce(a.canonical_company_name,d.company_name) canonical_company_name,coalesce(a.canonical_person_name,d.person_name) canonical_person_name from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id where d.id=?""",(contact_id,)).fetchone()
   if not row:return jsonify(error='Contact not found'),404
   item=dict(row);item['team']=company_team(conn,item.get('company_name',''),item.get('source_domain',''));item['team_count']=len(item['team'])
  return jsonify(item)
 @bp.post('/api/platform/sprint38/contacts/<int:contact_id>/review')
 @owner_required
 def review_contact(contact_id):
  action=str((request.get_json(silent=True) or {}).get('action') or '').strip().lower();mapping={'approve':'Approved','reject':'Rejected','pending':'Pending review','favorite':'Favorite'}
  if action not in mapping:return jsonify(error='Action must be approve, reject, pending, or favorite'),400
  status=mapping[action]
  with connect() as conn:
   if not conn.execute('select id from discovered_contacts where id=?',(contact_id,)).fetchone():return jsonify(error='Contact not found'),404
   conn.execute('update discovered_contacts set review_status=? where id=?',(status,contact_id));conn.execute('update ai_contact_insights set reviewed_status=? where discovered_contact_id=?',(status,contact_id));conn.commit()
  return jsonify(id=contact_id,review_status=status,outreach_performed=False)
 @bp.get('/api/platform/sprint38/companies')
 @owner_required
 def companies():
  state=(request.args.get('state') or '').strip().upper()[:2];limit=min(max(int(request.args.get('limit') or 100),1),500)
  with connect() as conn:
   sync_company_contacts(conn,state)
   rows=conn.execute("""select d.id,d.company_name,d.state,d.city,d.source_url,d.source_domain,d.created_at discovered_at,(select count(*) from discovered_contacts t where t.source_domain=d.source_domain and trim(coalesce(t.person_name,''))<>'' and t.review_status<>'Rejected') contact_count,coalesce(a.opportunity_score,0) top_score,case when d.review_status='Pending review' then 1 else 0 end pending_count from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id where trim(coalesce(d.person_name,''))='' and d.role='Mortgage Brokerage' and d.review_status<>'Rejected' and (?='' or d.state=?) order by top_score desc,contact_count desc,d.id desc limit ?""",(state,state,limit)).fetchall()
  return jsonify(items=[dict(r) for r in rows],count=len(rows))
 @bp.get('/api/platform/sprint38/companies/detail')
 @owner_required
 def company_detail():
  name=(request.args.get('name') or '').strip()
  if not name:return jsonify(error='Company name is required'),400
  with connect() as conn:
   company=conn.execute("select * from discovered_contacts where company_name=? and trim(coalesce(person_name,''))='' and role='Mortgage Brokerage' order by id desc limit 1",(name,)).fetchone()
   contacts=company_team(conn,name,company['source_domain'] if company else '')
  return jsonify(company=dict(company),contacts=contacts) if company else (jsonify(error='Company not found'),404)
 @bp.get('/api/platform/sprint39/overview')
 @owner_required
 def sprint39_overview():
  with connect() as conn:
   init_ember(conn);sync_company_contacts(conn);since=(datetime.now()-timedelta(hours=24)).isoformat(timespec='seconds')
   activity=[dict(r) for r in conn.execute('select * from ember_activity order by id desc limit 40')]
   states=[dict(r) for r in conn.execute('select * from ember_state_cursors order by state')]
   history=[dict(r) for r in conn.execute('select * from ember_company_history order by id desc limit 75')]
   completed=int(conn.execute("select count(*) from ember_company_history where status='Completed' and last_crawled_at>=?",(since,)).fetchone()[0] or 0);failed=int(conn.execute("select count(*) from ember_company_history where status='Failed' and last_crawled_at>=?",(since,)).fetchone()[0] or 0)
   queue={r[0]:int(r[1]) for r in conn.execute('select status,count(*) from website_enrichment_queue group by status')}
   priorities=[dict(r) for r in conn.execute("""select d.id,d.person_name,d.company_name,d.role,d.phone,d.public_email,d.state,d.source_url,d.source_domain,d.review_status,coalesce(a.opportunity_score,0) opportunity_score,coalesce(a.next_best_action,'Review and verify this brokerage.') next_best_action,coalesce(a.reasons_json,'[]') reasons_json,(select count(*) from discovered_contacts t where t.source_domain=d.source_domain and trim(coalesce(t.person_name,''))<>'' and t.review_status<>'Rejected') team_count from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id where d.review_status='Pending review' and trim(coalesce(d.person_name,''))='' and d.role='Mortgage Brokerage' order by opportunity_score desc,d.confidence desc,d.id desc limit 10""")]
  return jsonify(activity=activity,states=states,companies=history,health={'status':'Healthy' if failed<3 else 'Needs attention','completed_24h':completed,'failures_24h':failed,'queue':queue},priorities=priorities)
 app.register_blueprint(bp);return bp
