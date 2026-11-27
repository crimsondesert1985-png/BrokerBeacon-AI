"""Workspace-scoped call queue for live wholesale AEs."""
import io
import json
import os
import operator
import re
import time
import uuid
import wave
from bisect import bisect_left, bisect_right
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import wraps
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from flask import Blueprint, Response, abort, current_app, g, jsonify, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from twilio.http.http_client import TwilioHttpClient
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


bp = Blueprint("priority_dialer", __name__)
PREFIX = "/api/priority-dialer"
WEIGHTS = {"units": 25, "volume": 20, "relationship": 25, "follow_up": 30}
FIELDS = ("first_name", "last_name", "office_number", "cell_number", "email",
          "broker_name", "units", "volume")
OUTCOMES = ("Connected", "Left voicemail", "No answer", "Busy", "Failed",
            "Wrong number", "Do not call", "Interested", "Meeting scheduled", "Not interested")
MEANINGFUL = {"Connected", "Interested", "Positive response", "Meeting scheduled", "Application started", "Not interested"}
TERMINAL = {"completed", "busy", "no-answer", "failed", "canceled"}
LEASE_SECONDS = 20
SCHEMA = """
create table if not exists dialer_weights(component text primary key, weight integer not null);
create table if not exists dialer_phone_policy(
    number text primary key, suppressed integer not null default 0,
    voicemail_consent integer not null default 0, evidence text not null default '',
    updated_by integer not null, updated_at text not null
);
create table if not exists dialer_phone_policy_history(
    id integer primary key, number text not null, action text not null, evidence text not null,
    actor_id integer not null, recorded_at text not null
);
create table if not exists dialer_clips(
    id text primary key, user_id integer not null, name text not null,
    audio blob not null, seconds real not null, created_at text not null
);
create table if not exists dialer_sessions(
    id text primary key, user_id integer not null, state text not null default 'paused',
    leg_sid text not null default '', conference_sid text not null default '',
    lease_until real not null default 0, clip_id text references dialer_clips(id),
    voicemail_mode text not null, created_at text not null, filters text not null
);
create unique index if not exists dialer_open_session on dialer_sessions(user_id) where state <> 'ended';
create table if not exists dialer_items(
    session_id text not null references dialer_sessions(id), position integer not null,
    contact_id integer not null, number text not null, snapshot text not null,
    state text not null default 'pending', skip_reason text not null default '',
    primary key(session_id, position)
);
create table if not exists dialer_attempts(
    id text primary key, session_id text not null, position integer not null,
    provider_sid text not null default '', status text not null default 'starting',
    last_poll real not null default 0,
    detected text not null default '', armed integer not null default 0,
    playback_started integer not null default 0, playback_complete integer not null default 0,
    outcome text not null default '', notes text not null default '', follow_up_date text not null default '',
    sales_action_id integer, memory_id integer, created_at text not null,
    unique(session_id, position),
    foreign key(session_id, position) references dialer_items(session_id, position)
);
create unique index if not exists dialer_provider_sid on dialer_attempts(provider_sid) where provider_sid <> '';
create index if not exists dialer_contact_history on dialer_items(contact_id, session_id);
"""


def config(name):
    return os.environ.get(name, "").strip()


def public_origin():
    value = config("DIALER_PUBLIC_URL").rstrip("/")
    parts = urlsplit(value)
    return value if parts.scheme == "https" and parts.hostname and not (
        parts.path or parts.query or parts.fragment or parts.username
    ) else ""


def configured():
    return config("DIALER_ENABLED").lower() == "true" and bool(public_origin()) and all(config(key) for key in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
        "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_DIALER_APP_SID",
    ))


def client():
    return Client(config("TWILIO_ACCOUNT_SID"), config("TWILIO_AUTH_TOKEN"), http_client=TwilioHttpClient(timeout=12))


def callbacks(workspace, path):
    return f"{public_origin()}/dialer/voice/{workspace}/{path}"


def install_priority_dialer(app, db, now):
    app.extensions["priority_dialer"] = {"db": db, "now": now}
    app.register_blueprint(bp)


def now():
    return current_app.extensions["priority_dialer"]["now"]()


@contextmanager
def database(write=False):
    connection = current_app.extensions["priority_dialer"]["db"]()
    try:
        if not connection.execute(
            "select 1 from sqlite_master where type='index' and name='dialer_contact_history'"
        ).fetchone():
            connection.executescript(SCHEMA)
        with connection:
            if write:
                connection.execute("begin immediate")
            yield connection
    finally:
        connection.close()


def require_ae(view):
    @wraps(view)
    def checked(*args, **kwargs):
        if request.cookies.get("bb_demo") == "1" or g.get("membership_role") not in {"AE", "Manager", "Owner"}:
            return jsonify(error="AE workspace access required"), 403
        if request.method in {"POST", "PUT"} and request.headers.get("X-BrokerBeacon-Dialer") != "1":
            return jsonify(error="Dialer request header required"), 403
        return view(*args, **kwargs)
    return checked


