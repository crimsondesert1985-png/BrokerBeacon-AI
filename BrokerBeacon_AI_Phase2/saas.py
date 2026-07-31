"""BrokerBeacon SaaS foundation: identity, tenancy, roles, and platform controls."""
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import hmac
from email.message import EmailMessage
import json
import os
import secrets
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request as urlrequest

from flask import Blueprint, g, jsonify, redirect, render_template_string, request, session
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from security_monitoring import emit_security_alert
from postgres_migration import build_migration_plan, migration_status, rehearsal_status


ROLE_RANK = {"Read Only": 10, "AE": 20, "Manager": 30, "Owner": 40}
PUBLIC_PATHS = {"/login", "/register", "/forgot-password", "/reset-password", "/verify-email",
                "/resend-verification", "/pricing", "/api/saas/billing/webhook",
                "/health", "/api/version", "/demo"}
LOGIN_LIMIT = 5
LOGIN_WINDOW_MINUTES = 15
PLAN_LIMITS = {
    "Founding": {"seats": 25, "monthly_ai_actions": 10000},
    "Trial": {"seats": 5, "monthly_ai_actions": 500},
    "Starter": {"seats": 10, "monthly_ai_actions": 2500},
}
PLATFORM_PREFIXES = (
    "/api/scout", "/api/index-population", "/api/automation",
    "/api/platform", "/api/population",
)

