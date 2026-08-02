"""Decision-first founder briefing for BrokerBeacon's platform owner."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from flask import g, jsonify, request


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma busy_timeout=30000")
    return conn


def _tables(conn):
    return {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def _count(conn, sql, args=()):
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    except (sqlite3.Error, TypeError, IndexError):
        return 0


def build_briefing(conn):
    """Return a compact, migration-tolerant briefing with one next action."""
    tables = _tables(conn)
    since = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")

    companies_24h = 0
    if "ember_company_history" in tables:
        cols = _columns(conn, "ember_company_history")
        timestamp = "first_seen_at" if "first_seen_at" in cols else "last_crawled_at" if "last_crawled_at" in cols else ""
        if timestamp:
            companies_24h = _count(conn, f"select count(*) from ember_company_history where {timestamp}>=?", (since,))

    contacts_24h = pending_review = high_priority = 0
    if "discovered_contacts" in tables:
        cols = _columns(conn, "discovered_contacts")
        created = "created_at" if "created_at" in cols else "discovered_at" if "discovered_at" in cols else ""
        if created:
            contacts_24h = _count(conn, f"select count(*) from discovered_contacts where {created}>=?", (since,))
        if "review_status" in cols:
            pending_review = _count(conn, "select count(*) from discovered_contacts where review_status='Pending review'")
        if "opportunity_score" in cols:
            high_priority = _count(conn, "select count(*) from discovered_contacts where opportunity_score>=75" + (" and review_status='Pending review'" if "review_status" in cols else ""))
    if not high_priority and "ai_contact_insights" in tables:
        cols = _columns(conn, "ai_contact_insights")
        if "opportunity_score" in cols:
            high_priority = _count(conn, "select count(*) from ai_contact_insights where opportunity_score>=75")

    states_reached = active_hunts = 0
    if "ember_state_cursors" in tables:
        states_reached = _count(conn, "select count(*) from ember_state_cursors where coalesce(last_run_at,'')<>''")
    if "crawl_jobs" in tables:
        active_hunts = _count(conn, "select count(*) from crawl_jobs where status in ('Queued','Running')")

    worker = {"status": "Waiting", "last_heartbeat_at": "", "current_job_id": None}
    if "worker_status" in tables:
        row = conn.execute("select status,last_heartbeat_at,current_job_id from worker_status order by updated_at desc limit 1").fetchone()
        if row:
            worker = dict(row)

    if high_priority:
        action = {
            "title": f"Review {high_priority} high-priority prospect{'s' if high_priority != 1 else ''}",
            "detail": "Ember ranked these as the strongest opportunities requiring a human decision.",
            "label": "Open priority review",
            "href": "/platform/control-tower#review",
            "kind": "priority",
        }
    elif pending_review:
        amount = min(pending_review, 10)
        action = {
            "title": f"Review the next {amount} prospect{'s' if amount != 1 else ''}",
            "detail": f"{pending_review} prospect{'s are' if pending_review != 1 else ' is'} waiting; start with a decision-sized batch.",
            "label": "Start review",
            "href": "/platform/control-tower#review",
            "kind": "review",
        }
    elif active_hunts:
        action = {
            "title": "Let Ember keep hunting",
            "detail": f"{active_hunts} national discovery job{'s are' if active_hunts != 1 else ' is'} already queued or running.",
            "label": "Watch live activity",
            "href": "/platform/control-tower#activity",
            "kind": "working",
        }
    else:
        action = {
            "title": "Refill the national hunt queue",
            "detail": "Ember has no active discovery work. Refill the bounded all-state queue.",
            "label": "Queue national hunts",
            "href": "/platform/control-tower#national",
            "kind": "attention",
        }

    return {
        "window_hours": 24,
        "companies_discovered": companies_24h,
        "contacts_discovered": contacts_24h,
        "high_priority": high_priority,
        "pending_review": pending_review,
        "states_reached": states_reached,
        "national_states": 50,
        "active_hunts": active_hunts,
        "worker": worker,
        "recommended_action": action,
        "dedication": "Built with purpose. Dedicated to Aiden.",
        "outreach_enabled": False,
    }


def install_founder_briefing(app, db_path):
    @app.get("/api/platform/founder-briefing")
    def founder_briefing_api():
        if not bool(getattr(g, "is_platform_owner", False)):
            return jsonify(error="Platform Owner access required"), 403
        with _connect(db_path) as conn:
            return jsonify(build_briefing(conn))

    @app.after_request
    def inject_founder_briefing(response):
        if not bool(getattr(g, "is_platform_owner", False)):
            return response
        if request.path != "/platform/control-tower" or response.status_code != 200:
            return response
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "founder-briefing-shell" in body or "</body>" not in body.lower():
            return response
        enhancement = r'''
<style id="founder-briefing-style">
#founder-briefing-shell{margin:16px 0 20px;padding:1px;border-radius:24px;background:linear-gradient(120deg,#36e4ba55,#6c63ff55,#ff5f8f55);box-shadow:0 22px 70px #06142b35}
#founder-briefing{position:relative;overflow:hidden;border-radius:23px;padding:24px;background:linear-gradient(145deg,#07162ef5,#0d2347f2);color:#eef6ff}
#founder-briefing:after{content:'';position:absolute;width:240px;height:240px;border-radius:50%;right:-90px;top:-110px;background:#6c63ff33;filter:blur(8px)}
.fb-top,.fb-stats,.fb-action{position:relative;z-index:1}.fb-top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.fb-kicker{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#65e6c2;font-weight:900}.fb-title{font-size:clamp(22px,4vw,36px);margin:7px 0 4px;font-weight:900}.fb-sub{color:#adc0dc}.fb-live{padding:8px 12px;border-radius:999px;background:#43dfa719;border:1px solid #43dfa744;color:#6cf0c8;font-size:11px;font-weight:900;white-space:nowrap}.fb-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}.fb-stat{padding:14px;border-radius:16px;background:#ffffff0b;border:1px solid #ffffff16;cursor:pointer;transition:.18s transform,.18s background}.fb-stat:hover{transform:translateY(-2px);background:#ffffff13}.fb-num{font-size:24px;font-weight:900}.fb-label{font-size:11px;color:#aebed6;margin-top:3px}.fb-action{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:17px;border-radius:18px;background:linear-gradient(105deg,#ffffff12,#ffffff08);border:1px solid #ffffff1e}.fb-action h3{margin:0 0 4px;font-size:17px}.fb-action p{margin:0;color:#b9c8dc;font-size:13px}.fb-button{border:0;border-radius:12px;padding:12px 16px;background:linear-gradient(110deg,#43dfa7,#69a7ff);color:#07162e;font-weight:900;cursor:pointer;white-space:nowrap}.fb-dedication{position:relative;z-index:1;text-align:center;margin-top:16px;color:#8fa4c4;font-size:11px;font-style:italic}@media(max-width:720px){.fb-top,.fb-action{align-items:stretch;flex-direction:column}.fb-stats{grid-template-columns:repeat(2,1fr)}.fb-button{width:100%}}
</style>
<section id="founder-briefing-shell"><div id="founder-briefing" aria-live="polite"><div class="fb-top"><div><div class="fb-kicker">Founder briefing</div><div class="fb-title">Good to have you back, Clay.</div><div class="fb-sub">Ember is preparing your decision-first briefing…</div></div><div class="fb-live">● EMBER LIVE</div></div><div class="fb-stats"><div class="fb-stat"><div class="fb-num">—</div><div class="fb-label">Companies found</div></div><div class="fb-stat"><div class="fb-num">—</div><div class="fb-label">Contacts found</div></div><div class="fb-stat"><div class="fb-num">—</div><div class="fb-label">Priority reviews</div></div><div class="fb-stat"><div class="fb-num">—</div><div class="fb-label">States reached</div></div></div><div class="fb-action"><div><h3>Finding your best next step…</h3><p>Only actionable work will appear here.</p></div><button class="fb-button" type="button">Loading</button></div><div class="fb-dedication">Built with purpose. Dedicated to Aiden.</div></div></section>
<script id="founder-briefing-script">(function(){const root=document.getElementById('founder-briefing');if(!root)return;const nums=root.querySelectorAll('.fb-num'),stats=root.querySelectorAll('.fb-stat'),action=root.querySelector('.fb-action'),sub=root.querySelector('.fb-sub');function load(){fetch('/api/platform/founder-briefing',{credentials:'same-origin'}).then(r=>r.ok?r.json():Promise.reject()).then(d=>{nums[0].textContent=d.companies_discovered;nums[1].textContent=d.contacts_discovered;nums[2].textContent=d.high_priority;nums[3].textContent=d.states_reached+'/50';sub.textContent='In the last 24 hours, Ember worked nationwide and filtered the result down to one useful decision.';const links=['/platform/control-tower#companies','/platform/control-tower#contacts','/platform/control-tower#review','/platform/control-tower#national'];stats.forEach((s,i)=>s.onclick=()=>location.href=links[i]);action.innerHTML='<div><h3>'+d.recommended_action.title+'</h3><p>'+d.recommended_action.detail+'</p></div><button class="fb-button" type="button">'+d.recommended_action.label+'</button>';action.querySelector('button').onclick=()=>location.href=d.recommended_action.href}).catch(()=>{sub.textContent='Briefing data is temporarily unavailable. Ember continues working safely.';action.querySelector('h3').textContent='Open live operations';action.querySelector('p').textContent='Review worker health and recent activity.';const b=action.querySelector('button');b.textContent='Open Control Tower';b.onclick=()=>location.href='/platform/control-tower#activity'})}load();setInterval(load,30000)})();</script>
'''
        marker = body.lower().find("<main")
        if marker >= 0:
            close = body.find(">", marker)
            body = body[:close + 1] + enhancement + body[close + 1:]
        else:
            pos = body.lower().rfind("</body>")
            body = body[:pos] + enhancement + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response


__all__ = ["build_briefing", "install_founder_briefing"]