def provider_request(view):
    @wraps(view)
    def checked(*args, workspace=None, **kwargs):
        token = config("TWILIO_AUTH_TOKEN")
        url = public_origin() + request.path
        signature = request.headers.get("X-Twilio-Signature", "")
        if not token or not public_origin() or not RequestValidator(token).validate(url, request.form, signature):
            abort(403)
        if request.form.get("AccountSid") != config("TWILIO_ACCOUNT_SID"):
            abort(403)
        if workspace is None:
            identity = re.fullmatch(r"client:bb_(\d+)_(\d+)", request.form.get("From", ""))
            if not identity:
                abort(403)
            workspace = int(identity[1])
        g.workspace_id = workspace
        return view(workspace, *args, **kwargs)
    return checked


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def error(message, status=400):
    return jsonify(error=message), status


def normalize_number(value):
    original = str(value or "").strip()
    if not re.fullmatch(r"[+() 0-9.-]+", original):
        return ""
    digits = re.sub(r"\D", "", original)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits if re.fullmatch(r"1[2-9]\d{2}[2-9]\d{6}", digits) else ""


def follow_up_score(value, today):
    try:
        days = (date.fromisoformat(value[:10]) - today).days
    except (ValueError, TypeError):
        return 0, "unscheduled"
    if days < 0:
        return 100, "overdue"
    if days == 0:
        return 85, "today"
    return (45, "week") if days <= 7 else (0, "later")


def production_window(today):
    end = today.replace(day=1)
    return end.replace(year=end.year - 1).isoformat()[:7], end.isoformat()[:7]


def percentile(value, values):
    if value is None or len(values) <= 1:
        return 50
    return round(100 * (bisect_left(values, value) + bisect_right(values, value) - 1) / (2 * (len(values) - 1)))


def read_weights(c):
    return WEIGHTS | {row["component"]: row["weight"] for row in c.execute("select * from dialer_weights")}


def suppressions(c):
    return {normalize_number(row["destination"]) for row in c.execute(
        "select destination from suppressions where upper(channel) in ('VOICE','PHONE','CALL','ALL')"
    )}


def get_destination(office, cell, preference, blocked):
    numbers = (cell, office) if preference == "cell" else (office, cell)
    return next((number for number in numbers if number and number not in blocked), "")


