"""Consistent, owner-only metric drill-down pages across BrokerBeacon."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, render_template_string, request, session

from broker_company_contacts import sync_company_contacts


DETAILS_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} · BrokerBeacon</title>
<style>
:root{color-scheme:dark;--bg:#06152d;--panel:#0b203e;--line:#58d6ff2e;--text:#eef6ff;--muted:#90a8c8;--cyan:#58d6ff;--green:#45e0a8;--ember:#ff8a52}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0,#ff7a451c,transparent 32%),linear-gradient(145deg,#06152d,#081b38);color:var(--text);font:14px/1.45 Inter,system-ui,sans-serif;min-height:100vh}
main{width:min(1450px,calc(100% - 32px));margin:24px auto}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.back{display:inline-flex;align-items:center;gap:8px;color:#b9d8ff;text-decoration:none;font-weight:800}.back:hover{color:white}
h1{margin:12px 0 5px;font-size:clamp(25px,4vw,40px)}.sub{margin:0;color:var(--muted)}.count{padding:10px 14px;border:1px solid #45e0a83b;border-radius:14px;background:#45e0a812;color:#7cf1c2;font-weight:900;white-space:nowrap}
.tools{display:grid;grid-template-columns:minmax(220px,1fr) 190px auto;gap:9px;margin:15px 0}.tools input,.tools select{min-width:0;padding:12px 14px;border:1px solid #ffffff19;border-radius:12px;background:#0b203e;color:white;outline:none}.tools button{border:0;border-radius:12px;padding:0 18px;background:linear-gradient(135deg,var(--cyan),var(--green));color:#05213a;font-weight:900;cursor:pointer}
.view-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.view-tabs a{padding:8px 12px;border-radius:999px;border:1px solid #ffffff18;background:#ffffff08;color:#b9d8ff;text-decoration:none;font-weight:800}.view-tabs a.active{background:#58d6ff20;border-color:#58d6ff66;color:white}
.panel{overflow:auto;border:1px solid var(--line);border-radius:18px;background:#071a34d9;box-shadow:0 20px 60px #0006}table{width:100%;border-collapse:collapse;min-width:900px}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid #ffffff0c;vertical-align:top}th{position:sticky;top:0;background:#0c2343;color:#9fc0e7;font-size:11px;text-transform:uppercase;letter-spacing:.07em}tr:hover td{background:#58d6ff08}td{color:#dceaff;max-width:360px;overflow-wrap:anywhere}.empty{padding:60px 20px;text-align:center;color:var(--muted)}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#58d6ff12;border:1px solid #58d6ff2c;font-size:11px}.open-link{color:#7fdcff;text-decoration:none;font-weight:800}
@media(max-width:700px){main{width:min(100% - 18px,1450px);margin:12px auto}.top{display:block}.count{display:inline-block;margin-top:12px}.tools{grid-template-columns:1fr}.tools button{padding:12px}}
</style>
</head>
<body><main>
<div class="top"><div><a class="back" href="/platform/control-tower">← Back to BrokerBeacon</a><h1>{{ title }}</h1><p class="sub">{{ description }}</p></div><div class="count">{{ rows|length }} records shown</div></div>
{% if kind in ('prospects','contacts') %}<nav class="view-tabs"><a class="{{ 'active' if kind=='prospects' else '' }}" href="/platform/details/prospects?state={{ state }}">Company prospects</a><a class="{{ 'active' if kind=='contacts' else '' }}" href="/platform/details/contacts?state={{ state }}">Loan-officer contacts</a></nav>{% endif %}
<form class="tools" method="get"><input name="q" value="{{ query }}" placeholder="Search company, person, city, NMLS, phone, or email…"><select name="state" onchange="this.form.submit()"><option value="">All states</option>{% for item in states %}<option value="{{ item }}" {{ 'selected' if item==state else '' }}>{{ item }}</option>{% endfor %}</select><input type="hidden" name="status" value="{{ status }}"><button>Search</button></form>
<section class="panel">
{% if rows %}<table><thead><tr>{% for header in headers %}<th>{{ header|replace('_',' ') }}</th>{% endfor %}</tr></thead><tbody>{% for row in rows %}<tr>{% for header in headers %}<td>{% if header in ('status','review_status','event_type') %}<span class="pill">{{ row.get(header,'') }}</span>{% elif header=='intelligence' and row.get('id') %}<a class="open-link" href="/platform/details/prospect/{{ row.get('id') }}">Open intelligence →</a>{% else %}{{ row.get(header,'') }}{% endif %}</td>{% endfor %}</tr>{% endfor %}</tbody></table>{% else %}<div class="empty">No matching records yet. Ember discoveries will appear here automatically after they are staged for review.</div>{% endif %}
</section></main></body></html>"""

