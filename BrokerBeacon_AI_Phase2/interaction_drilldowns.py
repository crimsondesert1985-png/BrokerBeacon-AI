"""Consistent, owner-only metric drill-down pages across BrokerBeacon."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, render_template_string, request, session


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
.tools{display:flex;gap:9px;margin:15px 0}.tools input{flex:1;min-width:0;padding:12px 14px;border:1px solid #ffffff19;border-radius:12px;background:#ffffff08;color:white;outline:none}.tools button{border:0;border-radius:12px;padding:0 18px;background:linear-gradient(135deg,var(--cyan),var(--green));color:#05213a;font-weight:900;cursor:pointer}
.panel{overflow:auto;border:1px solid var(--line);border-radius:18px;background:#071a34d9;box-shadow:0 20px 60px #0006}table{width:100%;border-collapse:collapse;min-width:850px}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid #ffffff0c;vertical-align:top}th{position:sticky;top:0;background:#0c2343;color:#9fc0e7;font-size:11px;text-transform:uppercase;letter-spacing:.07em}tr:hover td{background:#58d6ff08}td{color:#dceaff;max-width:360px;overflow-wrap:anywhere}.empty{padding:60px 20px;text-align:center;color:var(--muted)}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#58d6ff12;border:1px solid #58d6ff2c;font-size:11px}
@media(max-width:700px){main{width:min(100% - 18px,1450px);margin:12px auto}.top{display:block}.count{display:inline-block;margin-top:12px}}
</style>
</head>
<body><main>
<div class="top"><div><a class="back" href="/platform/control-tower">← Back to BrokerBeacon</a><h1>{{ title }}</h1><p class="sub">{{ description }}</p></div><div class="count">{{ rows|length }} records shown</div></div>
<form class="tools" method="get"><input name="q" value="{{ query }}" placeholder="Filter these details…"><input type="hidden" name="status" value="{{ status }}"><button>Search</button></form>
<section class="panel">
{% if rows %}
<table><thead><tr>{% for header in headers %}<th>{{ header|replace('_',' ') }}</th>{% endfor %}</tr></thead>
<tbody>{% for row in rows %}<tr>{% for header in headers %}<td>{% if header in ('status','review_status','event_type') %}<span class="pill">{{ row.get(header,'') }}</span>{% else %}{{ row.get(header,'') }}{% endif %}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
{% else %}<div class="empty">No matching details yet.</div>{% endif %}
</section></main></body></html>"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma busy_timeout=30000")
    return conn


def _dataset(conn: sqlite3.Connection, kind: str, status: str, query: str) -> tuple[str, str, list[str], list[dict]]:
    like = f"%{query.strip()}%"
    if kind == "jobs":
        where, args = [], []
        if status == "active":
            where.append("status in ('Queued','Running')")
        elif status == "completed":
            where.extend(["status='Completed'", "substr(completed_at,1,10)=?"])
            args.append(datetime.now().date().isoformat())
        elif status == "failed":
            where.append("status='Failed'")
        if query:
            where.append("(state like ? or job_type like ? or status like ? or last_error like ?)")
            args.extend([like] * 4)
        sql = """select id,job_type,state,status,attempts,claimed_by,created_at,completed_at,last_error
                 from crawl_jobs""" + (" where " + " and ".join(where) if where else "") + " order by id desc limit 500"
        rows = [dict(row) for row in conn.execute(sql, args)]
        label = "Active jobs" if status == "active" else "Completed today" if status == "completed" else "Discovery jobs"
        return label, "Queue activity, status, timing, state, and errors.", list(rows[0]) if rows else ["id","job_type","state","status","created_at"], rows

    if kind in {"prospects", "contacts"}:
        where, args = [], []
        if kind == "prospects" or status == "pending":
            where.append("d.review_status='Pending review'")
        if query:
            where.append("""(d.person_name like ? or d.company_name like ? or d.role like ? or
                              d.state like ? or d.city like ? or d.public_email like ? or d.phone like ?)""")
            args.extend([like] * 7)
        sql = """select d.id,d.person_name,d.company_name,d.role,d.city,d.state,d.public_email,d.phone,
                        d.nmls_id,d.review_status,coalesce(a.opportunity_score,0) opportunity_score,
                        d.discovered_at
                 from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id""" + (
                 " where " + " and ".join(where) if where else "") + " order by opportunity_score desc,d.id desc limit 500"
        rows = [dict(row) for row in conn.execute(sql, args)]
        title = "Prospects pending review" if kind == "prospects" else "Discovered contacts"
        return title, "Open the facts behind the dashboard total and review the underlying records.", list(rows[0]) if rows else ["id","person_name","company_name","state","review_status"], rows

    if kind == "companies":
        args = [like] * 4 if query else []
        where = " where company_name like ? or state like ? or source_domain like ? or status like ?" if query else ""
        rows = [dict(row) for row in conn.execute(
            """select company_name,state,source_domain,status,contacts_found,pages_fetched,last_crawled_at,next_crawl_at
               from ember_company_history""" + where + " order by last_crawled_at desc limit 500", args)]
        return "Tracked companies", "Companies Ember has checked, queued, or scheduled for refresh.", list(rows[0]) if rows else ["company_name","state","status","contacts_found","last_crawled_at"], rows

    if kind == "states":
        args = [like] * 2 if query else []
        where = " where state like ? or last_run_at like ?" if query else ""
        rows = [dict(row) for row in conn.execute(
            """select state,last_index_id,companies_processed,contacts_found,last_run_at,updated_at
               from ember_state_cursors""" + where + " order by coalesce(last_run_at,'') desc,state", args)]
        return "State coverage", "Coverage, yield, and most recent discovery activity by state.", list(rows[0]) if rows else ["state","companies_processed","contacts_found","last_run_at"], rows

    where, args = [], []
    if status == "failed":
        where.append("event_type like '%Failed%'")
    if query:
        where.append("(event_type like ? or state like ? or message like ? or detail_json like ?)")
        args.extend([like] * 4)
    rows = [dict(row) for row in conn.execute(
        """select id,event_type,worker_key,job_id,state,message,created_at from activity_events""" +
        (" where " + " and ".join(where) if where else "") + " order by id desc limit 500", args)]
    return "System activity", "A detailed timeline of Ember and BrokerBeacon operational events.", list(rows[0]) if rows else ["id","event_type","job_id","state","message","created_at"], rows


def install_interaction_drilldowns(app, db_path):
    bp = Blueprint("interaction_drilldowns", __name__)

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner")):
                return "Platform owner access required", 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/platform/details/<kind>")
    @owner_required
    def details(kind):
        if kind not in {"jobs", "activity", "prospects", "contacts", "companies", "states"}:
            return "Unknown detail view", 404
        status = str(request.args.get("status") or "").strip().lower()
        query = str(request.args.get("q") or "").strip()[:120]
        try:
            with _connect(db_path) as conn:
                title, description, headers, rows = _dataset(conn, kind, status, query)
        except sqlite3.OperationalError:
            title, description, headers, rows = "Details unavailable", "The underlying data is still initializing.", [], []
        return render_template_string(
            DETAILS_TEMPLATE, title=title, description=description, headers=headers,
            rows=rows, query=query, status=status,
        )

    app.register_blueprint(bp)

    @app.after_request
    def add_global_drilldowns(response):
        if response.status_code != 200 or not response.is_sequence:
            return response
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            html = response.get_data(as_text=True)
            if "brokerbeacon-global-drilldowns" in html or "</body>" not in html.lower():
                return response
            enhancement = r"""<style id="brokerbeacon-global-drilldowns">