def rank_contacts(c, options, today=None):
    if today is None:
        try:
            today = datetime.now(ZoneInfo(options.get("timezone") or "UTC")).date()
        except (ValueError, ZoneInfoNotFoundError):
            today = date.today()
    first_month, end_month = production_window(today)
    weights = read_weights(c)
    policies = {row["number"]: dict(row) for row in c.execute("select * from dialer_phone_policy")}
    blocked = suppressions(c) | {number for number, policy in policies.items() if policy["suppressed"]}
    production = defaultdict(list)
    names = defaultdict(list)
    aggregates = c.execute("""
        with snapshots as (
            select *, dense_rank() over (
                partition by source_name, period_month, trim(lo_nmls), lower(trim(lo_name)), lower(trim(company)), purpose
                order by data_as_of desc, import_id desc
            ) snapshot_rank
            from production_records
            where period_month>=? and period_month<? and replace(replace(lower(loan_type),'-',''),' ','')='nonqm'
            and (trim(lo_nmls)<>'' or trim(lo_name)<>'')
        )
        select trim(lo_nmls) nmls, lower(trim(lo_name)) name, lower(trim(company)) company,
               sum(units) units, sum(volume) volume, max(data_as_of) data_as_of, source_name
        from snapshots where snapshot_rank=1
        group by trim(lo_nmls), lower(trim(lo_name)), lower(trim(company)), source_name
    """, (first_month, end_month))
    for row in aggregates:
        row = dict(row)
        if row["nmls"]:
            production[row["nmls"]].append(row)
        if row["name"]:
            names[(row["company"], row["name"])].append(row)

    activity = defaultdict(list)
    for row in c.execute("""
        select i.contact_id, a.outcome, a.notes, a.follow_up_date, a.created_at, a.memory_id,
               m.follow_up_date as memory_due
        from dialer_attempts a join dialer_items i using(session_id, position)
        left join memories m on m.id=a.memory_id
        where a.outcome<>'' order by a.created_at desc, a.sales_action_id desc
    """):
        activity[row["contact_id"]].append(dict(row))
    account_activity = defaultdict(list)
    for row in c.execute("""
        select s.prospect_id,s.outcome,s.notes,s.follow_up_date,s.created_at
        from sales_actions s where coalesce(s.source_view,'') <> 'priority_dialer'
        and s.prospect_id in (select prospect_id from contacts group by prospect_id having count(*)=1)
        order by s.id desc
    """):
        account_activity[row["prospect_id"]].append(dict(row))
    account_due = dict(c.execute("""
        select m.prospect_id, min(m.follow_up_date) from memories m
        where m.note_type not like 'Completed:%' and m.follow_up_date<>''
        and m.prospect_id in (select prospect_id from contacts group by prospect_id having count(*)=1)
        and not exists (select 1 from dialer_attempts a where a.memory_id=m.id)
        group by m.prospect_id
    """))
    rows = []
    source_rows = c.execute("select c.*,coalesce(p.company,'') broker_name from contacts c join prospects p on p.id=c.prospect_id")
    for raw in source_rows:
        row = dict(raw)
        name = (row.get("name") or "").strip().split(maxsplit=1)
        first, last = (name + ["", ""])[:2]
        nmls = (row.get("nmls") or "").strip()
        matches = production[nmls] if nmls else names[(row["broker_name"].lower().strip(), (row.get("name") or "").lower().strip())]
        if not nmls and len({match["nmls"] for match in matches if match["nmls"]}) > 1:
            matches = []
        if matches:
            # Two imports from different providers can describe the same loans.
            source = max(matches, key=lambda match: (match["data_as_of"] or "", match["source_name"]))["source_name"]
            matches = [match for match in matches if match["source_name"] == source]
        units = sum(match["units"] for match in matches) if matches else None
        volume = round(sum(match["volume"] for match in matches), 2) if matches else None
        previous = activity[row["id"]]
        history = sorted(previous + account_activity[row["prospect_id"]], key=lambda item: item["created_at"], reverse=True)
        meaningful = next((item["created_at"] for item in history if item["outcome"] in MEANINGFUL), "")
        try:
            age = (today - date.fromisoformat(meaningful[:10])).days
        except ValueError:
            age = 9999
        relationship = max(0, 100 - max(0, age) * 2) if meaningful else 0
        follow_up = ((previous[0]["memory_due"] or "") if previous else account_due.get(row["prospect_id"], ""))
        urgency, bucket = follow_up_score(follow_up, today)
        office = row.get("phone") or ""
        cell = row.get("mobile") or ""
        office_normalized = normalize_number(office)
        cell_normalized = normalize_number(cell)
        destination = "" if row.get("voice_opt_out") or row.get("roster_status") == "Former / inactive" else get_destination(
            office_normalized, cell_normalized, options.get("phone"), blocked
        )
        rows.append({
            "id": row["id"], "first_name": first, "last_name": last, "email": row.get("email") or "",
            "office_number": office, "cell_number": cell, "broker_name": row["broker_name"],
            "units": units, "volume": volume, "phone": destination, "follow_up": follow_up,
            "follow_up_bucket": bucket, "components": {"relationship": relationship, "follow_up": urgency},
            "source": ", ".join(sorted({match["source_name"] for match in matches})),
            "period": f"{first_month} through {(date.fromisoformat(end_month + '-01') - timedelta(days=1)).isoformat()[:7]}",
            "last_touch": meaningful, "recent": [{k: item[k] for k in ("outcome", "notes", "created_at")} for item in history[:3]],
            "numbers": [{"number": number, "consent": bool(policies.get(number, {}).get("voicemail_consent")),
                         "suppressed": number in blocked} for number in dict.fromkeys((office_normalized, cell_normalized)) if number],
        })
    for field in ("units", "volume"):
        values = sorted(row[field] for row in rows if row[field] is not None)
        for row in rows:
            row["components"][field] = percentile(row[field], values)
    for row in rows:
        row["score"] = round(sum(row["components"][field] * weights[field] for field in weights) / 100, 1)
    query = options.get("search", "").casefold().strip()
    digits = re.sub(r"\D", "", query) if re.fullmatch(r"[+() .0-9-]+", query) else ""
    broker = options.get("broker", "").casefold().strip()
    matched = []
    for row in rows:
        if query and query not in " ".join(str(row[field]) for field in FIELDS[:6]).casefold() and not (
            digits and any(digits in re.sub(r"\D", "", row[field]) for field in ("office_number", "cell_number"))
        ):
            continue
        if broker and broker not in row["broker_name"].casefold():
            continue
        if options.get("follow_up") and row["follow_up_bucket"] != options["follow_up"]:
            continue
        if options.get("relationship") == "warm" and not row["components"]["relationship"]:
            continue
        if options.get("relationship") == "cold" and row["components"]["relationship"]:
            continue
        if options.get("callable") == "yes" and not row["phone"]:
            continue
        if options.get("callable") == "no" and row["phone"]:
            continue
        if any(options.get(key, "") and (row[field] is None or not comparator(row[field], float(options[key])))
               for key, field, comparator in (
                   ("min_units", "units", operator.ge),
                   ("max_units", "units", operator.le),
                   ("min_volume", "volume", operator.ge),
                   ("max_volume", "volume", operator.le),
               )):
            continue
        matched.append(row)
    matched.sort(key=lambda row: (-row["score"], row["follow_up"] or "9999", row["id"]))
    field = options.get("sort")
    if field in FIELDS:
        present = [row for row in matched if row[field] not in (None, "")]
        missing = [row for row in matched if row[field] in (None, "")]
        present.sort(key=lambda row: row[field].casefold() if isinstance(row[field], str) else row[field],
                     reverse=options.get("direction") == "desc")
        matched = present + missing
    return matched, weights


def ordered_queue(rows):
    used = set()
    queue = []
    for row in rows:
        if not row["phone"]:
            continue
        candidates = [row["phone"]] + [item["number"] for item in row["numbers"] if not item["suppressed"]]
        destination = next((number for number in candidates if number not in used), "")
        if destination:
            used.add(destination)
            queue.append(row | {"phone": destination})
    return queue


def options_from(data):
    keys = ("timezone", "search", "broker", "phone", "follow_up", "relationship", "callable", "sort", "direction",
            "min_units", "max_units", "min_volume", "max_volume")
    options = {key: str(data.get(key, ""))[:160] for key in keys}
    for key in ("min_units", "max_units", "min_volume", "max_volume"):
        if options[key] and not re.fullmatch(r"\d{1,14}(\.\d{1,2})?", options[key]):
            raise ValueError("Production filters must be nonnegative numbers")
    return options


