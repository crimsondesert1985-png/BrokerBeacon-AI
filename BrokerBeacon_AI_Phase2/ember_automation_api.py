"""Internal, token-protected endpoint for scheduled Ember discovery batches."""
from __future__ import annotations
import hmac,json,os,sqlite3
from datetime import datetime,timedelta
from flask import Blueprint,jsonify,request
from ember_hunt import launch

def install_ember_automation(app,db_path):
 bp=Blueprint('ember_automation',__name__)
 def connect():
  conn=sqlite3.connect(db_path,timeout=30);conn.row_factory=sqlite3.Row;conn.execute('pragma foreign_keys=on');conn.execute('pragma busy_timeout=30000');return conn
 @bp.post('/api/internal/ember-cycle')
 def scheduled_cycle():
  expected=os.getenv('EMBER_AUTOMATION_TOKEN','').strip();supplied=request.headers.get('X-Ember-Token','').strip()
  if not expected or not supplied or not hmac.compare_digest(expected,supplied):return jsonify(error='Unauthorized'),401
  with connect() as conn:
   conn.execute("""create table if not exists ember_automation_runs(id integer primary key,state text not null,status text not null,detail_json text not null default '{}',created_at text not null,finished_at text default '')""")
   recent=conn.execute("select created_at from ember_automation_runs where status='Running' order by id desc limit 1").fetchone()
   if recent:
    try:
     if datetime.fromisoformat(recent['created_at'])>datetime.now()-timedelta(minutes=20):return jsonify(status='Skipped',reason='An Ember cycle is already running'),202
    except ValueError:pass
   started=datetime.now().isoformat(timespec='seconds');run_id=int(conn.execute("insert into ember_automation_runs(state,status,created_at) values('AUTO','Running',?)",(started,)).lastrowid);conn.commit()
   try:
    result=launch(conn,state='',company_limit=6,contact_limit=250)
    conn.execute("update ember_automation_runs set state=?,status='Completed',detail_json=?,finished_at=? where id=?",(result.get('state',''),json.dumps(result,default=str),datetime.now().isoformat(timespec='seconds'),run_id));conn.commit()
    return jsonify(status='Completed',run_id=run_id,result=result),201
   except Exception as exc:
    conn.execute("update ember_automation_runs set status='Failed',detail_json=?,finished_at=? where id=?",(str(exc)[:1000],datetime.now().isoformat(timespec='seconds'),run_id));conn.commit();app.logger.exception('Scheduled Ember cycle failed');return jsonify(error='Ember cycle failed safely',run_id=run_id),500
 app.register_blueprint(bp);return bp