.bb-drilldown{cursor:pointer!important;position:relative;transition:transform .18s,border-color .18s,box-shadow .18s}
.bb-drilldown:hover,.bb-drilldown:focus{transform:translateY(-2px);border-color:#58d6ff66!important;box-shadow:0 12px 28px #0004;outline:none}
.bb-drilldown:after{content:'View details →';display:block;margin-top:6px;color:#73cfff;font-size:10px;font-weight:800;letter-spacing:.02em}
</style><script id="brokerbeacon-global-drilldowns">
(function(){
const rules=[
[/failure|failed|error|alert|issue/,'/platform/details/activity?status=failed'],
[/active job|active hunt|current job|queue/,'/platform/details/jobs?status=active'],
[/completed today|completed job|successful discovery/,'/platform/details/jobs?status=completed'],
[/pending review|needs review|await.*review/,'/platform/details/prospects?status=pending'],
[/contact|lead|people found|prospect found/,'/platform/details/contacts'],
[/tracked compan|companies|accounts/,'/platform/details/companies'],
[/state coverage|states reached|market coverage|needs refresh/,'/platform/details/states'],
[/activity|event|history|heartbeat/,'/platform/details/activity']
];
const selectors='.s41-card,.metric-card,.stat-card,.kpi-card,.summary-card,.dashboard-card,[class*="metric-card"],[class*="stat-card"],[class*="kpi-card"]';
function routeFor(el){const explicit=el.getAttribute('data-detail-href');if(explicit)return explicit;const text=(el.innerText||'').replace(/\s+/g,' ').trim().toLowerCase();if(!text||text.length>180)return'';for(const item of rules){if(item[0].test(text))return item[1]}return''}
function install(){document.querySelectorAll(selectors).forEach(function(el){if(el.classList.contains('bb-drilldown')||el.closest('a,button,form')||el.querySelector('a,button,input,select,textarea'))return;const href=routeFor(el);if(!href)return;el.classList.add('bb-drilldown');el.tabIndex=0;el.setAttribute('role','link');el.setAttribute('aria-label','View details for '+(el.innerText||'this metric').replace(/\s+/g,' ').trim());el.addEventListener('click',function(e){if(e.target.closest('a,button,input,select,textarea'))return;window.location.href=href});el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();window.location.href=href}})})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
new MutationObserver(function(){install()}).observe(document.documentElement,{childList:true,subtree:true});
})();
</script>"""
            pos = html.lower().rfind("</body>")
            html = html[:pos] + enhancement + html[pos:]
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            app.logger.exception("Global drill-down enhancement failed")
        return response

    return bp