def selected_session(c):
    return c.execute("select * from dialer_sessions where user_id=? and state<>'ended'", (g.user_id,)).fetchone()


def current_item(c, session_id):
    return c.execute("""
        select i.*, a.id attempt_id, a.status, a.detected, a.armed, a.playback_started,
               a.playback_complete, a.provider_sid, a.created_at, a.last_poll
        from dialer_items i left join dialer_attempts a using(session_id,position)
        where i.session_id=? and i.state in ('pending','active') order by i.position limit 1
    """, (session_id,)).fetchone()


def item_json(row):
    if row is None:
        return None
    item = dict(row)
    item["contact"] = json.loads(item.pop("snapshot"))
    item.pop("provider_sid", None)
    return item


def session_snapshot(c, session_id):
    session = c.execute("select * from dialer_sessions where id=?", (session_id,)).fetchone()
    item = current_item(c, session_id)
    next_item = None
    if item:
        next_item = c.execute("""
            select snapshot, position from dialer_items
            where session_id=? and state='pending' and position>? order by position limit 1
        """, (session_id, item["position"])).fetchone()
    counts = dict(c.execute("select state,count(*) from dialer_items where session_id=? group by state", (session_id,)))
    return {
        "id": session["id"], "state": session["state"],
        "audio_ready": bool(session["conference_sid"] and session["lease_until"] >= time.time()),
        "mode": session["voicemail_mode"], "current": item_json(item),
        "next": json.loads(next_item["snapshot"]) if next_item else None,
        "counts": counts,
    }


def is_eligible(c, item, voicemail=False):
    number = item["number"]
    policy = c.execute("select * from dialer_phone_policy where number=?", (number,)).fetchone()
    row = c.execute("select * from contacts where id=?", (item["contact_id"],)).fetchone()
    if not row or dict(row).get("voice_opt_out") or dict(row).get("roster_status") == "Former / inactive":
        return False
    if number not in {normalize_number(row["phone"]), normalize_number(row["mobile"])}:
        return False
    if number in suppressions(c) or (policy and policy["suppressed"]):
        return False
    return not voicemail or bool(policy and policy["voicemail_consent"] and policy["evidence"])


def register_policy(c, number, state, evidence):
    c.execute("""
        insert into dialer_phone_policy(number,suppressed,voicemail_consent,evidence,updated_by,updated_at)
        values (?,?,?,?,?,?) on conflict(number) do update set
        suppressed=excluded.suppressed, voicemail_consent=excluded.voicemail_consent,
        evidence=excluded.evidence, updated_by=excluded.updated_by, updated_at=excluded.updated_at
    """, (number, int(state == "suppress"), int(state == "consent"), evidence, g.user_id, now()))
    c.execute("insert into dialer_phone_policy_history(number,action,evidence,actor_id,recorded_at) values(?,?,?,?,?)",
              (number, state, evidence, g.user_id, now()))


@bp.get("/priority-dialer")
@require_ae
def page():
    return render_template("priority_dialer.html")


@bp.get(PREFIX + "/contacts")
@require_ae
def contacts():
    try:
        options = options_from(request.args)
        page_no = max(1, request.args.get("page", 1, type=int))
    except ValueError as exc:
        return error(str(exc))
    with database() as c:
        rows, weights = rank_contacts(c, options)
    offset = (page_no - 1) * 75
    return jsonify(items=rows[offset:offset + 75], total=len(rows),
                   eligible=len(ordered_queue(rows)),
                   weights=weights, configured=configured(),
                   can_manage=g.membership_role in {"Manager", "Owner"})


@bp.put(PREFIX + "/weights")
@require_ae
def weights():
    if g.membership_role not in {"Manager", "Owner"}:
        return error("Manager access required", 403)
    values = body()
    if set(values) != set(WEIGHTS) or any(type(v) is not int or not 0 <= v <= 100 for v in values.values()) or sum(values.values()) != 100:
        return error("Enter four whole-number weights that add up to 100")
    with database(write=True) as c:
        c.executemany("insert into dialer_weights values(?,?) on conflict(component) do update set weight=excluded.weight", values.items())
    return jsonify(ok=True)


@bp.put(PREFIX + "/contacts/<int:contact_id>/phone-policy")
@require_ae
def phone_policy(contact_id):
    data = body()
    number = normalize_number(data.get("number"))
    state = data.get("state")
    evidence = str(data.get("evidence", "")).strip()[:2000]
    if not number or state not in ("consent", "revoke", "suppress", "clear") or not evidence:
        return error("Select a valid phone number and provide the source or reason")
    if state in ("consent", "clear") and g.membership_role not in {"Manager", "Owner"}:
        return error("Manager access required", 403)
    with database(write=True) as c:
        contact = c.execute("select phone,mobile from contacts where id=?", (contact_id,)).fetchone()
        if not contact or number not in {normalize_number(value) for value in contact}:
            return error("Contact phone number was not found", 404)
        current = c.execute("select suppressed from dialer_phone_policy where number=?", (number,)).fetchone()
        if state == "consent" and current and current["suppressed"]:
            return error("Resolve the existing suppression before granting voicemail consent", 409)
        if state == "revoke" and current and current["suppressed"]:
            state = "suppress"
        register_policy(c, number, state, evidence)
    return jsonify(ok=True)


