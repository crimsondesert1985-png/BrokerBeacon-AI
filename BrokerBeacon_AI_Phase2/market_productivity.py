"""Daily mortgage-market intelligence and approved-broker productivity for BrokerBeacon.

This module adds five connected capabilities without requiring a front-end rewrite:
1. Daily Bloomberg/CNBC mortgage-market headline aggregation.
2. Shared market context for outreach, drip campaigns, marketing, and sales coaching.
3. Approved-broker account/production tracking with 90-day dormancy alerts.
4. Opportunity Engine summary APIs and an actionable enhancement layer.
5. Prospect intelligence APIs plus a restored Intelligence button on detail pages.

The current BrokerBeacon application is Flask + SQLite, so this module follows the
existing architecture rather than introducing an unrelated React/Next.js stack.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime, timedelta, timezone

from flask import g, jsonify, request, Response


NEWS_QUERY = "mortgage OR housing OR home sales OR mortgage rates OR interest rates OR Federal Reserve"
NEWS_SOURCES = (
    ("Bloomberg", "bloomberg.com"),
    ("CNBC", "cnbc.com"),
)
NEWS_LIMIT_PER_SOURCE = 8
DORMANT_DAYS = 90
_USER_AGENT = "BrokerBeacon-MarketBrief/1.0 (+headline-links-only)"
_STARTED = False
_LOCK = threading.Lock()


SCHEMA = """
create table if not exists market_news_cache(
    id integer primary key,
    publisher text not null,
    title text not null,
    url text not null,
    summary text default '',
    published_at text default '',
    fetched_at text not null,
    cache_date text not null,
    unique(publisher,title,url)
);
create index if not exists idx_market_news_date on market_news_cache(cache_date,publisher,published_at desc);

create table if not exists approved_brokers(
    id integer primary key,
    workspace_id integer not null,
    external_account_id text default '',
    company_name text not null,
    nmls text default '',
    primary_contact_name text default '',
    primary_contact_email text default '',
    primary_contact_phone text default '',
    account_owner text default '',
    approved_at text default '',
    last_submission_at text default '',
    total_loans integer not null default 0,
    total_volume real not null default 0,
    status text not null default 'Approved',
    portal_source text default 'Manual / future portal sync',
    created_at text not null,
    updated_at text not null,
    unique(workspace_id,external_account_id)
);
create index if not exists idx_approved_brokers_workspace on approved_brokers(workspace_id,company_name);
create index if not exists idx_approved_brokers_last_submission on approved_brokers(workspace_id,last_submission_at);

create table if not exists approved_broker_production(
    id integer primary key,
    workspace_id integer not null,
    broker_id integer not null,
    loan_external_id text default '',
    submitted_at text not null,
    volume real not null default 0,
    loan_status text default 'Submitted',
    created_at text not null,
    unique(workspace_id,broker_id,loan_external_id)
);
create index if not exists idx_approved_broker_production on approved_broker_production(workspace_id,broker_id,submitted_at desc);

create table if not exists approved_broker_notifications(
    id integer primary key,
    workspace_id integer not null,
    broker_id integer not null,
    notification_type text not null,
    status text not null default 'Open',
    message text not null,
    created_at text not null,
    resolved_at text default '',
    unique(workspace_id,broker_id,notification_type,status)
);
create index if not exists idx_approved_broker_notifications on approved_broker_notifications(workspace_id,status,id desc);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().date().isoformat()


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _clean_text(value: str, limit: int = 1200) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _parse_feed_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return value[:80]


def _google_news_feed(publisher: str, domain: str, limit: int = NEWS_LIMIT_PER_SOURCE) -> list[dict]:
    # Google News is used only as a discovery/index layer. BrokerBeacon stores
    # headline metadata and outbound links, not publisher article bodies.
    query = f"({NEWS_QUERY}) site:{domain}"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml"})
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(2_000_000)
    root = ET.fromstring(raw)
    items = []
    for node in root.findall("./channel/item"):
        title = _clean_text(node.findtext("title") or "", 300)
        link = (node.findtext("link") or "").strip()
        summary = _clean_text(node.findtext("description") or "", 700)
        published = _parse_feed_date(node.findtext("pubDate") or "")
        if not title or not link:
            continue
        # Google titles commonly end in " - Bloomberg" / " - CNBC". Remove
        # that duplicated publisher suffix from the displayed headline.
        title = re.sub(rf"\s+-\s+{re.escape(publisher)}\s*$", "", title, flags=re.I).strip()
        items.append({
            "publisher": publisher,
            "title": title,
            "url": link,
            "summary": summary,
            "published_at": published,
        })
        if len(items) >= max(1, int(limit)):
            break
    return items