DETAIL_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ company.company_name }} · Intelligence</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#06152d;color:#eef6ff;font:14px/1.5 Inter,system-ui,sans-serif}main{width:min(1100px,calc(100% - 28px));margin:24px auto}.back{color:#9fdcff;text-decoration:none;font-weight:800}.hero,.card{margin-top:16px;padding:20px;border:1px solid #58d6ff2e;border-radius:18px;background:#0b203e}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric{padding:12px;border-radius:12px;background:#ffffff08}.muted{color:#90a8c8}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:11px;border-bottom:1px solid #ffffff12}a{color:#7fdcff}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body><main><a class="back" href="/platform/details/prospects?state={{ company.state }}">← Back to {{ company.state or 'all' }} prospects</a><section class="hero"><h1>{{ company.company_name }}</h1><p class="muted">{{ company.city }}{% if company.state %}, {{ company.state }}{% endif %} · NMLS {{ company.nmls_id or 'not found' }}</p><div class="grid"><div class="metric"><b>{{ company.team_count }}</b><div class="muted">loan officers found</div></div><div class="metric"><b>{{ company.phone or 'Not found' }}</b><div class="muted">company phone</div></div><div class="metric"><b>{{ company.public_email or 'Not found' }}</b><div class="muted">company email</div></div></div>{% if company.source_url %}<p><a target="_blank" rel="noopener" href="{{ company.source_url }}">Open company website ↗</a></p>{% endif %}</section><section class="card"><h2>Loan officers and team</h2>{% if team %}<table><thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Phone</th><th>NMLS</th></tr></thead><tbody>{% for x in team %}<tr><td>{{ x.person_name }}</td><td>{{ x.role }}</td><td>{{ x.public_email }}</td><td>{{ x.phone }}</td><td>{{ x.nmls_id }}</td></tr>{% endfor %}</tbody></table>{% else %}<p class="muted">No loan officers have been attached yet. Ember can enrich this company on a later pass.</p>{% endif %}</section></main></body></html>"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma busy_timeout=30000")
    return conn


def _states(conn: sqlite3.Connection) -> list[str]:
    return [str(row[0]) for row in conn.execute("select distinct state from discovered_contacts where trim(coalesce(state,''))<>'' order by state")]