@bp.get(PREFIX + "/clips")
@require_ae
def clips():
    with database() as c:
        rows = c.execute("select id,name,seconds from dialer_clips where user_id=? order by created_at desc,id", (g.user_id,))
        return jsonify(items=[dict(row) for row in rows])


@bp.post(PREFIX + "/clips")
@require_ae
def upload_clip():
    if request.content_length is None or request.content_length > 2_000_000:
        return error("Voicemail clip must be under 2 MB", 413)
    upload = request.files.get("audio")
    name = request.form.get("name", "").strip()[:80]
    if not upload or not name:
        return error("Name and record the voicemail clip first")
    audio = upload.read(2_000_000)
    try:
        with wave.open(io.BytesIO(audio)) as recording:
            seconds = recording.getnframes() / recording.getframerate()
            if recording.getnchannels() != 1 or recording.getsampwidth() != 2 or recording.getframerate() != 8000 or not 1 <= seconds <= 60:
                raise ValueError
            if len(recording.readframes(recording.getnframes())) != recording.getnframes() * 2:
                raise ValueError
    except (wave.Error, ValueError, EOFError, ZeroDivisionError):
        return error("Record a voicemail between 1 and 60 seconds")
    with database(write=True) as c:
        clip_id = uuid.uuid4().hex
        c.execute("insert into dialer_clips values (?,?,?,?,?,?)", (clip_id, g.user_id, name, audio, seconds, now()))
    return jsonify(id=clip_id, name=name, seconds=seconds), 201


def wav_response(audio):
    return Response(audio, mimetype="audio/wav", headers={"Cache-Control": "private, no-store"})


@bp.get(PREFIX + "/clips/<clip_id>/audio")
@require_ae
def preview_clip(clip_id):
    with database() as c:
        row = c.execute("select audio from dialer_clips where id=? and user_id=?", (clip_id, g.user_id)).fetchone()
    return wav_response(row["audio"]) if row else error("Clip not found", 404)


@bp.route(PREFIX + "/session", methods=["GET", "POST"])
@require_ae
def session_route():
    if request.method == "GET":
        with database() as c:
            session = selected_session(c)
            return jsonify(session=session_snapshot(c, session["id"]) if session else None)
    if not configured():
        return error("Live dialing requires workspace phone setup", 503)
    data = body()
    mode = data.get("mode", "off")
    if mode not in ("off", "manual", "automatic"):
        return error("Choose a valid voicemail mode")
    clip_id = data.get("clip_id") if mode != "off" else None
    try:
        options = options_from(data.get("options") or {})
    except (AttributeError, ValueError) as exc:
        return error("Invalid search or production filters")
    with database(write=True) as c:
        if selected_session(c):
            return error("A dialer session is already open", 409)
        if mode != "off" and not c.execute("select 1 from dialer_clips where id=? and user_id=?", (clip_id, g.user_id)).fetchone():
            return error("Choose an approved personal voicemail")
        rows, _ = rank_contacts(c, options)
        queue = ordered_queue(rows)
        if not queue:
            return error("There are no callable contacts in this view", 409)
        session_id = uuid.uuid4().hex
        c.execute("""insert into dialer_sessions(id,user_id,clip_id,voicemail_mode,created_at,filters)
                     values (?,?,?,?,?,?)""", (session_id, g.user_id, clip_id, mode, now(), json.dumps(options)))
        c.executemany("insert into dialer_items(session_id,position,contact_id,number,snapshot) values(?,?,?,?,?)", [
            (session_id, position, row["id"], row["phone"], json.dumps(row))
            for position, row in enumerate(queue, 1)
        ])
        return jsonify(session=session_snapshot(c, session_id)), 201


@bp.get(PREFIX + "/token")
@require_ae
def voice_token():
    if not configured():
        return error("Live dialing requires workspace phone setup", 503)
    token = AccessToken(config("TWILIO_ACCOUNT_SID"), config("TWILIO_API_KEY_SID"),
                        config("TWILIO_API_KEY_SECRET"), identity=f"bb_{g.workspace_id}_{g.user_id}", ttl=3600)
    token.add_grant(VoiceGrant(outgoing_application_sid=config("TWILIO_DIALER_APP_SID")))
    return jsonify(token=token.to_jwt())


def owned_session(c, session_id):
    return c.execute("select * from dialer_sessions where id=? and user_id=?", (session_id, g.user_id)).fetchone()


def provider_update(sid, status):
    if not sid:
        return
    try:
        client().calls(sid).update(status=status)
    except TwilioRestException as exc:
        if exc.status not in (404, 400):
            current_app.logger.warning("Dialer call control failed (%s)", exc.status)
    except Exception:
        current_app.logger.warning("Dialer call control unavailable")


def refresh_provider(c, attempt, sid, status):
    if not sid or (attempt["provider_sid"] and attempt["provider_sid"] != sid):
        return
    order = {"starting": 0, "queued": 1, "initiated": 2, "ringing": 3, "in-progress": 4}
    if attempt["status"] in TERMINAL or (status not in TERMINAL and order.get(status, -1) < order.get(attempt["status"], 0)):
        return
    c.execute("update dialer_attempts set provider_sid=?,status=? where id=?", (sid, status, attempt["id"]))


