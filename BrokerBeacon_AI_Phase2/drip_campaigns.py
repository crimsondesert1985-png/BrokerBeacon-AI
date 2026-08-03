"""Sprint 53: safe email and SMS drip-campaign foundation.

This module stores campaigns, steps, enrollments, consent, suppression, and due
message records. It intentionally does not transmit messages; delivery providers
are connected only after workspace approval and compliance configuration.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from html import escape

from flask import g, jsonify, request, Response


def _now():
    return datetime.now().isoformat(timespec="seconds")


def install_drip_campaigns(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.executescript(
            """
            create table if not exists drip_campaigns(
                id integer primary key,
                workspace_id integer not null,
                created_by integer not null default 0,
                name text not null,
                description text default '',
                status text not null default 'draft',
                approval_required integer not null default 1,
                approved_by integer,
                approved_at text,
                stop_on_reply integer not null default 1,
                quiet_start integer not null default 20,
                quiet_end integer not null default 9,
                created_at text not null,
                updated_at text not null
            );
            create index if not exists idx_drip_campaign_workspace on drip_campaigns(workspace_id,id desc);
            create table if not exists drip_campaign_steps(
                id integer primary key,
                campaign_id integer not null,
                step_order integer not null,
                channel text not null,
                delay_days integer not null default 0,
                subject text default '',
                body text not null,
                created_at text not null,
                unique(campaign_id,step_order)
            );
            create table if not exists drip_enrollments(
                id integer primary key,
                workspace_id integer not null,
                campaign_id integer not null,
                prospect_key text not null,
                prospect_name text not null,
                email text default '',
                phone text default '',
                email_consent integer not null default 0,
                sms_consent integer not null default 0,
                status text not null default 'pending',
                current_step integer not null default 0,
                next_run_at text,
                stop_reason text default '',
                created_at text not null,
                updated_at text not null,
                unique(workspace_id,campaign_id,prospect_key)
            );
            create index if not exists idx_drip_due on drip_enrollments(workspace_id,status,next_run_at);
            create table if not exists drip_suppressions(
                id integer primary key,
                workspace_id integer not null,
                channel text not null,
                destination text not null,
                reason text not null,
                created_at text not null,
                unique(workspace_id,channel,destination)
            );
            create table if not exists drip_events(
                id integer primary key,
                workspace_id integer not null,
                campaign_id integer,
                enrollment_id integer,
                event_type text not null,
                details text default '',
                created_at text not null
            );
            """
        )

    def scope():
        return int(getattr(g, "workspace_id", 0) or 0), int(getattr(g, "user_id", 0) or 0)

    def require_user():
        if not getattr(g, "user_id", None):
            return jsonify(error="Authentication required"), 401
        return None

    @app.get("/api/drip-campaigns")
    def list_drip_campaigns():
        denied = require_user()
        if denied:
            return denied
        workspace_id, _ = scope()
        with connect() as conn:
            rows = conn.execute(
                """select c.*,
                   (select count(*) from drip_campaign_steps s where s.campaign_id=c.id) step_count,
                   (select count(*) from drip_enrollments e where e.campaign_id=c.id and e.workspace_id=c.workspace_id) enrollment_count
                   from drip_campaigns c where c.workspace_id=? order by c.id desc""",
                (workspace_id,),
            ).fetchall()
        return jsonify(items=[dict(row) for row in rows])

    @app.post("/api/drip-campaigns")
    def create_drip_campaign():
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()[:120]
        steps = data.get("steps") or []
        if not name or not isinstance(steps, list) or not steps:
            return jsonify(error="Campaign name and at least one step are required"), 400
        if len(steps) > 20:
            return jsonify(error="Campaigns are limited to 20 steps"), 400
        cleaned = []
        for index, step in enumerate(steps, 1):
            channel = (step.get("channel") or "").lower().strip()
            body = (step.get("body") or "").strip()
            if channel not in {"email", "sms"} or not body:
                return jsonify(error=f"Step {index} requires email or sms and a message body"), 400
            cleaned.append((index, channel, max(0, min(int(step.get("delay_days") or 0), 365)), (step.get("subject") or "")[:180], body[:5000]))
        workspace_id, user_id = scope()
        now = _now()
        with connect() as conn:
            cur = conn.execute(
                """insert into drip_campaigns(workspace_id,created_by,name,description,status,approval_required,stop_on_reply,quiet_start,quiet_end,created_at,updated_at)
                   values(?,?,?,?,?,?,?,?,?,?,?)""",
                (workspace_id, user_id, name, (data.get("description") or "")[:500], "draft", 1,
                 1 if data.get("stop_on_reply", True) else 0,
                 max(0, min(int(data.get("quiet_start") or 20), 23)),
                 max(0, min(int(data.get("quiet_end") or 9), 23)), now, now),
            )
            campaign_id = cur.lastrowid
            conn.executemany(
                "insert into drip_campaign_steps(campaign_id,step_order,channel,delay_days,subject,body,created_at) values(?,?,?,?,?,?,?)",
                [(campaign_id, *step, now) for step in cleaned],
            )
            conn.execute(
                "insert into drip_events(workspace_id,campaign_id,event_type,details,created_at) values(?,?,?,?,?)",
                (workspace_id, campaign_id, "campaign_created", json.dumps({"steps": len(cleaned)}), now),
            )
        return jsonify(ok=True, campaign_id=campaign_id, status="draft"), 201

    @app.post("/api/drip-campaigns/<int:campaign_id>/approve")
    def approve_drip_campaign(campaign_id):
        denied = require_user()
        if denied:
            return denied
        workspace_id, user_id = scope()
        now = _now()
        with connect() as conn:
            cur = conn.execute(
                "update drip_campaigns set status='approved',approved_by=?,approved_at=?,updated_at=? where id=? and workspace_id=? and status in ('draft','paused')",
                (user_id, now, now, campaign_id, workspace_id),
            )
            if not cur.rowcount:
                return jsonify(error="Campaign not found or cannot be approved"), 404
            conn.execute(
                "insert into drip_events(workspace_id,campaign_id,event_type,details,created_at) values(?,?,?,?,?)",
                (workspace_id, campaign_id, "campaign_approved", "First-message approval recorded", now),
            )
        return jsonify(ok=True, status="approved")

    @app.post("/api/drip-campaigns/<int:campaign_id>/enroll")
    def enroll_in_drip_campaign(campaign_id):
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        name = (data.get("prospect_name") or "").strip()[:180]
        key = (data.get("prospect_key") or name.lower()).strip()[:180]
        email = (data.get("email") or "").strip()[:254]
        phone = (data.get("phone") or "").strip()[:40]
        email_consent = bool(data.get("email_consent"))
        sms_consent = bool(data.get("sms_consent"))
        if not name or not key:
            return jsonify(error="Prospect name is required"), 400
        if not ((email and email_consent) or (phone and sms_consent)):
            return jsonify(error="A reachable channel and recorded consent are required"), 400
        workspace_id, _ = scope()
        now = _now()
        with connect() as conn:
            campaign = conn.execute(
                "select status from drip_campaigns where id=? and workspace_id=?",
                (campaign_id, workspace_id),
            ).fetchone()
            if not campaign or campaign["status"] != "approved":
                return jsonify(error="Campaign must be approved before enrollment"), 409
            for channel, destination in (("email", email), ("sms", phone)):
                if destination and conn.execute(
                    "select 1 from drip_suppressions where workspace_id=? and channel=? and destination=?",
                    (workspace_id, channel, destination),
                ).fetchone():
                    return jsonify(error=f"{channel.upper()} destination is suppressed"), 409
            try:
                cur = conn.execute(
                    """insert into drip_enrollments(workspace_id,campaign_id,prospect_key,prospect_name,email,phone,email_consent,sms_consent,status,current_step,next_run_at,created_at,updated_at)
                       values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (workspace_id, campaign_id, key, name, email, phone, int(email_consent), int(sms_consent), "active", 0, now, now, now),
                )
            except sqlite3.IntegrityError:
                return jsonify(error="Prospect is already enrolled in this campaign"), 409
            conn.execute(
                "insert into drip_events(workspace_id,campaign_id,enrollment_id,event_type,details,created_at) values(?,?,?,?,?,?)",
                (workspace_id, campaign_id, cur.lastrowid, "prospect_enrolled", json.dumps({"email_consent": email_consent, "sms_consent": sms_consent}), now),
            )
        return jsonify(ok=True, enrollment_id=cur.lastrowid, status="active"), 201

    @app.post("/api/drip-enrollments/<int:enrollment_id>/<action>")
    def control_drip_enrollment(enrollment_id, action):
        denied = require_user()
        if denied:
            return denied
        if action not in {"pause", "resume", "stop", "reply"}:
            return jsonify(error="Invalid action"), 400
        status = {"pause": "paused", "resume": "active", "stop": "stopped", "reply": "replied"}[action]
        workspace_id, _ = scope()
        now = _now()
        with connect() as conn:
            row = conn.execute(
                "select campaign_id from drip_enrollments where id=? and workspace_id=?",
                (enrollment_id, workspace_id),
            ).fetchone()
            if not row:
                return jsonify(error="Enrollment not found"), 404
            conn.execute(
                "update drip_enrollments set status=?,stop_reason=?,updated_at=? where id=? and workspace_id=?",
                (status, "reply received" if action == "reply" else action, now, enrollment_id, workspace_id),
            )
            conn.execute(
                "insert into drip_events(workspace_id,campaign_id,enrollment_id,event_type,details,created_at) values(?,?,?,?,?,?)",
                (workspace_id, row["campaign_id"], enrollment_id, f"enrollment_{action}", "", now),
            )
        return jsonify(ok=True, status=status)

    @app.get("/api/drip-campaigns/due")
    def due_drip_messages():
        """Return reviewable messages due now. This endpoint never sends them."""
        denied = require_user()
        if denied:
            return denied
        workspace_id, _ = scope()
        now = _now()
        with connect() as conn:
            rows = conn.execute(
                """select e.id enrollment_id,e.prospect_name,e.email,e.phone,e.email_consent,e.sms_consent,
                          c.id campaign_id,c.name campaign_name,c.quiet_start,c.quiet_end,
                          s.id step_id,s.step_order,s.channel,s.subject,s.body,s.delay_days
                   from drip_enrollments e
                   join drip_campaigns c on c.id=e.campaign_id and c.workspace_id=e.workspace_id
                   join drip_campaign_steps s on s.campaign_id=e.campaign_id and s.step_order=e.current_step+1
                   where e.workspace_id=? and e.status='active' and c.status='approved' and e.next_run_at<=?
                   order by e.next_run_at asc limit 100""",
                (workspace_id, now),
            ).fetchall()
        return jsonify(items=[dict(row) for row in rows], sending_enabled=False, approval_required=True)

    @app.post("/api/drip-suppressions")
    def add_drip_suppression():
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        channel = (data.get("channel") or "").lower().strip()
        destination = (data.get("destination") or "").strip()[:254]
        if channel not in {"email", "sms"} or not destination:
            return jsonify(error="Valid channel and destination are required"), 400
        workspace_id, _ = scope()
        with connect() as conn:
            conn.execute(
                "insert or replace into drip_suppressions(workspace_id,channel,destination,reason,created_at) values(?,?,?,?,?)",
                (workspace_id, channel, destination, (data.get("reason") or "unsubscribe")[:120], _now()),
            )
            if channel == "email":
                conn.execute("update drip_enrollments set status='stopped',stop_reason='email suppressed',updated_at=? where workspace_id=? and email=?", (_now(), workspace_id, destination))
            else:
                conn.execute("update drip_enrollments set status='stopped',stop_reason='sms suppressed',updated_at=? where workspace_id=? and phone=?", (_now(), workspace_id, destination))
        return jsonify(ok=True), 201

    @app.get("/outreach/campaigns")
    def drip_campaign_page():
        denied = require_user()
        if denied:
            return denied
        return Response(CAMPAIGN_HTML, mimetype="text/html")

    @app.after_request
    def inject_campaign_navigation(response):
        if not getattr(g, "user_id", None) or response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-drip-nav" in body or "</body>" not in body.lower():
            return response
        script = """<script id='brokerbeacon-drip-nav'>(function(){function add(){const nav=document.querySelector('.bb-legacy-list')||document.querySelector('aside nav')||document.querySelector('aside');if(!nav||document.getElementById('drip-campaigns-button'))return;const b=document.createElement('button');b.id='drip-campaigns-button';b.type='button';b.textContent='Drip Campaigns';b.title='Build approved email and text follow-up sequences.';b.onclick=()=>location.href='/outreach/campaigns';b.dataset.bbWorkspace='outreach';nav.appendChild(b)}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add()})();</script>"""
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