def refresh_market_news(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    today = _today()
    current = int(conn.execute("select count(*) from market_news_cache where cache_date=?", (today,)).fetchone()[0])
    if current and not force:
        return {"status": "cached", "date": today, "count": current, "errors": []}
    fetched_at = _now()
    collected, errors = [], []
    for publisher, domain in NEWS_SOURCES:
        try:
            collected.extend(_google_news_feed(publisher, domain))
        except Exception as exc:
            errors.append(f"{publisher}: {exc}")
    if collected:
        # Replace today's snapshot atomically; retain older dates briefly for
        # resilience and delete data older than one week.
        conn.execute("delete from market_news_cache where cache_date=?", (today,))
        for item in collected:
            conn.execute(
                """insert or ignore into market_news_cache
                   (publisher,title,url,summary,published_at,fetched_at,cache_date)
                   values(?,?,?,?,?,?,?)""",
                (item["publisher"], item["title"], item["url"], item["summary"], item["published_at"], fetched_at, today),
            )
        cutoff = (datetime.now().date() - timedelta(days=7)).isoformat()
        conn.execute("delete from market_news_cache where cache_date<?", (cutoff,))
        conn.commit()
    count = int(conn.execute("select count(*) from market_news_cache where cache_date=?", (today,)).fetchone()[0])
    return {"status": "refreshed" if collected else "stale", "date": today, "count": count, "errors": errors}


def market_news(conn: sqlite3.Connection, limit: int = 12) -> list[dict]:
    refresh_market_news(conn)
    today = _today()
    rows = conn.execute(
        """select publisher,title,url,summary,published_at,fetched_at
           from market_news_cache where cache_date=?
           order by case publisher when 'Bloomberg' then 0 else 1 end,published_at desc,id desc limit ?""",
        (today, max(1, min(int(limit), 30))),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """select publisher,title,url,summary,published_at,fetched_at
               from market_news_cache order by cache_date desc,published_at desc,id desc limit ?""",
            (max(1, min(int(limit), 30)),),
        ).fetchall()
    return [dict(row) for row in rows]


def build_market_context(conn: sqlite3.Connection) -> dict:
    items = market_news(conn, 10)
    top = items[:5]
    headlines = [f"{item['publisher']}: {item['title']}" for item in top]
    if headlines:
        lead = headlines[0]
        talking_point = (
            "Use today's market as a reason to be helpful, not alarmist. Ask how the broker is seeing "
            "borrower behavior and scenario mix, then connect the conversation to a specific way you can support them."
        )
        email_angle = f"Timely opener: {lead}. Keep it short, acknowledge the market movement, and offer scenario support rather than making a rate claim."
        call_angle = f"Call prep: reference {lead}, ask what it is changing for their pipeline, then listen for a scenario or product-support need."
        marketing_angle = f"Content angle: explain the practical broker impact behind {lead}; avoid predictions and unsupported rate/approval claims."
    else:
        talking_point = "No fresh Bloomberg/CNBC headline snapshot is available yet. Keep outreach evergreen and scenario-led."
        email_angle = "Lead with a useful scenario-support offer and avoid time-sensitive market claims until the news snapshot refreshes."
        call_angle = "Ask what is changing in the broker's pipeline today and listen for scenarios where you can help."
        marketing_angle = "Use educational, non-predictive mortgage content until the daily news snapshot refreshes."
    return {
        "date": _today(),
        "headlines": headlines,
        "items": items,
        "talking_point": talking_point,
        "email_angle": email_angle,
        "call_angle": call_angle,
        "marketing_angle": marketing_angle,
        "guardrail": "Verify licensing/contact details before relying on them. Do not make unsupported rate, approval, underwriting, or licensing claims.",
    }


def market_context_payload(db_path) -> dict:
    """Small lazy-import helper used by AI orchestration paths."""
    with closing(_connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        return build_market_context(conn)


def _parse_dt(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _broker_status(row: dict) -> dict:
    now = datetime.now()
    approved = _parse_dt(str(row.get("approved_at") or ""))
    last = _parse_dt(str(row.get("last_submission_at") or ""))
    anchor = last or approved
    days = (now - anchor).days if anchor else 0
    dormant = bool(anchor and days >= DORMANT_DAYS)
    status = "Dormant" if dormant else (str(row.get("status") or "Approved") or "Approved")
    if status.lower() == "dormant" and not dormant:
        status = "Approved"
    return {**row, "days_since_submission": (now - last).days if last else None, "days_since_activity_anchor": days if anchor else None, "dormant": dormant, "display_status": status}


def _sync_dormant_notifications(conn: sqlite3.Connection, workspace_id: int) -> int:
    rows = conn.execute("select * from approved_brokers where workspace_id=?", (workspace_id,)).fetchall()
    open_count = 0
    for raw in rows:
        row = _broker_status(dict(raw))
        if row["dormant"]:
            open_count += 1
            message = f"{row['company_name']} has had no submitted loans for at least {DORMANT_DAYS} days."
            exists = conn.execute(
                """select id from approved_broker_notifications
                   where workspace_id=? and broker_id=? and notification_type='Dormant' and status='Open' limit 1""",
                (workspace_id, row["id"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """insert into approved_broker_notifications
                       (workspace_id,broker_id,notification_type,status,message,created_at)
                       values(?,?,'Dormant','Open',?,?)""",
                    (workspace_id, row["id"], message, _now()),
                )
        else:
            conn.execute(
                """update approved_broker_notifications set status='Resolved',resolved_at=?
                   where workspace_id=? and broker_id=? and notification_type='Dormant' and status='Open'""",
                (_now(), workspace_id, row["id"]),
            )
    conn.commit()
    return open_count


def _approved_list(conn: sqlite3.Connection, workspace_id: int) -> dict:
    _sync_dormant_notifications(conn, workspace_id)
    rows = [_broker_status(dict(row)) for row in conn.execute(
        "select * from approved_brokers where workspace_id=? order by company_name", (workspace_id,)
    ).fetchall()]
    notifications = [dict(row) for row in conn.execute(
        """select n.*,b.company_name from approved_broker_notifications n
           join approved_brokers b on b.id=n.broker_id
           where n.workspace_id=? and n.status='Open' order by n.id desc""",
        (workspace_id,),
    ).fetchall()]
    total_volume = sum(float(row.get("total_volume") or 0) for row in rows)
    total_loans = sum(int(row.get("total_loans") or 0) for row in rows)
    dormant = sum(1 for row in rows if row["dormant"])
    return {
        "items": rows,
        "notifications": notifications,
        "summary": {
            "approved_accounts": len(rows),
            "active_accounts": len(rows) - dormant,
            "dormant_accounts": dormant,
            "loans_submitted": total_loans,
            "submitted_volume": total_volume,
        },
        "dormant_definition_days": DORMANT_DAYS,
        "portal_ready": True,
    }


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone())


def _prospect_intelligence(conn: sqlite3.Connection, prospect_id: int) -> dict | None:
    if not _table_exists(conn, "prospects"):
        return None
    prospect = conn.execute("select * from prospects where id=?", (prospect_id,)).fetchone()
    if not prospect:
        return None
    contacts = []
    if _table_exists(conn, "contacts"):
        cols = {str(row[1]) for row in conn.execute("pragma table_info(contacts)")}
        if "prospect_id" in cols:
            contacts = [dict(row) for row in conn.execute(
                "select * from contacts where prospect_id=? order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id",
                (prospect_id,),
            ).fetchall()]
    links = []
    if _table_exists(conn, "autonomous_prospect_links"):
        links = [dict(row) for row in conn.execute(
            "select * from autonomous_prospect_links where prospect_id=? order by warehouse_company_id", (prospect_id,)
        ).fetchall()]
    return {
        "prospect": dict(prospect),
        "contacts": contacts,
        "warehouse_links": links,
        "contact_count": len(contacts),
        "generated_at": _now(),
    }


def install_market_productivity(app, db_path):
    global _STARTED
    with closing(_connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()

    @app.get("/api/market-news")
    def api_market_news():
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            force = str(request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
            status = refresh_market_news(conn, force=force)
            return jsonify(items=market_news(conn, request.args.get("limit") or 12), **status)

    @app.get("/api/market-context")
    def api_market_context():
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            return jsonify(build_market_context(conn))

    @app.get("/api/market-content")
    def api_market_content():
        channel = str(request.args.get("channel") or "email").strip().lower()
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            context = build_market_context(conn)
        angle = {
            "email": context["email_angle"],
            "drip": context["email_angle"],
            "marketing": context["marketing_angle"],
            "call": context["call_angle"],
            "coach": context["call_angle"],
        }.get(channel, context["talking_point"])
        return jsonify(channel=channel, angle=angle, market_context=context)

    @app.get("/api/approved-brokers")
    def api_approved_brokers():
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            return jsonify(_approved_list(conn, workspace_id))

    @app.post("/api/approved-brokers")
    def api_upsert_approved_broker():
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        data = request.get_json(silent=True) or {}
        name = str(data.get("company_name") or "").strip()[:180]
        if not name:
            return jsonify(error="company_name is required"), 400
        external_id = str(data.get("external_account_id") or "").strip()[:120]
        now = _now()
        values = (
            workspace_id, external_id, name, str(data.get("nmls") or "")[:30],
            str(data.get("primary_contact_name") or "")[:160], str(data.get("primary_contact_email") or "")[:254],
            str(data.get("primary_contact_phone") or "")[:50], str(data.get("account_owner") or "")[:160],
            str(data.get("approved_at") or now)[:40], str(data.get("last_submission_at") or "")[:40],
            int(data.get("total_loans") or 0), float(data.get("total_volume") or 0),
            str(data.get("status") or "Approved")[:40], str(data.get("portal_source") or "Manual / future portal sync")[:120], now, now,
        )
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            if external_id:
                existing = conn.execute(
                    "select id from approved_brokers where workspace_id=? and external_account_id=?", (workspace_id, external_id)
                ).fetchone()
            else:
                existing = conn.execute(
                    "select id from approved_brokers where workspace_id=? and lower(company_name)=lower(?)", (workspace_id, name)
                ).fetchone()
            if existing:
                broker_id = int(existing[0])
                conn.execute(
                    """update approved_brokers set external_account_id=?,company_name=?,nmls=?,primary_contact_name=?,
                       primary_contact_email=?,primary_contact_phone=?,account_owner=?,approved_at=?,last_submission_at=?,
                       total_loans=?,total_volume=?,status=?,portal_source=?,updated_at=? where id=? and workspace_id=?""",
                    (external_id, name, values[3], values[4], values[5], values[6], values[7], values[8], values[9], values[10], values[11], values[12], values[13], now, broker_id, workspace_id),
                )
                created = False
            else:
                cur = conn.execute(
                    """insert into approved_brokers(workspace_id,external_account_id,company_name,nmls,primary_contact_name,
                       primary_contact_email,primary_contact_phone,account_owner,approved_at,last_submission_at,total_loans,total_volume,
                       status,portal_source,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values,
                )
                broker_id = int(cur.lastrowid)
                created = True
            conn.commit()
            _sync_dormant_notifications(conn, workspace_id)
        return jsonify(ok=True, broker_id=broker_id, created=created), 201 if created else 200

    @app.post("/api/approved-brokers/<int:broker_id>/production")
    def api_add_approved_broker_production(broker_id):
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        data = request.get_json(silent=True) or {}
        submitted_at = str(data.get("submitted_at") or _now())[:40]
        volume = max(0.0, float(data.get("volume") or 0))
        loan_id = str(data.get("loan_external_id") or "").strip()[:120]
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            broker = conn.execute("select id from approved_brokers where id=? and workspace_id=?", (broker_id, workspace_id)).fetchone()
            if not broker:
                return jsonify(error="Approved broker not found"), 404
            # Empty external IDs are made unique per event so manual entries do
            # not collide; real portal integrations should always send loan IDs.
            effective_loan_id = loan_id or f"manual-{broker_id}-{int(time.time() * 1000)}"
            try:
                conn.execute(
                    """insert into approved_broker_production(workspace_id,broker_id,loan_external_id,submitted_at,volume,loan_status,created_at)
                       values(?,?,?,?,?,?,?)""",
                    (workspace_id, broker_id, effective_loan_id, submitted_at, volume, str(data.get("loan_status") or "Submitted")[:60], _now()),
                )
            except sqlite3.IntegrityError:
                return jsonify(error="Production event already recorded"), 409
            conn.execute(
                """update approved_brokers set last_submission_at=?,total_loans=total_loans+1,total_volume=total_volume+?,
                   status='Approved',updated_at=? where id=? and workspace_id=?""",
                (submitted_at, volume, _now(), broker_id, workspace_id),
            )
            conn.commit()
            _sync_dormant_notifications(conn, workspace_id)
        return jsonify(ok=True, broker_id=broker_id, submitted_at=submitted_at, volume=volume), 201

    @app.get("/api/opportunity-engine/summary")
    def api_opportunity_summary():
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        with closing(_connect(db_path)) as conn:
            conn.executescript(SCHEMA)
            approved = _approved_list(conn, workspace_id)
            context = build_market_context(conn)
            prospect_total = contactable = high_priority = 0
            if _table_exists(conn, "prospects"):
                prospect_total = int(conn.execute("select count(*) from prospects").fetchone()[0])
                cols = {str(row[1]) for row in conn.execute("pragma table_info(prospects)")}
                if {"phone", "email"}.issubset(cols):
                    contactable = int(conn.execute(
                        "select count(*) from prospects where trim(coalesce(phone,''))<>'' or trim(coalesce(email,''))<>''"
                    ).fetchone()[0])
                if "score" in cols:
                    high_priority = int(conn.execute("select count(*) from prospects where coalesce(score,0)>=85").fetchone()[0])
            return jsonify(
                prospects={"total": prospect_total, "contactable": contactable, "high_priority": high_priority},
                approved_brokers=approved["summary"],
                market_context=context,
                portal_connection={"status": "Ready for adapter", "contract": "external account + loan submission IDs can be upserted through Approved Brokers APIs"},
            )

    @app.get("/api/prospects/<int:prospect_id>/intelligence")
    def api_prospect_intelligence(prospect_id):
        with closing(_connect(db_path)) as conn:
            data = _prospect_intelligence(conn, prospect_id)
        if not data:
            return jsonify(error="Prospect not found"), 404
        return jsonify(data)

    @app.get("/approved-brokers")
    def approved_brokers_page():
        return Response(APPROVED_BROKERS_HTML, mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.after_request
    def inject_market_productivity(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-market-productivity" in body or "</body>" not in body.lower():
            return response
        pos = body.lower().rfind("</body>")
        body = body[:pos] + MARKET_PRODUCTIVITY_SCRIPT + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    with _LOCK:
        if not _STARTED:
            _STARTED = True
            def refresh_loop():
                time.sleep(12)
                while True:
                    try:
                        with closing(_connect(db_path)) as conn:
                            conn.executescript(SCHEMA)
                            result = refresh_market_news(conn)
                            app.logger.warning("MARKET_NEWS daily_cache status=%s count=%s errors=%s", result["status"], result["count"], len(result["errors"]))
                    except Exception:
                        app.logger.exception("MARKET_NEWS refresh failed safely")
                    time.sleep(6 * 3600)
            threading.Thread(target=refresh_loop, name="market-news-refresh", daemon=True).start()
    app.logger.warning("MARKET_PRODUCTIVITY installed daily news, approved broker dormancy, opportunity summary, and prospect intelligence")
    return app


APPROVED_BROKERS_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Approved Brokers · BrokerBeacon</title><style>
:root{--b:#07162e;--p:#0d2347;--card:#fff;--ink:#17283d;--muted:#6d7d91;--line:#dfe8f3;--red:#b42336;--green:#17745a;--blue:#174ea6}*{box-sizing:border-box}body{margin:0;background:#f4f8fc;color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}header{padding:20px 28px;background:var(--b);color:white;display:flex;justify-content:space-between;align-items:center}header a{color:#9ed8ff;text-decoration:none}.wrap{max-width:1250px;margin:auto;padding:26px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px}.metric,.panel{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 24px #19365d0c}.metric{padding:16px}.metric b{display:block;font-size:24px;margin-top:4px}.muted{color:var(--muted)}.panel{padding:18px;margin-bottom:16px}.panel h2{margin:0 0 5px;font-size:18px}.toolbar{display:flex;gap:8px;margin:12px 0}input,button{padding:10px 11px;border:1px solid var(--line);border-radius:9px;background:white}input{flex:1}button{cursor:pointer;background:var(--blue);color:white;border-color:var(--blue)}table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:10px;text-transform:uppercase;color:var(--muted)}.status{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:10px;font-weight:800}.active{background:#e7f7f0;color:var(--green)}.dormant{background:#fdecef;color:var(--red)}.alert{padding:10px 12px;border-radius:10px;background:#fff1f3;color:#8e2635;margin-top:8px}.empty{padding:30px;text-align:center;color:var(--muted)}@media(max-width:900px){.metrics{grid-template-columns:1fr 1fr}.tablewrap{overflow:auto}}
</style></head><body><header><div><strong>BrokerBeacon</strong><div>Approved Brokers</div></div><a href="/">Back to workspace</a></header><main class="wrap"><section class="metrics" id="metrics"></section><section class="panel"><h2>Approved broker accounts</h2><div class="muted">Production-ready structure for a future loan-portal connection. Accounts are flagged dormant after 90 days with no submitted loans.</div><div class="toolbar"><input id="q" placeholder="Search approved brokers"><button id="refresh">Refresh</button></div><div id="alerts"></div><div class="tablewrap"><table><thead><tr><th>Account</th><th>Primary contact</th><th>Production</th><th>Last submission</th><th>Status</th><th>Owner</th></tr></thead><tbody id="rows"></tbody></table></div></section><section class="panel"><h2>Loan portal connection contract</h2><div class="muted">When your company's portal is connected, sync approved accounts into <code>POST /api/approved-brokers</code>, then post every submitted loan to <code>POST /api/approved-brokers/&lt;id&gt;/production</code>. Dormancy and notifications recalculate automatically.</div></section></main><script>
let data={items:[],summary:{},notifications:[]};const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(n||0));const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function render(){const s=data.summary||{};document.getElementById('metrics').innerHTML=[['Approved',s.approved_accounts],['Active',s.active_accounts],['Dormant',s.dormant_accounts],['Loans',s.loans_submitted],['Volume',money(s.submitted_volume)]].map(x=>`<div class="metric"><span class="muted">${x[0]}</span><b>${x[1]??0}</b></div>`).join('');document.getElementById('alerts').innerHTML=(data.notifications||[]).map(n=>`<div class="alert"><strong>Dormant account:</strong> ${esc(n.company_name)} · ${esc(n.message)}</div>`).join('');const q=document.getElementById('q').value.trim().toLowerCase();const items=(data.items||[]).filter(x=>!q||String(x.company_name).toLowerCase().includes(q)||String(x.nmls||'').includes(q));document.getElementById('rows').innerHTML=items.length?items.map(x=>`<tr><td><strong>${esc(x.company_name)}</strong><div class="muted">NMLS ${esc(x.nmls||'—')}</div></td><td>${esc(x.primary_contact_name||'—')}<div class="muted">${esc([x.primary_contact_phone,x.primary_contact_email].filter(Boolean).join(' · '))}</div></td><td><strong>${x.total_loans||0} loans</strong><div class="muted">${money(x.total_volume)}</div></td><td>${esc(x.last_submission_at||'No submissions yet')}</td><td><span class="status ${x.dormant?'dormant':'active'}">${x.dormant?'Dormant':'Approved'}</span>${x.days_since_submission!=null?`<div class="muted">${x.days_since_submission} days ago</div>`:''}</td><td>${esc(x.account_owner||'—')}</td></tr>`).join(''):`<tr><td colspan="6" class="empty">No approved broker accounts are loaded yet. The page is ready for your company's portal feed.</td></tr>`}async function load(){const r=await fetch('/api/approved-brokers');data=await r.json();render()}document.getElementById('q').oninput=render;document.getElementById('refresh').onclick=load;load();
</script></body></html>'''


MARKET_PRODUCTIVITY_SCRIPT = r'''<style id="brokerbeacon-market-productivity-style">
#bb-market-news{margin:18px 0;padding:18px;border:1px solid #dce7f4;border-radius:16px;background:linear-gradient(135deg,#fff,#f5f9ff);box-shadow:0 12px 34px #17365f10;color:#17283d}#bb-market-news h2{margin:0 0 4px;font-size:18px}#bb-market-news .bbmn-sub{color:#65758b;font-size:12px;margin-bottom:12px}.bbmn-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.bbmn-item{display:block;text-decoration:none;color:#17283d;border:1px solid #e2eaf4;background:white;border-radius:11px;padding:11px}.bbmn-item:hover{border-color:#9bbbe0}.bbmn-source{font-size:9px;font-weight:900;text-transform:uppercase;color:#174ea6;letter-spacing:.08em}.bbmn-title{font-weight:750;margin-top:4px;line-height:1.35}.bb-market-chip{display:inline-flex;padding:5px 8px;border-radius:999px;background:#174ea611;color:#174ea6;font-size:10px;font-weight:800}.bb-market-context{margin:14px 0;padding:14px;border:1px solid #dce7f4;border-radius:13px;background:#f7fbff;color:#17283d}.bb-market-context strong{display:block;margin-bottom:5px}.bb-market-context button{margin-top:8px;border:0;border-radius:8px;background:#174ea6;color:white;padding:8px 10px;cursor:pointer}#bb-intelligence-btn{position:fixed;right:22px;bottom:22px;z-index:320;border:0;border-radius:999px;padding:12px 16px;background:linear-gradient(135deg,#174ea6,#6a55ee);color:white;font-weight:850;box-shadow:0 14px 32px #123c7b4f;cursor:pointer}#bb-intel-backdrop{position:fixed;inset:0;background:#07111dcc;z-index:370;display:none}#bb-intel-modal{position:fixed;z-index:380;inset:5vh 5vw;background:white;color:#17283d;border-radius:18px;display:none;overflow:auto;box-shadow:0 28px 80px #0008}#bb-intel-modal.open,#bb-intel-backdrop.open{display:block}.bbintel-head{position:sticky;top:0;background:#0d2347;color:white;padding:17px 20px;display:flex;justify-content:space-between;align-items:center}.bbintel-body{padding:18px}.bbintel-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.bbintel-card{border:1px solid #dfe8f3;border-radius:12px;padding:13px}.bbintel-card h3{margin:0 0 8px}.bbintel-dl{display:grid;grid-template-columns:minmax(130px,180px) 1fr;gap:6px 10px;font-size:12px}.bbintel-dl b{color:#65758b}.bb-opportunity-command{margin:14px 0;padding:15px;border:1px solid #dbe7f5;border-radius:14px;background:linear-gradient(135deg,#f8fbff,#eef6ff);color:#17283d}.bb-opportunity-command .metrics{display:flex;gap:12px;flex-wrap:wrap;margin-top:9px}.bb-opportunity-command .metric{background:white;border:1px solid #dce7f3;border-radius:9px;padding:8px 10px}.bb-approved-nav{white-space:nowrap}@media(max-width:760px){.bbmn-grid,.bbintel-grid{grid-template-columns:1fr}#bb-intel-modal{inset:2vh 2vw}.bbintel-dl{grid-template-columns:1fr}}
</style><div id="bb-intel-backdrop"></div><section id="bb-intel-modal" aria-label="Prospect Intelligence"><div class="bbintel-head"><div><strong>Account Intelligence</strong><div style="font-size:11px;opacity:.75">All available account and contact data</div></div><button id="bb-intel-close" style="background:#ffffff18;color:white;border:1px solid #ffffff33;border-radius:8px;padding:8px 10px">Close</button></div><div id="bb-intel-body" class="bbintel-body">Loading…</div></section><script id="brokerbeacon-market-productivity">(function(){
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const txt=e=>(e&&e.textContent||'').replace(/\s+/g,' ').trim();
function addApprovedNav(){const nav=document.querySelector('.bb-legacy-list')||document.querySelector('aside nav')||document.querySelector('aside');if(!nav||document.getElementById('bb-approved-brokers-nav'))return;const b=document.createElement('button');b.id='bb-approved-brokers-nav';b.className='bb-approved-nav';b.type='button';b.textContent='Approved Brokers';b.title='Track approved accounts, production, and 90-day dormancy.';b.onclick=()=>location.href='/approved-brokers';nav.appendChild(b)}
async function market(){try{const r=await fetch('/api/market-context'),j=await r.json();window.BrokerBeaconMarketContext=j;return j}catch(e){return null}}
function dashboardHost(){if(location.pathname!='/')return null;return document.querySelector('main')||document.querySelector('.container')||document.body}
async function addNews(){const host=dashboardHost();if(!host||document.getElementById('bb-market-news'))return;const j=await market();if(!j)return;const box=document.createElement('section');box.id='bb-market-news';box.innerHTML=`<div class="bb-market-chip">Daily mortgage market brief</div><h2>Mortgage Market News</h2><div class="bbmn-sub">Latest relevant Bloomberg and CNBC headlines · refreshed daily</div><div class="bbmn-grid">${(j.items||[]).slice(0,8).map(x=>`<a class="bbmn-item" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer"><div class="bbmn-source">${esc(x.publisher)}</div><div class="bbmn-title">${esc(x.title)}</div></a>`).join('')||'<div class="bbmn-item">News snapshot is refreshing.</div>'}</div>`;host.prepend(box)}
function isOutreachPage(){const path=location.pathname.toLowerCase();const body=txt(document.body).toLowerCase().slice(0,12000);return /marketing|campaign|drip|coach|call prep|email/.test(path+' '+body)}
async function addMarketContext(){if(!isOutreachPage()||document.getElementById('bb-market-context'))return;const j=window.BrokerBeaconMarketContext||await market();if(!j)return;const host=document.querySelector('main')||document.querySelector('.wrap')||document.body;const box=document.createElement('section');box.id='bb-market-context';box.className='bb-market-context';box.innerHTML=`<strong>Today's Market Angle</strong><div>${esc(j.talking_point)}</div><div style="margin-top:6px;color:#65758b;font-size:11px">${esc(j.headlines?.[0]||'Market snapshot refreshing')}</div><button type="button">Copy timely outreach angle</button>`;box.querySelector('button').onclick=async()=>{const value=j.email_angle+'\n\n'+j.guardrail;try{await navigator.clipboard.writeText(value);box.querySelector('button').textContent='Copied'}catch(e){}};host.prepend(box)}
async function addOpportunity(){const body=txt(document.body);if(!/Opportunity Engine/i.test(body)||document.getElementById('bb-opportunity-command'))return;try{const r=await fetch('/api/opportunity-engine/summary'),j=await r.json();const host=document.querySelector('main')||document.querySelector('.wrap')||document.body;const box=document.createElement('section');box.id='bb-opportunity-command';box.className='bb-opportunity-command';box.innerHTML=`<strong>Opportunity Engine · Action Center</strong><div style="margin-top:4px;color:#65758b">Tie prospect priority, approved-account production, dormancy, and today's market into one next-action view.</div><div class="metrics"><div class="metric"><b>${j.prospects?.high_priority||0}</b><div>High-priority prospects</div></div><div class="metric"><b>${j.prospects?.contactable||0}</b><div>Contactable prospects</div></div><div class="metric"><b>${j.approved_brokers?.dormant_accounts||0}</b><div>Dormant approved accounts</div></div></div><div style="margin-top:9px"><span class="bb-market-chip">Portal-ready</span> <span style="font-size:11px;color:#65758b">${esc(j.portal_connection?.contract||'')}</span></div>`;host.prepend(box)}catch(e){}}
function prospectId(){let m=location.pathname.match(/\/prospects?\/(\d+)(?:\/|$)/i);if(m)return m[1];const el=document.querySelector('[data-prospect-id]');return el&&el.getAttribute('data-prospect-id')}
function renderPairs(obj){return `<div class="bbintel-dl">${Object.entries(obj||{}).filter(([k,v])=>v!==null&&v!==''&&typeof v!=='object').map(([k,v])=>`<b>${esc(k.replace(/_/g,' '))}</b><span>${esc(v)}</span>`).join('')}</div>`}
function addIntelligence(){const id=prospectId();if(!id||document.getElementById('bb-intelligence-btn'))return;const b=document.createElement('button');b.id='bb-intelligence-btn';b.type='button';b.textContent='Intelligence';b.onclick=async()=>{document.getElementById('bb-intel-backdrop').classList.add('open');document.getElementById('bb-intel-modal').classList.add('open');const body=document.getElementById('bb-intel-body');body.textContent='Loading account intelligence…';try{const r=await fetch('/api/prospects/'+id+'/intelligence'),j=await r.json();if(!r.ok)throw new Error(j.error||'Unable to load intelligence');const d=j;body.innerHTML=`<div class="bbintel-grid"><section class="bbintel-card"><h3>Account</h3>${renderPairs(d.prospect)}</section><section class="bbintel-card"><h3>Contacts (${d.contact_count||0})</h3>${(d.contacts||[]).map((c,i)=>`<div style="padding:9px 0;border-bottom:1px solid #e7edf5"><strong>${esc(c.name||('Contact '+(i+1)))}</strong>${renderPairs(c)}</div>`).join('')||'<div>No associated contacts are stored yet.</div>'}</section></div>`}catch(e){body.textContent=e.message}};document.body.appendChild(b)}
function closeIntel(){document.getElementById('bb-intel-backdrop').classList.remove('open');document.getElementById('bb-intel-modal').classList.remove('open')}document.getElementById('bb-intel-close').onclick=closeIntel;document.getElementById('bb-intel-backdrop').onclick=closeIntel;
async function init(){addApprovedNav();addIntelligence();await addNews();await addMarketContext();await addOpportunity()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();new MutationObserver(()=>{addApprovedNav();addIntelligence()}).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''


__all__ = ["install_market_productivity", "market_context_payload", "build_market_context"]