def get_attempt(c, attempt_id):
    return c.execute("""
        select a.*, i.number, i.contact_id, s.user_id, s.state session_state, s.clip_id, s.voicemail_mode,
               s.lease_until, s.leg_sid
        from dialer_attempts a join dialer_items i using(session_id,position)
        join dialer_sessions s on s.id=a.session_id where a.id=?
    """, (attempt_id,)).fetchone()


def mark_unconfirmed(attempt_id):
    current_app.logger.warning("Dialer call creation could not be confirmed")
    with database(write=True) as c:
        c.execute("update dialer_attempts set status='unconfirmed' where id=? and status='starting' and provider_sid=''", (attempt_id,))


def reconcile(attempt_id, sid):
    try:
        status = client().calls(sid).fetch().status
    except Exception:
        return
    with database(write=True) as c:
        refresh_provider(c, get_attempt(c, attempt_id), sid, status)


def dispatch(workspace, attempt_id, number):
    with database(write=True) as c:
        attempt = get_attempt(c, attempt_id)
        if not attempt or attempt["session_state"] not in ("running", "paused") or attempt["lease_until"] < time.time() or not is_eligible(c, attempt):
            c.execute("update dialer_attempts set status='canceled' where id=?", (attempt_id,))
            return
    try:
        call = client().calls.create(
            to=number, from_=config("TWILIO_FROM_NUMBER"), url=callbacks(workspace, f"answer/{attempt_id}"),
            status_callback=callbacks(workspace, f"status/{attempt_id}"),
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            timeout=25, time_limit=1800, machine_detection="DetectMessageEnd", machine_detection_timeout=25,
        )
    except TwilioRestException as exc:
        if 400 <= exc.status < 500 and exc.status != 429:
            with database(write=True) as c:
                c.execute("update dialer_attempts set status='failed' where id=? and provider_sid=''", (attempt_id,))
            return
        mark_unconfirmed(attempt_id)
        return
    except Exception:
        mark_unconfirmed(attempt_id)
        return
    with database(write=True) as c:
        attempt = get_attempt(c, attempt_id)
        refresh_provider(c, attempt, call.sid, call.status)
        closing = attempt["session_state"] == "closing"
    if closing:
        provider_update(call.sid, "completed" if call.status == "in-progress" else "canceled")