CAMPAIGN_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>BrokerBeacon Drip Campaigns</title><style>
body{margin:0;background:#f4f8fc;color:#17283d;font:14px Inter,Arial,sans-serif}.wrap{max-width:1100px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center}.card{background:white;border:1px solid #dce6f0;border-radius:16px;padding:18px;margin-top:14px;box-shadow:0 10px 30px #17324d0d}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}input,textarea,select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd8e5;border-radius:9px;margin-top:5px}textarea{min-height:90px}.btn{border:0;border-radius:10px;padding:10px 14px;cursor:pointer;background:#174ea6;color:white}.ghost{background:#eaf1fb;color:#174ea6}.step{padding:12px;border:1px solid #dce6f0;border-radius:12px;margin-top:9px}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#edf5ff;color:#174ea6;font-size:11px}.notice{padding:12px;border-radius:12px;background:#fff7db;border:1px solid #f0d77a}.campaign{display:flex;justify-content:space-between;gap:12px;padding:13px 0;border-bottom:1px solid #e6edf4}.campaign:last-child{border:0}@media(max-width:760px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><div class='wrap'><div class='top'><div><div class='pill'>Outreach</div><h1>Drip Campaigns</h1><p>Create approved email and SMS sequences. Automatic delivery remains off until a sending provider and compliance registration are configured.</p></div><button class='btn ghost' onclick="location.href='/'">Back to BrokerBeacon</button></div><div class='notice'><b>Safety defaults:</b> first-message approval, consent required, stop-on-reply, quiet hours, and suppression checks.</div><div class='grid'><div class='card'><h2>Campaign builder</h2><label>Name<input id='name' placeholder='New broker welcome sequence'></label><label>Description<textarea id='description' placeholder='What this campaign is for'></textarea></label><div id='steps'></div><button class='btn ghost' onclick='addStep()'>Add step</button> <button class='btn' onclick='saveCampaign()'>Save draft</button><div id='message'></div></div><div class='card'><h2>Your campaigns</h2><div id='campaigns'>Loading…</div></div></div><div class='card'><h2>How activation works</h2><p>1. Save the sequence as a draft. 2. Review and approve it. 3. Enroll only prospects with documented channel consent. 4. Due messages enter a review queue. Sending remains disabled in this foundation release.</p><p style='opacity:.65'>For Aiden — built with persistence.</p></div></div><script>
let stepCount=0;function addStep(){stepCount++;const d=document.createElement('div');d.className='step';d.innerHTML=`<b>Step ${stepCount}</b><label>Channel<select class='channel'><option value='email'>Email</option><option value='sms'>Text message</option></select></label><label>Wait days<input class='delay' type='number' min='0' max='365' value='${stepCount===1?0:3}'></label><label>Email subject<input class='subject' placeholder='Optional for SMS'></label><label>Message<textarea class='body' placeholder='Hi {{first_name}}, ...'></textarea></label>`;document.getElementById('steps').appendChild(d)}
async function load(){const r=await fetch('/api/drip-campaigns'),j=await r.json();document.getElementById('campaigns').innerHTML=(j.items||[]).map(c=>`<div class='campaign'><div><b>${esc(c.name)}</b><div>${c.step_count} steps · ${c.enrollment_count} enrolled</div><span class='pill'>${esc(c.status)}</span></div>${c.status!=='approved'?`<button class='btn' onclick='approve(${c.id})'>Approve</button>`:''}</div>`).join('')||'No campaigns yet.'}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}async function saveCampaign(){const steps=[...document.querySelectorAll('.step')].map(s=>({channel:s.querySelector('.channel').value,delay_days:Number(s.querySelector('.delay').value||0),subject:s.querySelector('.subject').value,body:s.querySelector('.body').value}));const r=await fetch('/api/drip-campaigns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('name').value,description:document.getElementById('description').value,steps})}),j=await r.json();document.getElementById('message').textContent=r.ok?'Draft saved. Review and approve it before enrollment.':j.error||'Unable to save';if(r.ok)load()}async function approve(id){const r=await fetch('/api/drip-campaigns/'+id+'/approve',{method:'POST'});if(r.ok)load()}addStep();load();
</script></body></html>"""
