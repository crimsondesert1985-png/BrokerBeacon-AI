"""BrokerBeacon SaaS foundation: identity, tenancy, roles, and platform controls."""
from datetime import datetime, timedelta
from functools import wraps
import hashlib
from email.message import EmailMessage
import json
import os
import secrets
import smtplib
import sqlite3

from flask import Blueprint, g, jsonify, redirect, render_template_string, request, session
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash
from security_monitoring import emit_security_alert


ROLE_RANK = {"Read Only": 10, "AE": 20, "Manager": 30, "Owner": 40}
PUBLIC_PATHS = {"/login", "/register", "/forgot-password", "/reset-password", "/verify-email",
                "/resend-verification", "/health", "/api/version", "/demo"}
LOGIN_LIMIT = 5
LOGIN_WINDOW_MINUTES = 15
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
line-height:1.5}label{display:block;font-size:12px;font-weight:700;margin:16px 0 6px}input{
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
create index if not exists idx_saas_memberships_user on saas_memberships(user_id,workspace_id);
create index if not exists idx_saas_audit_workspace on saas_audit_log(workspace_id,id desc);
create index if not exists idx_saas_resets_user on saas_password_resets(user_id,created_at desc);
create index if not exists idx_saas_verifications_user on saas_email_verifications(user_id,created_at desc);
create index if not exists idx_workspace_brokers_workspace on workspace_broker_records(workspace_id,id);
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
                    return redirect("/")
                except sqlite3.IntegrityError:
                    error = "That email already has an account."
        form = """<form method="post"><label>Your name</label><input name="name" required>
        <label>Company</label><input name="company" required><label>Email</label>
        <input type="email" name="email" required><label>Password</label>
        <input type="password" name="password" minlength="12" required>
        <button>Create workspace</button></form><div class="links"><a href="/login">Sign in</a></div>"""
        return render_template_string(AUTH_PAGE, title="Create your workspace",
            subtitle="Start a secure, private BrokerBeacon company workspace.", error=error, message="", form=form)

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
        return jsonify(ok=True, invitation_token=token,
                       accept_url=request.url_root.rstrip("/") + "/invite/" + token,
                       expires_in_days=7), 201

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

    app.register_blueprint(bp)