@bp.post(PREFIX + "/session/<session_id>/control")
@require_ae
def control(session_id):
    data = body()
    action = data.get("action")
    if action not in ("pulse", "resume", "pause", "end", "hangup", "arm", "resolve"):
        return error("Invalid dialer action")
    if action in ("pulse", "resume", "arm") and not configured():
        return error("Live dialing is unavailable", 503)
    queued = None
    cancel = None
    check = None
    with database(write=True) as c:
        session = owned_session(c, session_id)
        if not session:
            return error("Dialer session not found", 404)
        item = current_item(c, session_id)
        live = item and item["state"] == "active" and item["status"] not in TERMINAL
        owns_audio = session["leg_sid"] and session["leg_sid"] == data.get("leg_sid")
        if action in ("pulse", "resume") and (not owns_audio or not session["conference_sid"]):
            return error("Connect this browser’s headset to the session first", 409)
        if action == "resume" and session["state"] not in ("paused", "running"):
            return error("The session is closing", 409)
        if action == "pulse" and session["state"] == "running" and session["lease_until"] < time.time():
            c.execute("update dialer_sessions set state='paused' where id=?", (session_id,))
        if action in ("pulse", "resume"):
            c.execute("update dialer_sessions set lease_until=? where id=?", (time.time() + LEASE_SECONDS, session_id))
        if action == "resume":
            c.execute("update dialer_sessions set state='running' where id=?", (session_id,))
        if action == "pause" and session["state"] == "running":
            c.execute("update dialer_sessions set state='paused' where id=?", (session_id,))
        if action == "end" and session["state"] != "ended":
            c.execute("update dialer_sessions set state=?,lease_until=0 where id=?",
                      ("closing" if item and item["state"] == "active" else "ended", session_id))
        if action in ("hangup", "end") and live and item["provider_sid"]:
            cancel = (item["provider_sid"], "completed" if item["status"] == "in-progress" else "canceled")
        if action == "pulse" and live and item["provider_sid"] and time.time() - item["last_poll"] >= 15:
            check = (item["attempt_id"], item["provider_sid"])
            c.execute("update dialer_attempts set last_poll=? where id=?", (time.time(), item["attempt_id"]))
        if action == "resolve":
            if not live or item["provider_sid"] or item["status"] != "unconfirmed" or data.get("confirmed") is not True:
                return error("Confirm that no call is active in the provider dashboard", 409)
            try:
                age = time.time() - datetime.fromisoformat(item["created_at"]).timestamp()
            except ValueError:
                age = 0
            if age < 120:
                return error("Wait two minutes for provider callbacks before clearing this attempt", 409)
            c.execute("update dialer_attempts set status='failed' where id=?", (item["attempt_id"],))
            if session["state"] == "running":
                c.execute("update dialer_sessions set state='paused' where id=?", (session_id,))
        if action == "arm":
            if not live or item["detected"] or not owns_audio or session["voicemail_mode"] != "manual" or not is_eligible(c, item, voicemail=True):
                return error("The current call is not eligible for a voicemail drop", 409)
            c.execute("update dialer_attempts set armed=1 where id=?", (item["attempt_id"],))
        session = owned_session(c, session_id)
        if action in ("pulse", "resume") and session["state"] == "running":
            while item and item["state"] == "pending" and not is_eligible(c, item):
                c.execute("update dialer_items set state='skipped',skip_reason='Phone unavailable or suppressed' where session_id=? and position=?",
                          (session_id, item["position"]))
                item = current_item(c, session_id)
            if item and item["state"] == "pending":
                attempt_id = uuid.uuid4().hex
                c.execute("update dialer_items set state='active' where session_id=? and position=?", (session_id, item["position"]))
                c.execute("insert into dialer_attempts(id,session_id,position,created_at) values (?,?,?,?)",
                          (attempt_id, session_id, item["position"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
                queued = (attempt_id, item["number"])
            elif not item:
                c.execute("update dialer_sessions set state='ended',lease_until=0 where id=?", (session_id,))
    if cancel:
        provider_update(*cancel)
        if item:
            reconcile(item["attempt_id"], cancel[0])
    if check:
        reconcile(*check)
    if queued:
        dispatch(g.workspace_id, *queued)
    with database() as c:
        return jsonify(session=session_snapshot(c, session_id))


@bp.post(PREFIX + "/session/<session_id>/outcome")
@require_ae
def save_outcome(session_id):
    data = body()
    outcome = data.get("outcome")
    if outcome not in OUTCOMES:
        return error("Choose a call outcome")
    notes = str(data.get("notes", "")).strip()[:5000]
    follow_up = str(data.get("follow_up", "")).strip()
    if follow_up:
        try:
            follow_up = date.fromisoformat(follow_up).isoformat()
        except ValueError:
            return error("Choose a valid follow-up date")
    with database(write=True) as c:
        session = owned_session(c, session_id)
        attempt = get_attempt(c, data.get("attempt_id", ""))
        if not session or not attempt or attempt["session_id"] != session_id:
            return error("Dialer call not found", 404)
        if attempt["outcome"]:
            return jsonify(session=session_snapshot(c, session_id))
        if attempt["status"] not in TERMINAL:
            return error("Finish the current call before logging the outcome", 409)
        contact = json.loads(c.execute("select snapshot from dialer_items where session_id=? and position=?",
                                      (session_id, attempt["position"])).fetchone()[0])
        actual = c.execute("select prospect_id from contacts where id=?", (contact["id"],)).fetchone()
        if outcome == "Do not call":
            register_policy(c, attempt["number"], "suppress", notes or "Do not call recorded during dialer wrap-up")
        action_id = memory_id = None
        if actual:
            prospect_id = actual["prospect_id"]
            action_id = c.execute("""
                insert into sales_actions(prospect_id,action_type,outcome,notes,follow_up_date,created_at,source_view)
                values (?,'Call',?,?,?,?,'priority_dialer')
            """, (prospect_id, outcome, notes, follow_up, now())).lastrowid
            prior_reminders = c.execute("""
                select a.memory_id from dialer_attempts a join dialer_items i using(session_id,position)
                where i.contact_id=? and a.memory_id is not null
            """, (contact["id"],))
            reminders = [(row[0],) for row in prior_reminders]
            c.executemany("update memories set follow_up_date='',note_type='Completed:Follow-up' where id=? and note_type='Follow-up'", reminders)
            if follow_up:
                full_name = f"{contact['first_name']} {contact['last_name']}".strip() or "Contact"
                memory_id = c.execute("""
                    insert into memories(prospect_id,note_type,note,follow_up_date,created_at)
                    values (?,'Follow-up',?,?,?)
                """, (prospect_id, f"{full_name}: {notes or outcome}", follow_up, now())).lastrowid
            if outcome in ("Connected", "Interested"):
                c.execute("update prospects set status='Contacted',updated_at=? where id=? and status='New'", (now(), prospect_id))
            if outcome == "Meeting scheduled":
                c.execute("update prospects set status='Meeting',updated_at=? where id=? and status in ('New','Contacted','Replied')",
                          (now(), prospect_id))
        c.execute("""
            update dialer_attempts set outcome=?,notes=?,follow_up_date=?,sales_action_id=?,memory_id=? where id=?
        """, (outcome, notes, follow_up, action_id, memory_id, attempt["id"]))
        c.execute("update dialer_items set state='done' where session_id=? and position=?", (session_id, attempt["position"]))
        if session["state"] == "closing" or not current_item(c, session_id):
            c.execute("update dialer_sessions set state='ended',lease_until=0 where id=?", (session_id,))
        return jsonify(session=session_snapshot(c, session_id))


def twiml(content):
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{content}</Response>', mimetype="text/xml")


def room(session_id, ae=False, event_url=""):
    attributes = ' waitUrl="" startConferenceOnEnter="true"'
    if ae:
        attributes += f' endConferenceOnExit="true" statusCallback="{escape(event_url)}" statusCallbackEvent="join leave end"'
    return f'<Dial><Conference{attributes}>brokerbeacon-{session_id}</Conference></Dial>'


@bp.post("/dialer/voice/agent")
@provider_request
def agent(workspace):
    session_id = request.form.get("DialerSession", "")
    sid = request.form.get("CallSid", "")
    with database(write=True) as c:
        session = c.execute("select * from dialer_sessions where id=?", (session_id,)).fetchone()
        if not configured() or not session or session["state"] not in ("paused", "running") or not sid:
            return twiml("<Hangup/>")
        if request.form.get("From") != f"client:bb_{workspace}_{session['user_id']}":
            return twiml("<Hangup/>")
        if session["leg_sid"] == sid:
            return twiml(room(session_id, ae=True, event_url=callbacks(workspace, f"conference/{session_id}")))
        if session["leg_sid"] and session["lease_until"] >= time.time():
            return twiml("<Hangup/>")
        c.execute("""
            update dialer_sessions set leg_sid=?,state='paused',conference_sid='',lease_until=? where id=?
        """, (sid, time.time() + LEASE_SECONDS, session_id))
    return twiml(room(session_id, ae=True, event_url=callbacks(workspace, f"conference/{session_id}")))


@bp.post("/dialer/voice/<int:workspace>/conference/<session_id>")
@provider_request
def conference(workspace, session_id):
    event = request.form.get("StatusCallbackEvent")
    sid = request.form.get("CallSid")
    conference_sid = request.form.get("ConferenceSid", "")
    with database(write=True) as c:
        session = c.execute("select * from dialer_sessions where id=?", (session_id,)).fetchone()
        if session and event == "participant-join" and sid == session["leg_sid"]:
            c.execute("update dialer_sessions set conference_sid=? where id=?", (conference_sid, session_id))
        if session and ((event == "participant-leave" and sid == session["leg_sid"]) or
                        (event == "conference-end" and conference_sid and conference_sid == session["conference_sid"])):
            c.execute("""
                update dialer_sessions set leg_sid='',conference_sid='',lease_until=0,
                state=case when state='running' then 'paused' else state end where id=?
            """, (session_id,))
    return "", 204


def media_signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="priority-dialer-media")


def matching_sid(attempt):
    sid = request.form.get("CallSid", "")
    return bool(attempt and sid and attempt["provider_sid"] in ("", sid))


@bp.post("/dialer/voice/<int:workspace>/answer/<attempt_id>")
@provider_request
def answer(workspace, attempt_id):
    with database(write=True) as c:
        attempt = get_attempt(c, attempt_id)
        if not matching_sid(attempt) or attempt["status"] in TERMINAL:
            return twiml("<Hangup/>")
        refresh_provider(c, attempt, request.form["CallSid"], "in-progress")
        detected = request.form.get("AnsweredBy", "unknown")[:50]
        if attempt["detected"] and attempt["detected"] != detected:
            return twiml("<Hangup/>")
        c.execute("update dialer_attempts set detected=? where id=?", (detected, attempt_id))
        if not configured() or attempt["session_state"] not in ("running", "paused") or not is_eligible(c, attempt):
            return twiml("<Hangup/>")
        if detected in ("human", "unknown") and attempt["leg_sid"] and attempt["lease_until"] >= time.time():
            return twiml(room(attempt["session_id"]))
        if detected == "machine_end_beep" and attempt["clip_id"] and (
            attempt["voicemail_mode"] == "automatic" or attempt["armed"]
        ) and not attempt["playback_started"] and is_eligible(c, attempt, voicemail=True):
            c.execute("update dialer_attempts set playback_started=1 where id=?", (attempt_id,))
            token = media_signer().dumps([workspace, attempt_id, attempt["clip_id"]])
            audio = escape(callbacks(workspace, f"media/{token}"))
            done = escape(callbacks(workspace, f"played/{attempt_id}"))
            return twiml(f'<Play>{audio}</Play><Redirect method="POST">{done}</Redirect>')
    return twiml("<Hangup/>")


@bp.post("/dialer/voice/<int:workspace>/played/<attempt_id>")
@provider_request
def played(workspace, attempt_id):
    with database(write=True) as c:
        attempt = get_attempt(c, attempt_id)
        if matching_sid(attempt) and attempt["playback_started"]:
            c.execute("update dialer_attempts set playback_complete=1 where id=?", (attempt_id,))
    return twiml("<Hangup/>")


@bp.post("/dialer/voice/<int:workspace>/status/<attempt_id>")
@provider_request
def status(workspace, attempt_id):
    closing = False
    sid = request.form.get("CallSid", "")
    next_status = request.form.get("CallStatus", "")
    with database(write=True) as c:
        attempt = get_attempt(c, attempt_id)
        if matching_sid(attempt) and next_status in TERMINAL | {"queued", "initiated", "ringing", "in-progress"}:
            refresh_provider(c, attempt, sid, next_status)
            closing = attempt["session_state"] == "closing" and next_status not in TERMINAL
    if closing:
        provider_update(sid, "completed" if next_status == "in-progress" else "canceled")
    return "", 204


@bp.get("/dialer/voice/<int:workspace>/media/<token>")
def media(workspace, token):
    try:
        signed_workspace, attempt_id, clip_id = media_signer().loads(token, max_age=120)
    except BadSignature:
        abort(403)
    if signed_workspace != workspace:
        abort(403)
    g.workspace_id = workspace
    with database() as c:
        attempt = get_attempt(c, attempt_id)
        if not attempt or attempt["clip_id"] != clip_id or not attempt["playback_started"] or attempt["status"] in TERMINAL or attempt["session_state"] == "closing":
            abort(404)
        if not is_eligible(c, attempt, voicemail=True):
            abort(403)
        row = c.execute("select audio from dialer_clips where id=?", (clip_id,)).fetchone()
    return wav_response(row["audio"]) if row else abort(404)