def _dataset(conn: sqlite3.Connection, kind: str, status: str, query: str, state: str) -> tuple[str, str, list[str], list[dict]]:
    like = f"%{query.strip()}%"
    if kind == "jobs":
        where,args=[],[]
        if status=="active":where.append("status in ('Queued','Running')")
        elif status=="completed":where.extend(["status='Completed'","substr(completed_at,1,10)=?"]);args.append(datetime.now().date().isoformat())
        elif status=="failed":where.append("status='Failed'")
        if state:where.append("state=?");args.append(state)
        if query:where.append("(state like ? or job_type like ? or status like ? or last_error like ?)");args.extend([like]*4)
        rows=[dict(r) for r in conn.execute("select id,job_type,state,status,attempts,claimed_by,created_at,completed_at,last_error from crawl_jobs"+(" where "+" and ".join(where) if where else "")+" order by id desc limit 500",args)]
        return "Discovery jobs","Queue activity, status, timing, state, and errors.",list(rows[0]) if rows else ["id","job_type","state","status","created_at"],rows
    if kind in {"prospects","contacts"}:
        sync_company_contacts(conn,state)
        where,args=["d.review_status<>'Rejected'"],[]
        if kind=="prospects":where.extend(["trim(coalesce(d.person_name,''))=''","d.role='Mortgage Brokerage'"])
        else:where.append("trim(coalesce(d.person_name,''))<>''")
        if status=="pending":where.append("d.review_status='Pending review'")
        if state:where.append("d.state=?");args.append(state)
        if query:where.append("(d.person_name like ? or d.company_name like ? or d.role like ? or d.state like ? or d.city like ? or d.public_email like ? or d.phone like ? or d.nmls_id like ?)");args.extend([like]*8)
        if kind=="prospects":
            sql="""select d.id,d.company_name,d.city,d.state,d.phone,d.public_email,d.nmls_id,d.review_status,coalesce(a.opportunity_score,0) opportunity_score,(select count(*) from discovered_contacts t where t.source_domain=d.source_domain and trim(coalesce(t.person_name,''))<>'' and t.review_status<>'Rejected') team_count,d.created_at,'Open' intelligence from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id"""
        else:
            sql="""select d.id,d.person_name,d.company_name,d.role,d.city,d.state,d.public_email,d.phone,d.nmls_id,d.review_status,d.created_at from discovered_contacts d"""
        rows=[dict(r) for r in conn.execute(sql+" where "+" and ".join(where)+" order by "+("opportunity_score desc," if kind=="prospects" else "")+"d.id desc limit 1000",args)]
        title="Company prospects" if kind=="prospects" else "Loan-officer contacts"
        desc="One row per brokerage. Open Intelligence to see all attached loan officers." if kind=="prospects" else "Public loan-officer contacts attached to the brokerage where Ember found them."
        return title,desc,list(rows[0]) if rows else (["id","company_name","city","state","team_count","review_status","intelligence"] if kind=="prospects" else ["id","person_name","company_name","role","state","public_email","phone"]),rows
    if kind=="companies":
        where,args=[],[]
        if state:where.append("state=?");args.append(state)
        if query:where.append("(company_name like ? or state like ? or source_domain like ? or status like ?)");args.extend([like]*4)
        rows=[dict(r) for r in conn.execute("select company_name,state,source_domain,status,contacts_found,pages_fetched,last_crawled_at,next_crawl_at from ember_company_history"+(" where "+" and ".join(where) if where else "")+" order by last_crawled_at desc limit 500",args)]
        return "Tracked companies","Companies Ember has checked, queued, or scheduled for refresh.",list(rows[0]) if rows else ["company_name","state","status","contacts_found","last_crawled_at"],rows
    if kind=="states":
        rows=[dict(r) for r in conn.execute("select state,last_index_id,companies_processed,contacts_found,last_run_at,updated_at from ember_state_cursors order by coalesce(last_run_at,'') desc,state")]
        return "State coverage","Coverage, yield, and most recent discovery activity by state.",list(rows[0]) if rows else ["state","companies_processed","contacts_found","last_run_at"],rows
    where,args=[],[]
    if status=="failed":where.append("event_type like '%Failed%'")
    if state:where.append("state=?");args.append(state)
    if query:where.append("(event_type like ? or state like ? or message like ? or detail_json like ?)");args.extend([like]*4)
    rows=[dict(r) for r in conn.execute("select id,event_type,worker_key,job_id,state,message,created_at from activity_events"+(" where "+" and ".join(where) if where else "")+" order by id desc limit 500",args)]
    return "System activity","A detailed timeline of Ember and BrokerBeacon operational events.",list(rows[0]) if rows else ["id","event_type","job_id","state","message","created_at"],rows


def install_interaction_drilldowns(app, db_path):
    bp=Blueprint("interaction_drilldowns",__name__)
    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not bool(getattr(g,"is_platform_owner",False) or session.get("is_platform_owner")):return "Platform owner access required",403
            return fn(*args,**kwargs)
        return wrapped
    @bp.get("/platform/details/<kind>")
    @owner_required
    def details(kind):
        if kind not in {"jobs","activity","prospects","contacts","companies","states"}:return "Unknown detail view",404
        status=str(request.args.get("status") or "").strip().lower();query=str(request.args.get("q") or "").strip()[:120];state=str(request.args.get("state") or "").strip().upper()[:2]
        try:
            with _connect(db_path) as conn:title,description,headers,rows=_dataset(conn,kind,status,query,state);states=_states(conn)
        except sqlite3.OperationalError:
            title,description,headers,rows,states="Details unavailable","The underlying data is still initializing.",[],[],[]
        return render_template_string(DETAILS_TEMPLATE,title=title,description=description,headers=headers,rows=rows,query=query,status=status,state=state,states=states,kind=kind)
    @bp.get("/platform/details/prospect/<int:contact_id>")
    @owner_required
    def prospect_detail(contact_id):
        with _connect(db_path) as conn:
            row=conn.execute("select * from discovered_contacts where id=? and trim(coalesce(person_name,''))=''",(contact_id,)).fetchone()
            if not row:return "Prospect not found",404
            company=dict(row);team=[dict(r) for r in conn.execute("select * from discovered_contacts where source_domain=? and trim(coalesce(person_name,''))<>'' and review_status<>'Rejected' order by confidence desc,id desc",(company.get("source_domain",""),))];company["team_count"]=len(team)
        return render_template_string(DETAIL_TEMPLATE,company=company,team=team)
    app.register_blueprint(bp)
    return bp
