"""PartnerBeacon Facebook home-purchase leads.

Generates inbound purchase leads from Facebook Lead Ads, tracks each customer
through a simple pipeline, and prepares first-touch plus drip outreach.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Response, g, jsonify, request

STAGES = [
    "New Lead", "Contacted", "Qualified", "Pre-Approved", "House Hunting",
    "Under Contract", "Clear to Close", "Funded", "Nurture", "Dead",
]
STOP_STAGES = {"Funded", "Dead"}
PURCHASE_DRIPS = {
    "facebook_purchase_7day": {
        "name": "New Facebook Purchase Lead (7 days)",
        "steps": [
            (0, "sms", "", "Hi {first_name}, this is {lo_name} with {company}. Got your home-purchase request. I can run numbers and map next steps. Good time for a 10-min call today? Reply STOP to opt out."),
            (0, "email", "Your home purchase next step", "Hi {first_name},\n\nThanks for requesting help buying a home in {market}. I received your Facebook form and will treat this as a purchase file, not a refinance pitch.\n\nReply with a good time today or tomorrow and I will walk through payment range, down payment options, and what we need for a pre-approval letter.\n\n{lo_name}\n{company}\n{lo_phone}"),
            (2, "sms", "", "Hi {first_name}, {lo_name} again. Still happy to quote a purchase payment range for {market}. Want me to send a short checklist? Reply STOP to opt out."),
            (5, "email", "Pre-approval checklist for your purchase", "Hi {first_name},\n\nIf you are still shopping or getting ready to write an offer, a current pre-approval letter is usually what listing agents want to see.\n\nTypical next items: photo ID, last 30 days of pay, last two years of W-2s or returns if self-employed, and two months of asset statements.\n\nI can start the file as soon as you say go.\n\n{lo_name}\n{company}"),
        ],
    },
    "preapproved_nurture_30": {
        "name": "Pre-Approved Nurture (30 days)",
        "steps": [
            (0, "email", "You are cleared to shop", "Hi {first_name},\n\nYour purchase pre-approval is active. Use the letter with your agent when you tour or write. If the purchase price or down payment changes, text me before you submit so we can refresh the letter the same day.\n\n{lo_name}"),
            (7, "sms", "", "Hi {first_name}, any houses you want a payment check on? Send address or list price and I will run it. Reply STOP to opt out."),
            (21, "email", "Still shopping? I can refresh your purchase letter", "Hi {first_name},\n\nJust checking in on the house hunt. If rates or the target price moved, I can issue an updated letter without starting over.\n\n{lo_name}"),
        ],
    },
    "warm_90": {
        "name": "Dead-but-warm (90 days)",
        "steps": [
            (0, "email", "Whenever you are ready to buy", "Hi {first_name},\n\nNo pressure. If the purchase timeline slipped, I will keep your file quiet and ready. When you want updated payments, reply to this email.\n\n{lo_name}"),
            (30, "email", "Market check-in for your next purchase", "Hi {first_name},\n\nQuick check-in only. If you want a fresh payment range for {market}, I can send one this week.\n\n{lo_name}"),
            (90, "sms", "", "Hi {first_name}, {lo_name}. Still here if a purchase comes back on the calendar. Reply STOP to opt out."),
        ],
    },
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _key(*parts: str) -> str:
    raw = "|".join((p or "").strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _clean_phone(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _score_lead(field_map: dict) -> tuple:
    score = 40
    reasons = []
    timeframe = (field_map.get("timeframe") or field_map.get("when_do_you_want_to_buy") or "").lower()
    if any(token in timeframe for token in ("0-3", "immediately", "now", "this month", "30")):
        score += 25
        reasons.append("near-term timeframe")
    elif any(token in timeframe for token in ("3-6", "soon", "this year")):
        score += 12
        reasons.append("mid-term timeframe")
    status = (field_map.get("pre_approval_status") or field_map.get("are_you_pre_approved") or "").lower()
    if "yes" in status:
        score += 10
        reasons.append("already exploring pre-approval")
    if field_map.get("price_range") or field_map.get("purchase_price_range"):
        score += 8
        reasons.append("named a price range")
    if field_map.get("zip") or field_map.get("zip_code"):
        score += 7
        reasons.append("local zip provided")
    return min(score, 99), ", ".join(reasons) or "new Facebook purchase inquiry"


def _graph_get(url: str, timeout: int = 15) -> dict:
    req = Request(url, headers={"User-Agent": "PartnerBeacon/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _field_map(lead: dict) -> dict:
    mapping = {}
    for item in lead.get("field_data") or []:
        name = str(item.get("name") or "").strip().lower()
        values = item.get("values") or []
        mapping[name] = (values[0] if values else "") or ""
    return mapping


def install_facebook_purchase_leads(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.executescript(
            """
            create table if not exists fb_ad_connections(
                id integer primary key, workspace_id integer not null default 1,
                page_id text default '', ad_account_id text default '', page_name text default '', created_at text not null
            );
            create table if not exists fb_campaigns(
                id integer primary key, workspace_id integer not null default 1, name text not null,
                market text default 'Charlotte, NC', offer text default 'Purchase pre-approval',
                partner_name text default '', daily_budget_cents integer not null default 2500,
                status text not null default 'draft', facebook_campaign_id text default '',
                facebook_form_id text default '', landing_path text default '/leads/facebook/apply',
                created_at text not null, updated_at text not null
            );
            create table if not exists fb_purchase_leads(
                id integer primary key, workspace_id integer not null default 1, campaign_id integer,
                facebook_lead_id text default '', facebook_form_id text default '', facebook_ad_id text default '',
                source text not null default 'Facebook Purchase', first_name text default '', last_name text default '',
                full_name text not null, email text default '', phone text default '', zip text default '',
                market text default '', timeframe text default '', price_range text default '',
                pre_approval_status text default '', first_time_buyer text default '', partner_name text default '',
                assigned_lo text default '', stage text not null default 'New Lead', score integer not null default 40,
                score_reason text default '', email_consent integer not null default 0, sms_consent integer not null default 0,
                raw_json text default '', created_at text not null, updated_at text not null,
                unique(workspace_id, facebook_lead_id)
            );
            create index if not exists idx_fb_leads_stage on fb_purchase_leads(workspace_id, stage, id desc);
            create table if not exists fb_lead_events(
                id integer primary key, workspace_id integer not null default 1, lead_id integer not null,
                actor text default 'system', event_type text not null, channel text default '',
                details text default '', created_at text not null
            );
            create table if not exists fb_outreach_tasks(
                id integer primary key, workspace_id integer not null default 1, lead_id integer not null,
                title text not null, due_at text not null, status text not null default 'open',
                channel text default 'call', created_at text not null
            );
            create table if not exists fb_drip_queue(
                id integer primary key, workspace_id integer not null default 1, lead_id integer not null,
                sequence_key text not null, step_index integer not null, channel text not null,
                subject text default '', body text not null, send_after text not null,
                status text not null default 'queued', created_at text not null
            );
            """
        )

    def workspace_id():
        return int(getattr(g, "workspace_id", 0) or 1)

    def require_user():
        if not getattr(g, "user_id", None):
            return jsonify(error="Authentication required"), 401
        return None

    def add_event(conn, lead_id, event_type, details="", actor="system", channel=""):
        conn.execute(
            "insert into fb_lead_events(workspace_id,lead_id,actor,event_type,channel,details,created_at) values(?,?,?,?,?,?,?)",
            (workspace_id(), lead_id, actor, event_type, channel, details[:2000], _now()),
        )

    def create_task(conn, lead_id, title, minutes=5, channel="call"):
        due = (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        conn.execute(
            "insert into fb_outreach_tasks(workspace_id,lead_id,title,due_at,status,channel,created_at) values(?,?,?,?,?,?,?)",
            (workspace_id(), lead_id, title[:180], due, "open", channel, _now()),
        )

    def enroll_drip(conn, lead, sequence_key="facebook_purchase_7day"):
        sequence = PURCHASE_DRIPS[sequence_key]
        first = (lead["first_name"] or lead["full_name"].split(" ")[0] or "there").title()
        tokens = {
            "first_name": first,
            "lo_name": os.environ.get("PB_LO_NAME", "your loan officer"),
            "company": os.environ.get("PB_COMPANY_NAME", "PartnerBeacon Lending"),
            "lo_phone": os.environ.get("PB_LO_PHONE", ""),
            "market": lead["market"] or "your area",
        }
        now = datetime.now()
        for index, (delay_days, channel, subject, body) in enumerate(sequence["steps"]):
            send_after = (now + timedelta(days=delay_days)).isoformat(timespec="seconds")
            conn.execute(
                "insert into fb_drip_queue(workspace_id,lead_id,sequence_key,step_index,channel,subject,body,send_after,status,created_at) values(?,?,?,?,?,?,?,?,?,?)",
                (workspace_id(), lead["id"], sequence_key, index, channel, subject.format(**tokens), body.format(**tokens), send_after, "queued", _now()),
            )

    def upsert_lead(conn, payload, source="Facebook Purchase"):
        facebook_lead_id = (payload.get("facebook_lead_id") or "")[:80]
        email = (payload.get("email") or "").strip().lower()[:254]
        phone = _clean_phone(payload.get("phone") or "")
        first = (payload.get("first_name") or "").strip()[:80]
        last = (payload.get("last_name") or "").strip()[:80]
        full = (payload.get("full_name") or f"{first} {last}").strip()[:180] or "Facebook purchase lead"
        if facebook_lead_id:
            existing = conn.execute(
                "select id from fb_purchase_leads where workspace_id=? and facebook_lead_id=?",
                (workspace_id(), facebook_lead_id),
            ).fetchone()
            if existing:
                return existing["id"], False
        if email or phone:
            existing = conn.execute(
                "select id from fb_purchase_leads where workspace_id=? and ((email<>'' and email=?) or (phone<>'' and phone=?)) order by id desc limit 1",
                (workspace_id(), email, phone),
            ).fetchone()
            if existing:
                return existing["id"], False
        field_map = payload.get("fields") or {}
        score, reason = _score_lead(field_map)
        cur = conn.execute(
            """insert into fb_purchase_leads(
                   workspace_id,campaign_id,facebook_lead_id,facebook_form_id,facebook_ad_id,source,
                   first_name,last_name,full_name,email,phone,zip,market,timeframe,price_range,
                   pre_approval_status,first_time_buyer,partner_name,assigned_lo,stage,score,score_reason,
                   email_consent,sms_consent,raw_json,created_at,updated_at
               ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                workspace_id(), payload.get("campaign_id"), facebook_lead_id,
                (payload.get("facebook_form_id") or "")[:80], (payload.get("facebook_ad_id") or "")[:80], source,
                first, last, full, email, phone,
                (payload.get("zip") or field_map.get("zip_code") or field_map.get("zip") or "")[:12],
                (payload.get("market") or "Charlotte, NC")[:80],
                (payload.get("timeframe") or field_map.get("timeframe") or field_map.get("when_do_you_want_to_buy") or "")[:80],
                (payload.get("price_range") or field_map.get("price_range") or field_map.get("purchase_price_range") or "")[:80],
                (payload.get("pre_approval_status") or field_map.get("pre_approval_status") or "")[:80],
                (payload.get("first_time_buyer") or field_map.get("first_time_buyer") or "")[:40],
                (payload.get("partner_name") or "")[:120], os.environ.get("PB_LO_NAME", "")[:80],
                "New Lead", score, reason,
                1 if payload.get("email_consent") or email else 0,
                1 if payload.get("sms_consent") else 0,
                json.dumps(payload.get("raw") or payload)[:8000], _now(), _now(),
            ),
        )
        lead_id = cur.lastrowid
        lead = conn.execute("select * from fb_purchase_leads where id=?", (lead_id,)).fetchone()
        add_event(conn, lead_id, "lead_created", reason, actor="facebook")
        create_task(conn, lead_id, f"Call {full} within 5 minutes", minutes=5, channel="call")
        enroll_drip(conn, dict(lead))
        return lead_id, True

    def ingest_facebook_leadgen(leadgen_id, form_id="", ad_id=""):
        token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        if not token:
            raise RuntimeError("FACEBOOK_PAGE_ACCESS_TOKEN is not configured")
        fields = "id,created_time,ad_id,form_id,field_data"
        url = f"https://graph.facebook.com/v21.0/{leadgen_id}?{urlencode({'fields': fields, 'access_token': token})}"
        data = _graph_get(url)
        mapping = _field_map(data)
        full_name = mapping.get("full_name") or f"{mapping.get('first_name', '')} {mapping.get('last_name', '')}".strip()
        consent_text = (mapping.get("consent") or mapping.get("i_agree_to_be_contacted") or "").lower()
        payload = {
            "facebook_lead_id": data.get("id") or leadgen_id,
            "facebook_form_id": form_id or data.get("form_id") or "",
            "facebook_ad_id": ad_id or data.get("ad_id") or "",
            "first_name": mapping.get("first_name", ""),
            "last_name": mapping.get("last_name", ""),
            "full_name": full_name,
            "email": mapping.get("email", ""),
            "phone": mapping.get("phone_number") or mapping.get("phone") or "",
            "zip": mapping.get("zip_code") or mapping.get("zip") or "",
            "timeframe": mapping.get("timeframe") or mapping.get("when_do_you_want_to_buy") or "",
            "price_range": mapping.get("price_range") or mapping.get("purchase_price_range") or "",
            "pre_approval_status": mapping.get("pre_approval_status") or mapping.get("are_you_pre_approved") or "",
            "first_time_buyer": mapping.get("first_time_buyer") or "",
            "sms_consent": "yes" in consent_text or "agree" in consent_text or bool(mapping.get("phone_number")),
            "email_consent": bool(mapping.get("email")),
            "fields": mapping,
            "raw": data,
        }
        with connect() as conn:
            return upsert_lead(conn, payload)

    def valid_signature(raw_body):
        secret = os.environ.get("FACEBOOK_APP_SECRET", "")
        header = request.headers.get("X-Hub-Signature-256", "")
        if not secret:
            return True
        if not header.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(header.split("=", 1)[1], expected)

    @app.get("/webhooks/facebook/leads")
    def facebook_webhook_verify():
        verify_token = os.environ.get("FACEBOOK_VERIFY_TOKEN", "")
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        if mode == "subscribe" and verify_token and token == verify_token:
            return Response(challenge, mimetype="text/plain")
        return Response("Verification failed", status=403)

    @app.post("/webhooks/facebook/leads")
    def facebook_webhook_receive():
        raw = request.get_data()
        if not valid_signature(raw):
            return jsonify(error="Invalid signature"), 403
        body = request.get_json(silent=True) or {}
        created = []
        for entry in body.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                leadgen_id = value.get("leadgen_id")
                if not leadgen_id:
                    continue
                try:
                    lead_id, is_new = ingest_facebook_leadgen(str(leadgen_id), form_id=str(value.get("form_id") or ""), ad_id=str(value.get("ad_id") or ""))
                    created.append({"lead_id": lead_id, "new": is_new, "leadgen_id": leadgen_id})
                except Exception as exc:
                    created.append({"leadgen_id": leadgen_id, "error": str(exc)})
        return jsonify(ok=True, results=created)

    @app.post("/leads/facebook/apply")
    def landing_form_submit():
        form = request.form
        consent = form.get("consent") == "yes"
        payload = {
            "facebook_lead_id": f"landing-{_key(form.get('email', ''), form.get('phone', ''), _now())}",
            "first_name": form.get("first_name", ""), "last_name": form.get("last_name", ""),
            "email": form.get("email", ""), "phone": form.get("phone", ""), "zip": form.get("zip", ""),
            "market": form.get("market") or "Charlotte, NC", "timeframe": form.get("timeframe", ""),
            "price_range": form.get("price_range", ""), "pre_approval_status": form.get("pre_approval_status", ""),
            "first_time_buyer": form.get("first_time_buyer", ""), "sms_consent": consent, "email_consent": consent,
            "fields": {k: form.get(k, "") for k in form}, "raw": {k: form.get(k) for k in form},
        }
        if not ((payload["email"] or payload["phone"]) and consent):
            return Response("Consent and a phone or email are required.", status=400)
        with connect() as conn:
            upsert_lead(conn, payload, source="PartnerBeacon Landing")
        return Response(THANKS_HTML, mimetype="text/html")

    @app.get("/leads/facebook/apply")
    def landing_form():
        return Response(LANDING_HTML, mimetype="text/html")

    @app.get("/leads/facebook/apply/thanks")
    def landing_thanks():
        return Response(THANKS_HTML, mimetype="text/html")

    @app.get("/partnerbeacon/leads")
    def leads_workspace():
        denied = require_user()
        if denied:
            return denied
        return Response(WORKSPACE_HTML, mimetype="text/html")

    @app.get("/api/partnerbeacon/leads")
    def api_list_leads():
        denied = require_user()
        if denied:
            return denied
        stage = (request.args.get("stage") or "").strip()
        sql = "select * from fb_purchase_leads where workspace_id=?"
        args = [workspace_id()]
        if stage:
            sql += " and stage=?"
            args.append(stage)
        sql += " order by id desc limit 200"
        with connect() as conn:
            rows = conn.execute(sql, args).fetchall()
            open_tasks = conn.execute(
                "select t.*, l.full_name from fb_outreach_tasks t join fb_purchase_leads l on l.id=t.lead_id where t.workspace_id=? and t.status='open' order by t.due_at asc limit 20",
                (workspace_id(),),
            ).fetchall()
        return jsonify(items=[dict(r) for r in rows], tasks=[dict(t) for t in open_tasks], stages=STAGES)

    @app.get("/api/partnerbeacon/leads/<int:lead_id>")
    def api_lead_detail(lead_id):
        denied = require_user()
        if denied:
            return denied
        with connect() as conn:
            lead = conn.execute("select * from fb_purchase_leads where id=? and workspace_id=?", (lead_id, workspace_id())).fetchone()
            if not lead:
                return jsonify(error="Lead not found"), 404
            events = conn.execute("select * from fb_lead_events where lead_id=? order by id desc limit 50", (lead_id,)).fetchall()
            tasks = conn.execute("select * from fb_outreach_tasks where lead_id=? order by id desc", (lead_id,)).fetchall()
            drips = conn.execute("select * from fb_drip_queue where lead_id=? order by step_index", (lead_id,)).fetchall()
        return jsonify(item=dict(lead), events=[dict(e) for e in events], tasks=[dict(t) for t in tasks], drips=[dict(d) for d in drips], drafts=first_touch_drafts(dict(lead)))

    @app.post("/api/partnerbeacon/leads/<int:lead_id>/stage")
    def api_update_stage(lead_id):
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        stage = (data.get("stage") or "").strip()
        if stage not in STAGES:
            return jsonify(error="Invalid stage"), 400
        with connect() as conn:
            cur = conn.execute("update fb_purchase_leads set stage=?,updated_at=? where id=? and workspace_id=?", (stage, _now(), lead_id, workspace_id()))
            if not cur.rowcount:
                return jsonify(error="Lead not found"), 404
            add_event(conn, lead_id, "stage_changed", stage, actor="user")
            if stage in STOP_STAGES:
                conn.execute("update fb_drip_queue set status='stopped' where lead_id=? and status='queued'", (lead_id,))
            elif stage == "Pre-Approved":
                enroll_drip(conn, dict(conn.execute("select * from fb_purchase_leads where id=?", (lead_id,)).fetchone()), "preapproved_nurture_30")
            elif stage == "Nurture":
                enroll_drip(conn, dict(conn.execute("select * from fb_purchase_leads where id=?", (lead_id,)).fetchone()), "warm_90")
        return jsonify(ok=True, stage=stage)

    @app.post("/api/partnerbeacon/leads/<int:lead_id>/log")
    def api_log_interaction(lead_id):
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        channel = (data.get("channel") or "note").strip()[:30]
        details = (data.get("details") or data.get("note") or "").strip()[:2000]
        if not details:
            return jsonify(error="Note is required"), 400
        with connect() as conn:
            lead = conn.execute("select id,stage from fb_purchase_leads where id=? and workspace_id=?", (lead_id, workspace_id())).fetchone()
            if not lead:
                return jsonify(error="Lead not found"), 404
            add_event(conn, lead_id, "interaction", details, actor="user", channel=channel)
            if lead["stage"] == "New Lead":
                conn.execute("update fb_purchase_leads set stage='Contacted',updated_at=? where id=?", (_now(), lead_id))
            conn.execute("update fb_outreach_tasks set status='done' where lead_id=? and status='open' and channel=?", (lead_id, channel))
        return jsonify(ok=True)

    @app.post("/api/partnerbeacon/leads/manual")
    def api_manual_lead():
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        if not (data.get("full_name") or data.get("first_name") or data.get("email") or data.get("phone")):
            return jsonify(error="Name, email, or phone is required"), 400
        with connect() as conn:
            lead_id, created = upsert_lead(conn, data, source=data.get("source") or "Manual")
        return jsonify(ok=True, lead_id=lead_id, created=created), 201 if created else 200

    @app.post("/api/partnerbeacon/campaigns")
    def api_create_campaign():
        denied = require_user()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()[:120]
        if not name:
            return jsonify(error="Campaign name is required"), 400
        now = _now()
        with connect() as conn:
            cur = conn.execute(
                "insert into fb_campaigns(workspace_id,name,market,offer,partner_name,daily_budget_cents,status,created_at,updated_at) values(?,?,?,?,?,?,?,?,?)",
                (workspace_id(), name, (data.get("market") or "Charlotte, NC")[:80], (data.get("offer") or "Purchase pre-approval")[:120], (data.get("partner_name") or "")[:120], max(500, min(int(data.get("daily_budget_cents") or 2500), 100000)), "draft", now, now),
            )
        return jsonify(ok=True, campaign_id=cur.lastrowid, status="draft"), 201

    @app.get("/api/partnerbeacon/campaigns")
    def api_list_campaigns():
        denied = require_user()
        if denied:
            return denied
        with connect() as conn:
            rows = conn.execute("select * from fb_campaigns where workspace_id=? order by id desc", (workspace_id(),)).fetchall()
        return jsonify(items=[dict(r) for r in rows])

    @app.get("/api/partnerbeacon/ash")
    def api_ash_summary():
        denied = require_user()
        if denied:
            return denied
        lead_id = request.args.get("lead_id", type=int)
        if not lead_id:
            return jsonify(error="lead_id is required"), 400
        with connect() as conn:
            lead = conn.execute("select * from fb_purchase_leads where id=? and workspace_id=?", (lead_id, workspace_id())).fetchone()
        if not lead:
            return jsonify(error="Lead not found"), 404
        item = dict(lead)
        drafts = first_touch_drafts(item)
        summary = f"{item['full_name']} is a Facebook purchase lead in {item['market'] or 'an unspecified market'}. Stage: {item['stage']}. Score {item['score']} ({item['score_reason']}). Timeframe: {item['timeframe'] or 'unknown'}. Price range: {item['price_range'] or 'not given'}."
        next_action = "Call now and confirm purchase timeline plus consent to text."
        if item["stage"] == "Contacted":
            next_action = "Qualify income, down payment, and whether they have an agent."
        elif item["stage"] == "Pre-Approved":
            next_action = "Send the letter and introduce a partner realtor only after the buyer consents."
        return jsonify(summary=summary, next_action=next_action, drafts=drafts, realtor_intro=realtor_intro(item))

    @app.get("/api/partnerbeacon/today")
    def api_today():
        denied = require_user()
        if denied:
            return denied
        with connect() as conn:
            new_leads = conn.execute("select * from fb_purchase_leads where workspace_id=? and stage='New Lead' order by id desc limit 10", (workspace_id(),)).fetchall()
            tasks = conn.execute("select t.*, l.full_name, l.phone, l.email from fb_outreach_tasks t join fb_purchase_leads l on l.id=t.lead_id where t.workspace_id=? and t.status='open' order by t.due_at asc limit 10", (workspace_id(),)).fetchall()
            due_drips = conn.execute("select d.*, l.full_name from fb_drip_queue d join fb_purchase_leads l on l.id=d.lead_id where d.workspace_id=? and d.status='queued' and d.send_after<=? order by d.send_after limit 10", (workspace_id(), _now())).fetchall()
        return jsonify(new_leads=[dict(r) for r in new_leads], tasks=[dict(r) for r in tasks], due_drips=[dict(r) for r in due_drips])

    @app.after_request
    def inject_partnerbeacon_nav(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "partnerbeacon-fb-nav" in body or "</body>" not in body.lower():
            return response
        script = "<script id='partnerbeacon-fb-nav'>(function(){function add(){const nav=document.querySelector('.bb-legacy-list')||document.querySelector('aside nav')||document.querySelector('aside');if(!nav||document.getElementById('partnerbeacon-leads-button'))return;const b=document.createElement('button');b.id='partnerbeacon-leads-button';b.type='button';b.textContent='Purchase Leads';b.title='Facebook home-purchase leads, tracking, and outreach.';b.onclick=()=>location.href='/partnerbeacon/leads';nav.appendChild(b)}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add()})();</script>"
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


def first_touch_drafts(lead):
    first = (lead.get("first_name") or (lead.get("full_name") or "there").split(" ")[0]).title()
    lo = os.environ.get("PB_LO_NAME", "your loan officer")
    company = os.environ.get("PB_COMPANY_NAME", "PartnerBeacon Lending")
    market = lead.get("market") or "your area"
    return {
        "sms": f"Hi {first}, this is {lo} with {company}. I received your home-purchase request. I can outline payment range and pre-approval steps for {market}. Open to a 10-minute call today? Reply STOP to opt out.",
        "email_subject": f"Next step on your {market} home purchase",
        "email": f"Hi {first},\n\nThanks for requesting help buying a home. This is not a refinance pitch. I can review a purchase payment range for {market}, explain down-payment options, and tell you exactly what is needed for a pre-approval letter.\n\nReply with a time that works today or tomorrow.\n\n{lo}\n{company}",
        "call": f"Hi {first}, this is {lo} with {company}. You asked about buying a home in {market}. I just need your timeframe, target price range, and whether you already have an agent. Then I can tell you what a purchase pre-approval would take. Do you have two minutes?",
    }


def realtor_intro(lead):
    first = (lead.get("first_name") or "the buyer").title()
    partner = lead.get("partner_name") or "our realtor partner"
    return f"Hi {partner}, {first} asked about buying in {lead.get('market') or 'the area'} and consented to an introduction. Timeframe: {lead.get('timeframe') or 'not specified'}. I am handling financing. Can you take a quick intro call with us?"


LANDING_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>See your purchase payment range</title>
<style>body{margin:0;background:#0c1730;color:#f6f8ff;font:16px Inter,Arial,sans-serif}.wrap{max-width:720px;margin:auto;padding:36px 20px}.card{background:#132445;border:1px solid #ffffff22;border-radius:22px;padding:28px}label{display:block;margin:12px 0 6px;font-size:13px;color:#9eb0cc}input,select{width:100%;box-sizing:border-box;padding:12px;border-radius:10px;border:1px solid #ffffff25;background:#0c1730;color:white}button{margin-top:18px;width:100%;padding:14px;border:0;border-radius:12px;background:linear-gradient(135deg,#7c5cff,#438df2);color:white;font-weight:800;cursor:pointer}.fine{font-size:12px;color:#8ea0bb;line-height:1.5}</style></head><body><div class='wrap'>
<div class='card'><div style='letter-spacing:.14em;font-size:11px;color:#76e6ff;font-weight:800'>PARTNERBEACON</div>
<h1>Get a purchase payment range for Charlotte homes</h1>
<p>Not a refinance pitch. Tell us where you want to buy and we will outline the next step toward a pre-approval letter.</p>
<form method='post' action='/leads/facebook/apply'>
<label>First name<input name='first_name' required></label>
<label>Last name<input name='last_name' required></label>
<label>Email<input name='email' type='email'></label>
<label>Mobile phone<input name='phone' required></label>
<label>ZIP code<input name='zip' maxlength='10'></label>
<label>When do you want to buy?<select name='timeframe'><option>0-3 months</option><option>3-6 months</option><option>6-12 months</option><option>Just researching</option></select></label>
<label>Purchase price range<select name='price_range'><option>Under $300k</option><option>$300k-$450k</option><option>$450k-$650k</option><option>$650k+</option></select></label>
<label>First-time buyer?<select name='first_time_buyer'><option>Yes</option><option>No</option></select></label>
<label>Already pre-approved?<select name='pre_approval_status'><option>No</option><option>Yes, but it may be expired</option><option>Working with another lender</option></select></label>
<label><input name='consent' type='checkbox' value='yes' required style='width:auto'> I agree to be contacted by phone, text, or email about a home purchase. Message frequency varies. Reply STOP to opt out. Consent is not required to buy.</label>
<button type='submit'>See my next step</button>
<p class='fine'>Housing opportunities are available without regard to race, color, religion, sex, handicap, familial status, or national origin. This is a mortgage inquiry, not a commitment to lend. Equal Housing Lender.</p>
</form></div></div></body></html>"""

THANKS_HTML = """<!doctype html><html><head><meta charset='utf-8'><title>Request received</title></head>
<body style='font-family:Inter,Arial;background:#0c1730;color:white;padding:40px'><h1>We have your purchase request.</h1><p>A loan officer will reach out shortly.</p></body></html>"""

WORKSPACE_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>PartnerBeacon Purchase Leads</title>
<style>body{margin:0;background:#f4f8fc;color:#17283d;font:14px Inter,Arial,sans-serif}.wrap{max-width:1180px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}.card{background:white;border:1px solid #dce6f0;border-radius:16px;padding:16px;margin-top:12px}.lead{padding:12px 0;border-bottom:1px solid #e6edf4;cursor:pointer}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:#edf5ff;color:#174ea6;font-size:11px}.btn{border:0;border-radius:10px;padding:8px 12px;background:#174ea6;color:white;cursor:pointer}.ghost{background:#eaf1fb;color:#174ea6}textarea{width:100%;min-height:70px}@media(max-width:860px){.grid{grid-template-columns:1fr}}</style></head><body><div class='wrap'>
<div class='pill'>PartnerBeacon</div><h1>Home purchase leads</h1>
<p>Facebook + landing-page buyers, tracked from first click through funded.</p>
<div class='grid'><div><div class='card'><b>Today</b><div id='today'>Loading…</div></div><div class='card'><b>Pipeline</b><div id='leads'>Loading…</div></div></div>
<div><div class='card' id='detail'><h2>Select a lead</h2><p>Call, text, and stage changes live here.</p></div></div></div>
<script>
async function load(){const t=await (await fetch('/api/partnerbeacon/today')).json();document.getElementById('today').innerHTML=`<div>${(t.new_leads||[]).length} new · ${(t.tasks||[]).length} open tasks · ${(t.due_drips||[]).length} due drip items</div>`+(t.tasks||[]).map(x=>`<div class='lead'><b>${esc(x.full_name)}</b> — ${esc(x.title)} <span class='pill'>${esc(x.due_at)}</span></div>`).join('');const l=await (await fetch('/api/partnerbeacon/leads')).json();document.getElementById('leads').innerHTML=(l.items||[]).map(x=>`<div class='lead' onclick='openLead(${x.id})'><b>${esc(x.full_name)}</b><div>${esc(x.phone||x.email)} · ${esc(x.timeframe)}</div><span class='pill'>${esc(x.stage)} · ${x.score}</span></div>`).join('')||'No purchase leads yet.';}
async function openLead(id){const j=await (await fetch('/api/partnerbeacon/leads/'+id)).json();const a=await (await fetch('/api/partnerbeacon/ash?lead_id='+id)).json();const x=j.item;const d=j.drafts||{};document.getElementById('detail').innerHTML=`<h2>${esc(x.full_name)}</h2><div class='pill'>${esc(x.stage)}</div> <div class='pill'>Score ${x.score}</div><p>${esc(a.summary||'')}</p><p><b>Next:</b> ${esc(a.next_action||'')}</p><p>${esc(x.phone)} · ${esc(x.email)} · ${esc(x.zip)}</p><label>Stage <select id='stage'>${(await fetch('/api/partnerbeacon/leads').then(r=>r.json())).stages.map(s=>`<option ${s===x.stage?'selected':''}>${s}</option>`).join('')}</select></label><p><button class='btn' onclick='setStage(${x.id})'>Update stage</button></p><h3>First-touch drafts</h3><p><b>Text</b><br>${esc(d.sms)}</p><p><b>Call</b><br>${esc(d.call)}</p><p><b>Email</b><br>${esc(d.email_subject)}<br>${esc(d.email)}</p><textarea id='note' placeholder='Log the call or text'></textarea><p><button class='btn' onclick='logIt(${x.id},"call")'>Log call</button> <button class='btn ghost' onclick='logIt(${x.id},"sms")'>Log text</button></p>`;}
async function setStage(id){await fetch('/api/partnerbeacon/leads/'+id+'/stage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage:document.getElementById('stage').value})});openLead(id);load();}
async function logIt(id,channel){await fetch('/api/partnerbeacon/leads/'+id+'/log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel,details:document.getElementById('note').value||'Contacted'})});openLead(id);load();}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}load();
</script></body></html>"""