AUTH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>{{ title }} · BrokerBeacon AI</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#07162e;
font:15px Inter,Segoe UI,Arial;color:#17233a}.card{width:min(430px,92vw);background:white;
padding:32px;border-radius:18px;box-shadow:0 28px 80px #0008}.brand{font-size:24px;font-weight:900;
color:#0d2347}.brand span{color:#c6283d}h1{font-size:22px;margin:26px 0 8px}p{color:#66758f;
line-height:1.5}label{display:block;font-size:12px;font-weight:700;margin:16px 0 6px}input,select{
box-sizing:border-box;width:100%;padding:12px;border:1px solid #ccd7e7;border-radius:9px}
button{width:100%;margin-top:20px;padding:13px;border:0;border-radius:9px;background:#174ea6;
color:white;font-weight:800;cursor:pointer}.error{background:#fdecef;color:#9d1930;padding:10px;
border-radius:8px}.ok{background:#e7f7ed;color:#116635;padding:10px;border-radius:8px}a{
color:#174ea6;text-decoration:none}.links{display:flex;justify-content:space-between;margin-top:18px;
font-size:13px}</style></head><body><main class="card"><div class="brand">BrokerBeacon
<span>AI</span></div><h1>{{ title }}</h1><p>{{ subtitle }}</p>{% if error %}<div class="error">
{{ error }}</div>{% endif %}{% if message %}<div class="ok">{{ message }}</div>{% endif %}
{{ form|safe }}</main></body></html>"""


SCHEMA = """
create table if not exists saas_workspaces(
 id integer primary key, name text not null, slug text unique not null,
 plan text not null default 'Founding', subscription_status text not null default 'trialing',
 trial_ends_at text default '', billing_customer_id text default '',
 billing_subscription_id text default '', seat_limit integer not null default 5,
 is_founding integer not null default 0, created_at text not null, updated_at text not null
);
create table if not exists saas_users(
 id integer primary key, email text unique not null collate nocase, full_name text not null,
 password_hash text not null, is_platform_owner integer not null default 0,
 is_active integer not null default 1, last_login_at text default '',
 created_at text not null, updated_at text not null
);
create table if not exists saas_memberships(
 id integer primary key, workspace_id integer not null, user_id integer not null,
 role text not null check(role in ('Owner','Manager','AE','Read Only')),
 created_at text not null, unique(workspace_id,user_id),
 foreign key(workspace_id) references saas_workspaces(id),
 foreign key(user_id) references saas_users(id)
);
create table if not exists saas_invitations(
 id integer primary key, workspace_id integer not null, email text not null collate nocase,
 role text not null, token_hash text unique not null, invited_by integer not null,
 expires_at text not null, accepted_at text default '', created_at text not null
);
create table if not exists saas_password_resets(
 id integer primary key, user_id integer not null, token_hash text unique not null,
 expires_at text not null, used_at text default '', created_at text not null
);
create table if not exists saas_email_verifications(
 id integer primary key, user_id integer not null, token_hash text unique not null,
 expires_at text not null, used_at text default '', created_at text not null,
 foreign key(user_id) references saas_users(id)
);
create table if not exists saas_auth_attempts(
 identity_hash text not null, ip_address text not null, attempt_count integer not null default 0,
 window_started_at text not null, blocked_until text default '', updated_at text not null,
 primary key(identity_hash,ip_address)
);
create table if not exists saas_audit_log(
 id integer primary key, workspace_id integer, user_id integer, action text not null,
 target_type text default '', target_id text default '', detail_json text default '{}',
 ip_address text default '', created_at text not null
);
create table if not exists national_broker_index(
 id integer primary key, prospect_id integer unique, nmls text default '', company text not null,
 city text default '', state text default '', source_name text default '',
 source_url text default '', verification_status text default 'Needs verification',
 indexed_at text not null, updated_at text not null
);
create table if not exists workspace_broker_records(
 id integer primary key, workspace_id integer not null, national_broker_id integer not null,
 pipeline_status text not null default 'New', assigned_user_id integer,
 private_notes text default '', created_at text not null, updated_at text not null,
 unique(workspace_id,national_broker_id)
);
create table if not exists saas_workspace_settings(
 workspace_id integer primary key, primary_market text default '', team_size text default '',
 primary_goal text default '', onboarding_completed_at text default '', updated_at text not null,
 foreign key(workspace_id) references saas_workspaces(id) on delete cascade
);
create table if not exists saas_usage_events(
 id integer primary key, workspace_id integer not null, event_type text not null,
 quantity integer not null default 1, detail_json text default '{}', created_at text not null,
 foreign key(workspace_id) references saas_workspaces(id) on delete cascade
);
create index if not exists idx_saas_memberships_user on saas_memberships(user_id,workspace_id);
create index if not exists idx_saas_audit_workspace on saas_audit_log(workspace_id,id desc);
create index if not exists idx_saas_resets_user on saas_password_resets(user_id,created_at desc);
create index if not exists idx_saas_verifications_user on saas_email_verifications(user_id,created_at desc);
create index if not exists idx_workspace_brokers_workspace on workspace_broker_records(workspace_id,id);
create index if not exists idx_saas_usage_workspace on saas_usage_events(workspace_id,created_at,event_type);
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _safe_next(value):
    value = value or "/"
    return value if value.startswith("/") and not value.startswith("//") else "/"


def _slug(conn, name):
    base = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-") or "workspace"
    base = "-".join(filter(None, base.split("-")))[:44]
    candidate, suffix = base, 1
    while conn.execute("select 1 from saas_workspaces where slug=?", (candidate,)).fetchone():
        suffix += 1
        candidate = f"{base[:38]}-{suffix}"
    return candidate


def install_saas(app, db_path, build_version):
    bp = Blueprint("saas", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        conn.executescript(SCHEMA)
        now = _now()
        user_columns = {row[1] for row in conn.execute("pragma table_info(saas_users)")}
        if "email_verified_at" not in user_columns:
            conn.execute("alter table saas_users add column email_verified_at text default ''")
            conn.execute("update saas_users set email_verified_at=? where email_verified_at=''", (now,))
        if "auth_version" not in user_columns:
            conn.execute("alter table saas_users add column auth_version integer not null default 1")
        workspace_columns = {row[1] for row in conn.execute("pragma table_info(saas_workspaces)")}
        if "billing_price_id" not in workspace_columns:
            conn.execute("alter table saas_workspaces add column billing_price_id text default ''")
        conn.execute("""insert or ignore into saas_workspace_settings
            (workspace_id,onboarding_completed_at,updated_at)
            select id,case when is_founding=1 then ? else '' end,? from saas_workspaces""", (now, now))
        conn.execute("""insert or ignore into national_broker_index
            (prospect_id,nmls,company,city,state,source_name,source_url,verification_status,indexed_at,updated_at)
            select id,coalesce(nmls,''),company,coalesce(city,''),coalesce(state,''),
            coalesce(source_name,''),coalesce(source_url,''),coalesce(verification_status,'Needs verification'),?,?
            from prospects""", (now, now))

    app.secret_key = app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY") or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.getenv("RENDER") == "true",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12))

    def deliver_security_email(recipient, subject, text):
        """Deliver security mail without logging or persisting raw tokens."""
        if app.config.get("TESTING"):
            app.extensions.setdefault("security_outbox", []).append(
                {"to": recipient, "subject": subject, "text": text}
            )
            return True
        host = os.getenv("SMTP_HOST", "").strip()
        sender = os.getenv("SECURITY_EMAIL_FROM", "").strip()
        if not host or not sender:
            app.logger.error("Security email delivery is not configured")
            return False
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, recipient, subject
        message.set_content(text)
        port = int(os.getenv("SMTP_PORT", "587"))
        try:
            with smtplib.SMTP(host, port, timeout=10) as client:
                client.starttls()
                username = os.getenv("SMTP_USERNAME", "")
                if username:
                    client.login(username, os.getenv("SMTP_PASSWORD", ""))
                client.send_message(message)
            return True
        except Exception:
            app.logger.exception("Security email delivery failed")
            return False

    def create_verification(conn, user_id, email):
        token = secrets.token_urlsafe(32)
        conn.execute("update saas_email_verifications set used_at=? where user_id=? and used_at=''",
                     (_now(), user_id))
        conn.execute("""insert into saas_email_verifications
            (user_id,token_hash,expires_at,created_at) values(?,?,?,?)""",
            (user_id, _hash_token(token),
             (datetime.now()+timedelta(hours=24)).isoformat(timespec="seconds"), _now()))
        link = request.url_root.rstrip("/") + "/verify-email?token=" + token
        return deliver_security_email(email, "Verify your BrokerBeacon email",
            "Verify your BrokerBeacon email address within 24 hours:\n\n" + link)

    def client_ip():
        return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",", 1)[0].strip()[:120]

    def login_key(email):
        return hashlib.sha256(email.encode("utf-8")).hexdigest()

    def login_is_blocked(conn, email):
        attempt = conn.execute("select blocked_until from saas_auth_attempts where identity_hash=? and ip_address=?",
                               (login_key(email), client_ip())).fetchone()
        return bool(attempt and attempt["blocked_until"] and attempt["blocked_until"] > _now())

    def record_login_failure(conn, email):
        key, ip, now = login_key(email), client_ip(), _now()
        attempt = conn.execute("select * from saas_auth_attempts where identity_hash=? and ip_address=?",
                               (key, ip)).fetchone()
        window_cutoff = (datetime.now()-timedelta(minutes=LOGIN_WINDOW_MINUTES)).isoformat(timespec="seconds")
        count = (int(attempt["attempt_count"]) if attempt and attempt["window_started_at"] > window_cutoff else 0) + 1
        started = attempt["window_started_at"] if attempt and attempt["window_started_at"] > window_cutoff else now
        blocked = (datetime.now()+timedelta(minutes=LOGIN_WINDOW_MINUTES)).isoformat(timespec="seconds") if count >= LOGIN_LIMIT else ""
        conn.execute("""insert into saas_auth_attempts(identity_hash,ip_address,attempt_count,window_started_at,blocked_until,updated_at)
            values(?,?,?,?,?,?) on conflict(identity_hash,ip_address) do update set attempt_count=excluded.attempt_count,
            window_started_at=excluded.window_started_at,blocked_until=excluded.blocked_until,updated_at=excluded.updated_at""",
            (key, ip, count, started, blocked, now))
        return count, blocked

    def clear_login_failures(conn, email):
        conn.execute("delete from saas_auth_attempts where identity_hash=? and ip_address=?",
                     (login_key(email), client_ip()))

    def stripe_request(path, data):
        secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
        if not secret:
            raise RuntimeError("Stripe billing is not configured")
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        stripe_request = urlrequest.Request(
            "https://api.stripe.com/v1/" + path.lstrip("/"), data=encoded,
            headers={"Authorization": "Bearer " + secret,
                     "Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": "BrokerBeacon-Billing/1.0"}, method="POST")
        with urlrequest.urlopen(stripe_request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def verify_stripe_signature(payload, signature):
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").encode("utf-8")
        if not secret or not signature:
            return False
        values = {}
        for item in signature.split(","):
            key, _, value = item.partition("=")
            values.setdefault(key, []).append(value)
        try:
            timestamp = int(values["t"][0])
        except (KeyError, ValueError):
            return False
        if abs(int(time.time()) - timestamp) > 300:
            return False
        expected = hmac.new(secret, str(timestamp).encode()+b"."+payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, candidate) for candidate in values.get("v1", []))

    def audit(conn, action, target_type="", target_id="", detail="{}"):
        workspace_id = getattr(g, "workspace_id", None)
        if not workspace_id and target_type == "user" and target_id:
            member = conn.execute("select workspace_id from saas_memberships where user_id=? order by id limit 1",
                                  (target_id,)).fetchone()
            workspace_id = member["workspace_id"] if member else None
        conn.execute("""insert into saas_audit_log
            (workspace_id,user_id,action,target_type,target_id,detail_json,ip_address,created_at)
            values(?,?,?,?,?,?,?,?)""", (workspace_id,
            getattr(g, "user_id", None), action, target_type, str(target_id), detail,
            client_ip(), _now()))

    @app.before_request
    def load_saas_context():
        g.user_id = session.get("user_id")
        g.workspace_id = session.get("workspace_id")
        g.membership_role = None
        g.is_platform_owner = False
        if g.user_id:
            with connect() as conn:
                user = conn.execute("select * from saas_users where id=? and is_active=1", (g.user_id,)).fetchone()
                if not user:
                    session.clear()
                else:
                    g.is_platform_owner = bool(user["is_platform_owner"])
                    if session.get("auth_version") != int(user["auth_version"]):
                        session.clear()
                        if request.path.startswith("/api/"):
                            return jsonify(error="Session expired"), 401
                        return redirect("/login")
                    membership = conn.execute("""select role from saas_memberships
                        where user_id=? and workspace_id=?""", (g.user_id, g.workspace_id)).fetchone()
                    g.membership_role = membership["role"] if membership else None
        if request.path in PUBLIC_PATHS or request.path.startswith(("/static/", "/invite/")):
            return None
        if not g.user_id:
            if request.path.startswith("/api/"):
                return jsonify(error="Authentication required"), 401
            return redirect("/login?next=" + request.path)
        if not g.membership_role:
            if request.path.startswith("/api/"):
                return jsonify(error="Workspace access required"), 403
            session.pop("workspace_id", None)
            return redirect("/login")
        if any(request.path.startswith(prefix) for prefix in PLATFORM_PREFIXES) and not g.is_platform_owner:
            return jsonify(error="Platform owner access required"), 403
        if request.path not in {"/onboarding", "/logout"} and not request.path.startswith("/api/saas/"):
            with connect() as conn:
                workspace = conn.execute("select is_founding,subscription_status,trial_ends_at from saas_workspaces where id=?",
                                         (g.workspace_id,)).fetchone()
                settings = conn.execute("select onboarding_completed_at from saas_workspace_settings where workspace_id=?",
                                        (g.workspace_id,)).fetchone()
            if workspace and not workspace["is_founding"] and not (settings and settings["onboarding_completed_at"]):
                if request.path.startswith("/api/"):
                    return jsonify(error="Workspace onboarding required", onboarding_url="/onboarding"), 428
                return redirect("/onboarding")
        if request.path not in {"/pricing", "/logout"} and not request.path.startswith("/api/saas/billing"):
            with connect() as conn:
                workspace = conn.execute("""select is_founding,subscription_status,trial_ends_at
                    from saas_workspaces where id=?""", (g.workspace_id,)).fetchone()
            expired = (workspace and not workspace["is_founding"] and
                       workspace["subscription_status"] != "active" and
                       workspace["trial_ends_at"] and workspace["trial_ends_at"] < _now())
            if expired:
                if request.path.startswith("/api/"):
                    return jsonify(error="Trial expired", billing_url="/pricing"), 402
                return redirect("/pricing?trial=expired")
        return None

    def require_role(minimum):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.membership_role or ROLE_RANK[g.membership_role] < ROLE_RANK[minimum]:
                    return jsonify(error=f"{minimum} role required"), 403
                return fn(*args, **kwargs)
            return wrapped
        return decorator

    @bp.route("/register", methods=["GET", "POST"])
    def register():
        error = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            name = (request.form.get("name") or "").strip()
            company = (request.form.get("company") or "").strip()
            password = request.form.get("password") or ""
            if not email or "@" not in email or not name or not company:
                error = "Name, company, and a valid email are required."
            elif len(password) < 12:
                error = "Use a password of at least 12 characters."
            else:
                try:
                    with connect() as conn:
                        first = conn.execute("select count(*) from saas_users").fetchone()[0] == 0
                        now = _now()
                        cur = conn.execute("""insert into saas_workspaces
                            (name,slug,plan,subscription_status,trial_ends_at,seat_limit,is_founding,created_at,updated_at)
                            values(?,?,?,?,?,?,?,?,?)""", (company, _slug(conn, company),
                            "Founding" if first else "Trial", "active" if first else "trialing",
                            "" if first else (datetime.now()+timedelta(days=14)).isoformat(timespec="seconds"),
                            25 if first else 5, 1 if first else 0, now, now))
                        workspace_id = cur.lastrowid
                        cur = conn.execute("""insert into saas_users
                            (email,full_name,password_hash,is_platform_owner,created_at,updated_at)
                            values(?,?,?,?,?,?)""", (email, name, generate_password_hash(password),
                            1 if first else 0, now, now))
                        user_id = cur.lastrowid
                        conn.execute("""insert into saas_memberships
                            (workspace_id,user_id,role,created_at) values(?,?,?,?)""",
                            (workspace_id, user_id, "Owner", now))
                        create_verification(conn, user_id, email)
                        session.update(user_id=user_id, workspace_id=workspace_id, auth_version=1)
                        session.permanent = True
                        g.user_id, g.workspace_id = user_id, workspace_id
                        audit(conn, "account.registered", "workspace", workspace_id)
                    return redirect("/" if first else "/onboarding")
                except sqlite3.IntegrityError:
                    error = "That email already has an account."
        form = """<form method="post"><label>Your name</label><input name="name" required>
        <label>Company</label><input name="company" required><label>Email</label>
        <input type="email" name="email" required><label>Password</label>
        <input type="password" name="password" minlength="12" required>
        <button>Create workspace</button></form><div class="links"><a href="/login">Sign in</a></div>"""
        return render_template_string(AUTH_PAGE, title="Create your workspace",
            subtitle="Start a secure, private BrokerBeacon company workspace.", error=error, message="", form=form)

    @bp.route("/onboarding", methods=["GET", "POST"])
    def onboarding():
        if request.method == "POST":
            market = (request.form.get("primary_market") or "").strip()[:120]
            team_size = (request.form.get("team_size") or "").strip()[:40]
            goal = (request.form.get("primary_goal") or "").strip()[:200]
            if market and team_size and goal:
                with connect() as conn:
                    conn.execute("""insert into saas_workspace_settings
                        (workspace_id,primary_market,team_size,primary_goal,onboarding_completed_at,updated_at)
                        values(?,?,?,?,?,?) on conflict(workspace_id) do update set
                        primary_market=excluded.primary_market,team_size=excluded.team_size,
                        primary_goal=excluded.primary_goal,onboarding_completed_at=excluded.onboarding_completed_at,
                        updated_at=excluded.updated_at""",
                        (g.workspace_id, market, team_size, goal, _now(), _now()))
                    audit(conn, "workspace.onboarding_completed", "workspace", g.workspace_id)
                return redirect("/")
        form = """<form method="post"><label>Primary market</label>
        <input name="primary_market" placeholder="Example: North Carolina wholesale" required>
        <label>Team size</label><select name="team_size" required><option value="">Choose one</option>
        <option>Just me</option><option>2–5 people</option><option>6–10 people</option><option>11+ people</option></select>
        <label>First outcome</label><input name="primary_goal" placeholder="Example: Prioritize and convert broker accounts" required>
        <button>Finish workspace setup</button></form>"""
        return render_template_string(AUTH_PAGE, title="Set up your workspace",
            subtitle="Three details help BrokerBeacon prepare the right operating view.",
            error="", message="", form=form)

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            with connect() as conn:
                if login_is_blocked(conn, email):
                    audit(conn, "security.login_blocked", "email_hash", login_key(email)[:16])
                    emit_security_alert("login_blocked", "warning", {"ip": client_ip()})
                    return render_template_string(AUTH_PAGE, title="Welcome back",
                        subtitle=f"Secure access to BrokerBeacon {build_version}.",
                        error="Too many attempts. Try again in 15 minutes.", message="", form=""), 429
                user = conn.execute("select * from saas_users where email=? and is_active=1", (email,)).fetchone()
                if user and check_password_hash(user["password_hash"], request.form.get("password") or ""):
                    if not user["email_verified_at"]:
                        audit(conn, "security.unverified_login_blocked", "user", user["id"])
                        error = "Verify your email before signing in."
                    else:
                        member = conn.execute("""select workspace_id from saas_memberships
                            where user_id=? order by id limit 1""", (user["id"],)).fetchone()
                        clear_login_failures(conn, email)
                        session.clear()
                        session.permanent = True
                        session.update(user_id=user["id"], workspace_id=member["workspace_id"],
                                       auth_version=int(user["auth_version"]))
                        conn.execute("update saas_users set last_login_at=?,updated_at=? where id=?",
                                     (_now(), _now(), user["id"]))
                        g.user_id, g.workspace_id = user["id"], member["workspace_id"]
                        audit(conn, "session.login", "user", user["id"])
                        return redirect(_safe_next(request.args.get("next")))
                else:
                    count, blocked = record_login_failure(conn, email)
                    audit(conn, "security.login_failed", "email_hash", login_key(email)[:16],
                          json.dumps({"attempt": count, "blocked": bool(blocked)}))
            if not error:
                error = "Email or password was incorrect."
        form = """<form method="post"><label>Email</label><input type="email" name="email" required>
        <label>Password</label><input type="password" name="password" required>
        <button>Sign in</button></form><div class="links"><a href="/register">Create account</a>
        <a href="/forgot-password">Forgot password?</a></div>"""
        return render_template_string(AUTH_PAGE, title="Welcome back",
            subtitle=f"Secure access to BrokerBeacon {build_version}.", error=error, message="", form=form)

    @bp.post("/logout")
    def logout():
        with connect() as conn:
            audit(conn, "session.logout", "user", g.user_id)
        session.clear()
        return redirect("/login")

    @bp.route("/invite/<token>", methods=["GET", "POST"])
    def accept_invitation(token):
        error = ""
        with connect() as conn:
            invitation = conn.execute("""select i.*,w.name workspace_name from saas_invitations i
                join saas_workspaces w on w.id=i.workspace_id where i.token_hash=?
                and i.accepted_at='' and i.expires_at>?""", (_hash_token(token), _now())).fetchone()
            if not invitation:
                return render_template_string(AUTH_PAGE, title="Invitation unavailable",
                    subtitle="This invitation is invalid, expired, or has already been used.",
                    error="Ask your workspace owner for a new invitation.", message="", form=""), 410
            existing = conn.execute("select * from saas_users where email=? collate nocase",
                                    (invitation["email"],)).fetchone()
            if request.method == "POST":
                user = existing
                if existing:
                    signed_in_as_invitee = g.user_id == existing["id"]
                    if not signed_in_as_invitee and not check_password_hash(
                            existing["password_hash"], request.form.get("password") or ""):
                        error = "Enter the password for this BrokerBeacon account."
                else:
                    name = (request.form.get("name") or "").strip()
                    password = request.form.get("password") or ""
                    if not name:
                        error = "Your name is required."
                    elif len(password) < 12:
                        error = "Use a password of at least 12 characters."
                    else:
                        now = _now()
                        cur = conn.execute("""insert into saas_users
                            (email,full_name,password_hash,created_at,updated_at)
                            values(?,?,?,?,?)""", (invitation["email"], name,
                            generate_password_hash(password), now, now))
                        user = conn.execute("select * from saas_users where id=?", (cur.lastrowid,)).fetchone()
                if not error:
                    seats = conn.execute("select count(*) from saas_memberships where workspace_id=?",
                                         (invitation["workspace_id"],)).fetchone()[0]
                    limit = conn.execute("select seat_limit from saas_workspaces where id=?",
                                         (invitation["workspace_id"],)).fetchone()[0]
                    already_member = conn.execute("""select 1 from saas_memberships
                        where workspace_id=? and user_id=?""",
                        (invitation["workspace_id"], user["id"])).fetchone()
                    if seats >= limit and not already_member:
                        error = "This workspace has reached its seat limit."
                    else:
                        conn.execute("""insert or ignore into saas_memberships
                            (workspace_id,user_id,role,created_at) values(?,?,?,?)""",
                            (invitation["workspace_id"], user["id"], invitation["role"], _now()))
                        conn.execute("update saas_invitations set accepted_at=? where id=?",
                                     (_now(), invitation["id"]))
                        session.clear()
                        session.permanent = True
                        session.update(user_id=user["id"], workspace_id=invitation["workspace_id"],
                                       auth_version=int(user["auth_version"]))
                        if not user["email_verified_at"]:
                            conn.execute("update saas_users set email_verified_at=?,updated_at=? where id=?",
                                         (_now(), _now(), user["id"]))
                        g.user_id, g.workspace_id = user["id"], invitation["workspace_id"]
                        audit(conn, "member.invitation_accepted", "user", user["id"])
                        return redirect("/")
        identity = ("Enter your existing password to join." if existing else
                    "Choose your name and a password to create your account.")
        safe_email = escape(invitation["email"])
        safe_workspace = escape(invitation["workspace_name"])
        name_field = "" if existing else '<label>Your name</label><input name="name" required>'
        form = f'''<form method="post">{name_field}<label>Email</label>
        <input value="{safe_email}" disabled><label>Password</label>
        <input type="password" name="password" minlength="12" required>
        <button>Join {safe_workspace}</button></form>'''
        return render_template_string(AUTH_PAGE, title=f"Join {invitation['workspace_name']}",
            subtitle=f"You were invited as {invitation['role']}. {identity}",
            error=error, message="", form=form)

    @bp.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        message = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            with connect() as conn:
                user = conn.execute("select id from saas_users where email=? and is_active=1", (email,)).fetchone()
                if user:
                    token = secrets.token_urlsafe(32)
                    conn.execute("update saas_password_resets set used_at=? where user_id=? and used_at=''",
                                 (_now(), user["id"]))
                    conn.execute("""insert into saas_password_resets
                        (user_id,token_hash,expires_at,created_at) values(?,?,?,?)""",
                        (user["id"], _hash_token(token),
                         (datetime.now()+timedelta(hours=1)).isoformat(timespec="seconds"), _now()))
                    link = request.url_root.rstrip("/") + "/reset-password?token=" + token
                    deliver_security_email(email, "Reset your BrokerBeacon password",
                        "Reset your BrokerBeacon password within one hour:\n\n" + link +
                        "\n\nIf you did not request this, ignore this message.")
                    audit(conn, "security.password_reset_requested", "user", user["id"])
            message = "If that account exists, a reset link has been prepared."
        form = """<form method="post"><label>Email</label><input type="email" name="email" required>
        <button>Request reset</button></form><div class="links"><a href="/login">Back to sign in</a></div>"""
        return render_template_string(AUTH_PAGE, title="Reset password",
            subtitle="Reset links expire after one hour.", error="", message=message, form=form)

    @bp.route("/reset-password", methods=["GET", "POST"])
    def reset_password():
        token = request.values.get("token") or ""
        error = ""
        if request.method == "POST":
            password = request.form.get("password") or ""
            if len(password) < 12:
                error = "Use a password of at least 12 characters."
            else:
                with connect() as conn:
                    reset = conn.execute("""select * from saas_password_resets where token_hash=?
                        and used_at='' and expires_at>?""", (_hash_token(token), _now())).fetchone()
                    if reset:
                        conn.execute("""update saas_users set password_hash=?,auth_version=auth_version+1,
                            updated_at=? where id=?""",
                            (generate_password_hash(password), _now(), reset["user_id"]))
                        conn.execute("update saas_password_resets set used_at=? where id=?", (_now(), reset["id"]))
                        conn.execute("update saas_password_resets set used_at=? where user_id=? and used_at=''",
                                     (_now(), reset["user_id"]))
                        audit(conn, "security.password_reset_completed", "user", reset["user_id"])
                        session.clear()
                        return redirect("/login")
                    error = "This reset link is invalid or expired."
        form = f"""<form method="post"><input type="hidden" name="token" value="{token}">
        <label>New password</label><input type="password" name="password" minlength="12" required>
        <button>Save new password</button></form>"""
        return render_template_string(AUTH_PAGE, title="Choose a new password",
            subtitle="Use at least 12 characters.", error=error, message="", form=form)

    @bp.get("/verify-email")
    def verify_email():
        token = request.args.get("token") or ""
        with connect() as conn:
            verification = conn.execute("""select * from saas_email_verifications
                where token_hash=? and used_at='' and expires_at>?""",
                (_hash_token(token), _now())).fetchone()
            if not verification:
                return render_template_string(AUTH_PAGE, title="Verification unavailable",
                    subtitle="Email verification links expire after 24 hours.",
                    error="This verification link is invalid, expired, or already used.",
                    message="", form='<div class="links"><a href="/resend-verification">Send a new link</a></div>'), 410
            conn.execute("update saas_users set email_verified_at=?,updated_at=? where id=?",
                         (_now(), _now(), verification["user_id"]))
            conn.execute("update saas_email_verifications set used_at=? where id=?",
                         (_now(), verification["id"]))
            g.user_id = verification["user_id"]
            audit(conn, "security.email_verified", "user", verification["user_id"])
        return redirect("/login")

    @bp.route("/resend-verification", methods=["GET", "POST"])
    def resend_verification():
        message = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            with connect() as conn:
                user = conn.execute("""select id,email from saas_users
                    where email=? and is_active=1 and email_verified_at=''""", (email,)).fetchone()
                if user:
                    create_verification(conn, user["id"], user["email"])
                    audit(conn, "security.email_verification_resent", "user", user["id"])
            message = "If that unverified account exists, a new verification link has been sent."
        form = """<form method="post"><label>Email</label><input type="email" name="email" required>
        <button>Send verification link</button></form><div class="links"><a href="/login">Back to sign in</a></div>"""
        return render_template_string(AUTH_PAGE, title="Verify your email",
            subtitle="Verification links expire after 24 hours.", error="", message=message, form=form)

    @bp.get("/api/saas/context")
    def context():
        with connect() as conn:
            user = dict(conn.execute("""select id,email,full_name,is_platform_owner,last_login_at
                from saas_users where id=?""", (g.user_id,)).fetchone())
            workspaces = [dict(row) for row in conn.execute("""select w.id,w.name,w.slug,w.plan,
                w.subscription_status,w.trial_ends_at,w.seat_limit,m.role
                from saas_workspaces w join saas_memberships m on m.workspace_id=w.id
                where m.user_id=? order by w.name""", (g.user_id,))]
        return jsonify(user=user, workspace_id=g.workspace_id, role=g.membership_role, workspaces=workspaces)

    @bp.get("/pricing")
    def pricing():
        form = """<div class="ok"><b>Starter</b><p>Up to 10 seats, 2,500 monthly AI-assisted actions,
        private workspace data, shared National Broker Index, and owner controls.</p></div>
        <div class="links"><a href="/register">Start 14-day trial</a><a href="/login">Sign in</a></div>"""
        return render_template_string(AUTH_PAGE, title="BrokerBeacon plans",
            subtitle="Start with one controlled pilot workspace. Upgrade only when the owner approves it.",
            error="", message="", form=form)

    @bp.get("/api/saas/billing")
    def billing_status():
        with connect() as conn:
            workspace = dict(conn.execute("""select id,name,plan,subscription_status,trial_ends_at,
                billing_customer_id,billing_subscription_id,seat_limit,is_founding
                from saas_workspaces where id=?""", (g.workspace_id,)).fetchone())
            seats = conn.execute("select count(*) from saas_memberships where workspace_id=?",
                                 (g.workspace_id,)).fetchone()[0]
            month = datetime.now().strftime("%Y-%m")
            usage = conn.execute("""select coalesce(sum(quantity),0) from saas_usage_events
                where workspace_id=? and event_type='ai_action' and substr(created_at,1,7)=?""",
                (g.workspace_id, month)).fetchone()[0]
        limits = PLAN_LIMITS.get(workspace["plan"], PLAN_LIMITS["Trial"])
        workspace.update(seats_used=seats, seat_limit=workspace["seat_limit"],
                         ai_actions_used=usage, ai_actions_limit=limits["monthly_ai_actions"],
                         stripe_configured=bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_PRICE_ID")))
        return jsonify(workspace)

    @bp.post("/api/saas/billing/checkout")
    @require_role("Owner")
    def billing_checkout():
        price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
        if not price_id:
            return jsonify(error="Billing checkout is not configured"), 503
        with connect() as conn:
            workspace = conn.execute("select * from saas_workspaces where id=?", (g.workspace_id,)).fetchone()
            owner = conn.execute("select email from saas_users where id=?", (g.user_id,)).fetchone()
        data = {
            "mode": "subscription", "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
            "success_url": request.url_root.rstrip("/")+"/?billing=success",
            "cancel_url": request.url_root.rstrip("/")+"/pricing?billing=cancelled",
            "client_reference_id": str(g.workspace_id), "metadata[workspace_id]": str(g.workspace_id),
            "customer_email": owner["email"], "allow_promotion_codes": "true",
        }
        if workspace["billing_customer_id"]:
            data.pop("customer_email", None)
            data["customer"] = workspace["billing_customer_id"]
        try:
            checkout = stripe_request("checkout/sessions", data)
        except Exception as exc:
            app.logger.exception("Unable to create Stripe Checkout session")
            return jsonify(error="Billing checkout is temporarily unavailable"), 502
        with connect() as conn:
            audit(conn, "billing.checkout_created", "workspace", g.workspace_id)
        return jsonify(url=checkout["url"]), 201

    @bp.post("/api/saas/billing/portal")
    @require_role("Owner")
    def billing_portal():
        with connect() as conn:
            workspace = conn.execute("select billing_customer_id from saas_workspaces where id=?",
                                     (g.workspace_id,)).fetchone()
        if not workspace["billing_customer_id"]:
            return jsonify(error="No billing account exists yet"), 409
        try:
            portal = stripe_request("billing_portal/sessions", {
                "customer": workspace["billing_customer_id"],
                "return_url": request.url_root.rstrip("/")+"/",
            })
        except Exception:
            app.logger.exception("Unable to create Stripe customer portal session")
            return jsonify(error="Billing portal is temporarily unavailable"), 502
        return jsonify(url=portal["url"]), 201

    @bp.post("/api/saas/billing/webhook")
    def billing_webhook():
        payload = request.get_data(cache=False)
        if not verify_stripe_signature(payload, request.headers.get("Stripe-Signature", "")):
            return jsonify(error="Invalid signature"), 400
        event = json.loads(payload)
        kind, item = event.get("type", ""), event.get("data", {}).get("object", {})
        with connect() as conn:
            if kind == "checkout.session.completed":
                workspace_id = int(item.get("client_reference_id") or item.get("metadata", {}).get("workspace_id") or 0)
                if workspace_id:
                    conn.execute("""update saas_workspaces set plan='Starter',subscription_status='active',
                        billing_customer_id=?,billing_subscription_id=?,billing_price_id=?,seat_limit=?,updated_at=?
                        where id=?""", (item.get("customer") or "", item.get("subscription") or "",
                        os.getenv("STRIPE_PRICE_ID", ""), PLAN_LIMITS["Starter"]["seats"], _now(), workspace_id))
                    g.workspace_id = workspace_id
                    audit(conn, "billing.subscription_activated", "workspace", workspace_id)
            elif kind == "customer.subscription.updated":
                subscription_id = item.get("id") or ""
                stripe_status = (item.get("status") or "").lower()
                status = {
                    "active": "active", "trialing": "trialing", "past_due": "past_due",
                    "unpaid": "unpaid", "paused": "paused", "canceled": "canceled",
                    "incomplete": "incomplete", "incomplete_expired": "canceled",
                }.get(stripe_status, stripe_status or "inactive")
                price_id = ""
                items = item.get("items", {}).get("data", [])
                if items:
                    price_id = items[0].get("price", {}).get("id") or ""
                conn.execute("""update saas_workspaces set subscription_status=?,
                    billing_price_id=coalesce(nullif(?,''),billing_price_id),updated_at=?
                    where billing_subscription_id=?""", (status, price_id, _now(), subscription_id))
            elif kind in {"customer.subscription.deleted", "customer.subscription.paused"}:
                subscription_id = item.get("id") or ""
                status = "paused" if kind.endswith(".paused") else "canceled"
                conn.execute("""update saas_workspaces set subscription_status=?,updated_at=?
                    where billing_subscription_id=?""", (status, _now(), subscription_id))
            elif kind in {"invoice.payment_failed", "invoice.paid"}:
                subscription_id = item.get("subscription") or ""
                if not subscription_id:
                    subscription_id = (item.get("parent", {}).get("subscription_details", {})
                                       .get("subscription") or "")
                if subscription_id:
                    status = "active" if kind == "invoice.paid" else "past_due"
                    conn.execute("""update saas_workspaces set subscription_status=?,updated_at=?
                        where billing_subscription_id=?""", (status, _now(), subscription_id))
        return jsonify(received=True)

    @bp.put("/api/saas/account")
    def update_account():
        name = ((request.get_json(silent=True) or {}).get("full_name") or "").strip()
        if not name:
            return jsonify(error="Name is required"), 400
        with connect() as conn:
            conn.execute("update saas_users set full_name=?,updated_at=? where id=?",
                         (name[:120], _now(), g.user_id))
            audit(conn, "account.updated", "user", g.user_id)
        return jsonify(ok=True, full_name=name[:120])

    @bp.post("/api/saas/workspace/switch")
    def switch_workspace():
        workspace_id = int((request.get_json(silent=True) or {}).get("workspace_id") or 0)
        with connect() as conn:
            member = conn.execute("select role from saas_memberships where user_id=? and workspace_id=?",
                                  (g.user_id, workspace_id)).fetchone()
            if not member:
                return jsonify(error="Workspace access denied"), 403
            session["workspace_id"] = workspace_id
            audit(conn, "workspace.switched", "workspace", workspace_id)
        return jsonify(ok=True, workspace_id=workspace_id)

    @bp.post("/api/saas/invitations")
    @require_role("Manager")
    def invite():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        role = data.get("role") or "AE"
        if "@" not in email or role not in ROLE_RANK or role == "Owner" and g.membership_role != "Owner":
            return jsonify(error="Valid email and permitted role required"), 400
        token = secrets.token_urlsafe(32)
        with connect() as conn:
            member = conn.execute("""select 1 from saas_memberships m join saas_users u on u.id=m.user_id
                where m.workspace_id=? and u.email=? collate nocase""", (g.workspace_id, email)).fetchone()
            if member:
                return jsonify(error="That person is already a workspace member"), 409
            workspace = conn.execute("select seat_limit from saas_workspaces where id=?", (g.workspace_id,)).fetchone()
            seats = conn.execute("select count(*) from saas_memberships where workspace_id=?", (g.workspace_id,)).fetchone()[0]
            if seats >= workspace["seat_limit"]:
                return jsonify(error="Workspace seat limit reached"), 409
            conn.execute("update saas_invitations set accepted_at=? where workspace_id=? and email=? and accepted_at=''",
                         (_now(), g.workspace_id, email))
            conn.execute("""insert into saas_invitations
                (workspace_id,email,role,token_hash,invited_by,expires_at,created_at)
                values(?,?,?,?,?,?,?)""", (g.workspace_id, email, role, _hash_token(token), g.user_id,
                (datetime.now()+timedelta(days=7)).isoformat(timespec="seconds"), _now()))
            audit(conn, "member.invited", "email", email)
        accept_url = request.url_root.rstrip("/") + "/invite/" + token
        delivered = deliver_security_email(email, "You’re invited to BrokerBeacon",
            "Your BrokerBeacon workspace owner invited you to join as "+role+".\n\n"+
            accept_url+"\n\nThis invitation expires in seven days.")
        response = {"ok": True, "email_delivered": delivered, "expires_in_days": 7}
        if app.config.get("TESTING"):
            response.update(invitation_token=token, accept_url=accept_url)
        return jsonify(response), 201

    @bp.get("/api/saas/members")
    @require_role("Manager")
    def members():
        with connect() as conn:
            rows = [dict(row) for row in conn.execute("""select u.id,u.email,u.full_name,
                u.last_login_at,u.is_active,m.role,m.created_at from saas_memberships m
                join saas_users u on u.id=m.user_id where m.workspace_id=?
                order by case m.role when 'Owner' then 1 when 'Manager' then 2
                when 'AE' then 3 else 4 end,u.full_name""", (g.workspace_id,))]
            pending = [dict(row) for row in conn.execute("""select id,email,role,expires_at,created_at
                from saas_invitations where workspace_id=? and accepted_at='' and expires_at>?
                order by id desc""", (g.workspace_id, _now()))]
        return jsonify(items=rows, pending_invitations=pending)

    @bp.put("/api/saas/members/<int:user_id>")
    @require_role("Owner")
    def update_member(user_id):
        role = (request.get_json(silent=True) or {}).get("role")
        if role not in ROLE_RANK:
            return jsonify(error="Valid role required"), 400
        with connect() as conn:
            target = conn.execute("select role from saas_memberships where workspace_id=? and user_id=?",
                                  (g.workspace_id, user_id)).fetchone()
            if not target:
                return jsonify(error="Member not found"), 404
            if user_id == g.user_id and target["role"] == "Owner" and role != "Owner":
                owners = conn.execute("select count(*) from saas_memberships where workspace_id=? and role='Owner'",
                                      (g.workspace_id,)).fetchone()[0]
                if owners == 1:
                    return jsonify(error="A workspace must retain at least one owner"), 409
            conn.execute("update saas_memberships set role=? where workspace_id=? and user_id=?",
                         (role, g.workspace_id, user_id))
            audit(conn, "member.role_updated", "user", user_id)
        return jsonify(ok=True, role=role)

    @bp.delete("/api/saas/members/<int:user_id>")
    @require_role("Owner")
    def remove_member(user_id):
        if user_id == g.user_id:
            return jsonify(error="You cannot remove yourself"), 409
        with connect() as conn:
            cur = conn.execute("delete from saas_memberships where workspace_id=? and user_id=?",
                               (g.workspace_id, user_id))
            if not cur.rowcount:
                return jsonify(error="Member not found"), 404
            audit(conn, "member.removed", "user", user_id)
        return jsonify(ok=True)

    @bp.get("/api/saas/audit")
    @require_role("Manager")
    def audit_log():
        with connect() as conn:
            rows = [dict(row) for row in conn.execute("""select id,user_id,action,target_type,
                target_id,detail_json,ip_address,created_at from saas_audit_log
                where workspace_id=? order by id desc limit 200""", (g.workspace_id,))]
        return jsonify(items=rows)

    @bp.get("/api/platform/security-audit")
    def platform_security_audit():
        with connect() as conn:
            rows = [dict(row) for row in conn.execute("""select a.id,a.workspace_id,a.user_id,
                a.action,a.target_type,a.target_id,a.detail_json,a.ip_address,a.created_at,
                w.name workspace_name,u.email user_email from saas_audit_log a
                left join saas_workspaces w on w.id=a.workspace_id
                left join saas_users u on u.id=a.user_id order by a.id desc limit 500""")]
        return jsonify(items=rows)

    @bp.get("/api/national-broker-index")
    def national_index():
        query = (request.args.get("search") or "").strip()
        state = (request.args.get("state") or "").strip().upper()
        where, params = ["1=1"], []
        if query:
            where.append("(company like ? or nmls like ?)")
            params += [f"%{query}%", f"%{query}%"]
        if state:
            where.append("state=?")
            params.append(state)
        with connect() as conn:
            rows = [dict(row) for row in conn.execute(f"""select id,nmls,company,city,state,
                source_name,source_url,verification_status,updated_at from national_broker_index
                where {' and '.join(where)} order by company limit 250""", params)]
        return jsonify(items=rows, shared=True)

    @bp.get("/api/platform/overview")
    def platform_overview():
        with connect() as conn:
            return jsonify(
                workspaces=conn.execute("select count(*) from saas_workspaces").fetchone()[0],
                users=conn.execute("select count(*) from saas_users").fetchone()[0],
                indexed_brokers=conn.execute("select count(*) from national_broker_index").fetchone()[0],
                trials=conn.execute("select count(*) from saas_workspaces where subscription_status='trialing'").fetchone()[0],
            )

    @bp.get("/api/platform/customers")
    def platform_customers():
        with connect() as conn:
            rows = [dict(row) for row in conn.execute("""select w.id,w.name,w.slug,w.plan,
                w.subscription_status,w.trial_ends_at,w.seat_limit,w.is_founding,w.created_at,
                count(m.id) seats_used,s.onboarding_completed_at,s.primary_market,s.primary_goal
                from saas_workspaces w left join saas_memberships m on m.workspace_id=w.id
                left join saas_workspace_settings s on s.workspace_id=w.id
                group by w.id order by w.id""")]
        return jsonify(items=rows)

    @bp.get("/api/platform/postgres-readiness")
    def platform_postgres_readiness():
        status = migration_status(db_path)
        status["rehearsal"] = rehearsal_status()
        if request.args.get("detail") == "1":
            status["plan"] = build_migration_plan(db_path, include_rows=False)
        return jsonify(status)

    @bp.put("/api/platform/customers/<int:workspace_id>")
    def platform_update_customer(workspace_id):
        data = request.get_json(silent=True) or {}
        status = data.get("subscription_status")
        plan = data.get("plan")
        if status not in {"active", "trialing", "paused", "canceled"} or plan not in PLAN_LIMITS:
            return jsonify(error="Valid plan and subscription status required"), 400
        limits = PLAN_LIMITS[plan]
        with connect() as conn:
            cur = conn.execute("""update saas_workspaces set plan=?,subscription_status=?,seat_limit=?,updated_at=?
                where id=? and is_founding=0""", (plan, status, limits["seats"], _now(), workspace_id))
            if not cur.rowcount:
                return jsonify(error="Customer workspace not found or protected"), 404
            audit(conn, "platform.customer_plan_updated", "workspace", workspace_id,
                  json.dumps({"plan": plan, "subscription_status": status}))
        return jsonify(ok=True, workspace_id=workspace_id, plan=plan, subscription_status=status)

    app.register_blueprint(bp)
