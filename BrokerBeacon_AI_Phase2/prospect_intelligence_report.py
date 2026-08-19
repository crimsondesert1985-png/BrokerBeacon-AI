"""Loan-officer-first Prospect Detail experience for BrokerBeacon."""
from __future__ import annotations

import html
import sqlite3
from contextlib import closing

from flask import Response, g


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _text(value) -> str:
    return str(value or "").strip()


def _esc(value) -> str:
    return html.escape(_text(value))


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute("select 1 from sqlite_master where type='table' and name=?", (name,)).fetchone())


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _first(record: dict, *names: str) -> str:
    for name in names:
        value = _text(record.get(name))
        if value:
            return value
    return ""


def _phone_href(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit() or ch == "+")


def _phones(contact: dict) -> list[tuple[str, str]]:
    values, seen = [], set()
    for label, field in (("Mobile", "mobile_phone"), ("Direct", "direct_phone"), ("Phone", "phone"), ("Office", "office_phone")):
        value = _text(contact.get(field))
        normalized = _phone_href(value)
        if value and normalized and normalized not in seen:
            seen.add(normalized)
            values.append((label, value))
    return values


def _emails(contact: dict) -> list[str]:
    values, seen = [], set()
    for field in ("email", "public_email", "work_email"):
        value = _text(contact.get(field))
        normalized = value.lower()
        if value and normalized not in seen:
            seen.add(normalized)
            values.append(value)
    return values


def _format_volume(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    if number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.1f}B"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"${number / 1_000:.0f}K"
    return f"${number:,.0f}"


def _extra_contact_details(contact: dict) -> list[tuple[str, str]]:
    hidden = {
        "id", "prospect_id", "name", "full_name", "contact_name", "title", "job_title", "role",
        "phone", "mobile_phone", "direct_phone", "office_phone", "email", "public_email", "work_email",
        "nmls", "nmls_id", "license_number", "city", "state", "is_primary", "is_decision_maker",
        "created_at", "updated_at",
    }
    values = []
    for key, value in contact.items():
        if key in hidden or value in (None, "", False) or isinstance(value, (dict, list, tuple)):
            continue
        values.append((key.replace("_", " ").title(), _text(value)))
    return values


def _contact_row(contact: dict, metrics: dict, index: int) -> str:
    name = _first(contact, "name", "full_name", "contact_name") or f"Contact {index}"
    title = _first(contact, "title", "job_title", "role") or "Loan Officer / Brokerage Contact"
    nmls = _first(contact, "nmls", "nmls_id", "license_number")
    location = ", ".join(v for v in (_first(contact, "city"), _first(contact, "state")) if v)
    phones = _phones(contact)
    emails = _emails(contact)

    badges = []
    if bool(contact.get("is_primary")):
        badges.append('<span class="badge primary">Primary</span>')
    if bool(contact.get("is_decision_maker")):
        badges.append('<span class="badge decision">Decision maker</span>')
    if nmls:
        badges.append(f'<span class="badge">NMLS {_esc(nmls)}</span>')

    phone_html = "".join(
        f'<a class="contact-channel" href="tel:{_esc(_phone_href(phone))}"><span>{_esc(label)}</span><strong>{_esc(phone)}</strong><em>Call</em></a>'
        for label, phone in phones
    ) or '<div class="contact-channel unavailable"><span>Phone</span><strong>Not available</strong></div>'
    email_html = "".join(
        f'<a class="contact-channel" href="mailto:{_esc(email)}"><span>Email</span><strong>{_esc(email)}</strong><em>Email</em></a>'
        for email in emails
    ) or '<div class="contact-channel unavailable"><span>Email</span><strong>Not available</strong></div>'

    extras = "".join(
        f'<div><b>{_esc(label)}</b><span>{_esc(value)}</span></div>'
        for label, value in _extra_contact_details(contact)
    )
    extra_html = f'<details class="more-contact"><summary>More contact details</summary><div class="extra-grid">{extras}</div></details>' if extras else ""

    last_contacted = _text(metrics.get("last_contacted_at")) or "—"
    production_volume = _format_volume(metrics.get("production_volume"))
    production_units = _text(metrics.get("production_units")) or "—"
    production_period = _text(metrics.get("production_period")) or "Production units"

    return f'''<article class="loan-officer">
      <section class="identity"><div class="avatar">{_esc(name[:1].upper())}</div><div><div class="name-line"><h2>{_esc(name)}</h2><div class="badges">{''.join(badges)}</div></div><div class="role">{_esc(title)}</div>{f'<div class="location">{_esc(location)}</div>' if location else ''}</div></section>
      <section class="communication"><div class="label">Contact</div><div class="channels">{phone_html}{email_html}</div></section>
      <section class="context"><div><span>Last contacted</span><strong>{_esc(last_contacted)}</strong></div><div><span>Production</span><strong>{_esc(production_volume)}</strong><small>{_esc(_text(metrics.get("production_period")) or "Volume")}</small></div><div><span>Units</span><strong>{_esc(production_units)}</strong><small>{_esc(production_period)}</small></div></section>
      {extra_html}
    </article>'''


def install_prospect_intelligence_report(app, db_path):
    # Framework for future activity and production data. The page works even before this table has rows.
    try:
        with closing(_connect(db_path)) as conn:
            conn.execute(
                """create table if not exists contact_sales_metrics(
                    id integer primary key,
                    contact_id integer not null unique,
                    last_contacted_at text default '',
                    production_volume real,
                    production_units integer,
                    production_period text default '',
                    updated_at text default '',
                    foreign key(contact_id) references contacts(id)
                )"""
            )
    except sqlite3.Error as exc:
        app.logger.warning("PROSPECT_DETAIL metrics table unavailable: %s", exc)

    @app.get("/prospects/<int:prospect_id>/intelligence-report")
    def prospect_intelligence_report(prospect_id: int):
        with closing(_connect(db_path)) as conn:
            if not _table_exists(conn, "prospects"):
                return Response("Prospects are not initialized.", status=404, mimetype="text/plain")
            row = conn.execute("select * from prospects where id=?", (prospect_id,)).fetchone()
            if not row:
                return Response("Prospect not found.", status=404, mimetype="text/plain")
            account = dict(row)

            contacts = []
            if _table_exists(conn, "contacts") and "prospect_id" in _columns(conn, "contacts"):
                contacts = [dict(item) for item in conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id""",
                    (prospect_id,),
                ).fetchall()]

            metrics_by_contact = {}
            if _table_exists(conn, "contact_sales_metrics") and "contact_id" in _columns(conn, "contact_sales_metrics"):
                ids = [item.get("id") for item in contacts if item.get("id")]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    rows = conn.execute(
                        f"select * from contact_sales_metrics where contact_id in ({placeholders})", ids
                    ).fetchall()
                    metrics_by_contact = {item["contact_id"]: dict(item) for item in rows}

        company = _first(account, "company", "company_name", "legal_name") or f"Prospect {prospect_id}"
        nmls = _first(account, "nmls", "nmls_id")
        location = ", ".join(v for v in (_first(account, "city"), _first(account, "state")) if v)
        status = _first(account, "status", "pipeline_status") or "New"
        score = _first(account, "score", "opportunity_score")
        source = _first(account, "source_name", "source")

        contact_rows = "".join(
            _contact_row(contact, metrics_by_contact.get(contact.get("id"), {}), index + 1)
            for index, contact in enumerate(contacts)
        ) or '<section class="empty"><h2>No individual loan officers are stored yet</h2><p>BrokerBeacon is still enriching this brokerage.</p></section>'

        account_meta = "".join(
            f'<div><b>{_esc(label)}</b><span>{_esc(value)}</span></div>'
            for label, value in (("NMLS", nmls), ("Location", location), ("Opportunity score", score), ("Pipeline status", status), ("Source", source))
            if value
        )
        raw_rows = "".join(
            f'<div><b>{_esc(key.replace("_", " ").title())}</b><span>{_esc(value)}</span></div>'
            for key, value in account.items()
            if value not in (None, "") and not isinstance(value, (dict, list, tuple))
        )

        body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(company)} · BrokerBeacon</title><style>
:root{{--navy:#07162e;--navy2:#102b52;--blue:#225be6;--ink:#15283f;--muted:#718197;--line:#dce5ef;--bg:#f5f8fc;--green:#08765b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}}.topbar{{background:linear-gradient(135deg,var(--navy),var(--navy2));color:white}}.topbar-inner{{max-width:1260px;margin:auto;padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:14px}}.topbar a,.topbar button{{color:#e9f1ff;text-decoration:none;border:1px solid #ffffff24;background:#ffffff0d;border-radius:9px;padding:7px 9px;font:inherit;font-size:11px;font-weight:750;cursor:pointer}}.nav{{display:flex;gap:6px;flex-wrap:wrap}}.page{{max-width:1260px;margin:auto;padding:22px 22px 60px}}.account{{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:17px}}.eyebrow{{color:#537eaf;font-size:10px;font-weight:900;letter-spacing:.12em;text-transform:uppercase}}h1{{margin:4px 0 5px;font-size:29px}}.meta-line{{color:var(--muted);font-size:12px}}.meta-line span+span:before{{content:' · '}}.count{{padding:7px 10px;border-radius:999px;background:#e8f7f1;color:var(--green);font-size:11px;font-weight:900;white-space:nowrap}}.intro{{margin-bottom:10px}}.intro h2{{margin:0;font-size:21px}}.intro p{{margin:3px 0 0;color:var(--muted);font-size:12px}}.list{{display:grid;gap:10px}}.loan-officer{{background:white;border:1px solid var(--line);border-radius:15px;padding:16px;display:grid;grid-template-columns:minmax(230px,.9fr) minmax(360px,1.45fr) minmax(260px,.85fr);gap:18px;align-items:start;box-shadow:0 5px 18px #14325009}}.identity{{display:flex;gap:11px;min-width:0}}.avatar{{width:42px;height:42px;flex:0 0 42px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#e8f0ff;color:#2558a4;font-weight:900;font-size:16px}}.name-line{{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}}.name-line h2{{margin:0;font-size:17px}}.role{{margin-top:4px;color:#53657a;font-size:12px}}.location{{margin-top:4px;color:var(--muted);font-size:11px}}.badges{{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end}}.badge{{padding:3px 6px;border-radius:999px;background:#eef2f6;color:#526174;font-size:8px;font-weight:900;white-space:nowrap}}.badge.primary{{background:#e8f7f1;color:var(--green)}}.badge.decision{{background:#fff3da;color:#8a5b00}}.label{{margin-bottom:6px;color:var(--muted);font-size:9px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}}.channels{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}}.contact-channel{{display:block;min-width:0;padding:10px 11px;background:#f8fbff;border:1px solid #d8e4f2;border-radius:10px;color:var(--ink);text-decoration:none}}.contact-channel:hover{{background:#eef4ff;border-color:#87ace2}}.contact-channel span{{display:block;color:var(--muted);font-size:8px;font-weight:900;text-transform:uppercase}}.contact-channel strong{{display:block;margin-top:3px;font-size:13px;overflow-wrap:anywhere}}.contact-channel em{{display:block;margin-top:5px;color:var(--blue);font-size:9px;font-style:normal;font-weight:900}}.contact-channel.unavailable{{opacity:.48}}.context{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}}.context>div{{padding:10px;border-radius:10px;background:#fafbfd;border:1px solid #e3e9f0}}.context span{{display:block;color:var(--muted);font-size:8px;font-weight:900;text-transform:uppercase}}.context strong{{display:block;margin-top:5px;font-size:14px}}.context small{{display:block;margin-top:2px;color:#8794a5;font-size:9px}}.more-contact{{grid-column:1/-1;margin-top:-4px}}summary{{cursor:pointer;color:var(--blue);font-weight:800}}.extra-grid,.account-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:9px}}.extra-grid>div,.account-grid>div{{border-top:1px solid var(--line);padding-top:7px}}.extra-grid b,.account-grid b{{display:block;color:var(--muted);font-size:8px;text-transform:uppercase}}.extra-grid span,.account-grid span{{display:block;margin-top:3px;font-size:11px;overflow-wrap:anywhere}}.secondary{{margin-top:27px;border-top:1px solid #dbe3ed;padding-top:18px}}.secondary h2{{margin:0 0 10px;font-size:16px}}.tools{{display:flex;gap:7px;flex-wrap:wrap}}.tools a,.tools button{{padding:8px 10px;border-radius:9px;background:white;border:1px solid var(--line);color:#42546b;text-decoration:none;font:inherit;font-size:11px;font-weight:750;cursor:pointer}}.account-summary{{margin-top:13px;background:white;border:1px solid var(--line);border-radius:13px;padding:13px}}.verify{{margin-top:16px;color:#7b8797;font-size:10px}}.empty{{background:white;border:1px dashed #b9c7d8;border-radius:14px;padding:24px;color:var(--muted)}}@media(max-width:1050px){{.loan-officer{{grid-template-columns:minmax(220px,.8fr) minmax(330px,1.2fr)}}.context{{grid-column:1/-1}}}}@media(max-width:720px){{.loan-officer{{grid-template-columns:1fr}}.context{{grid-column:auto}}.channels{{grid-template-columns:1fr}}.account{{align-items:flex-start;flex-direction:column}}.extra-grid,.account-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:480px){{.page{{padding:18px 13px 45px}}.topbar-inner{{align-items:flex-start;flex-direction:column}}h1{{font-size:23px}}.context,.extra-grid,.account-grid{{grid-template-columns:1fr}}}}
</style></head><body><header class="topbar"><div class="topbar-inner"><a href="/prospects/catalog">← Prospects</a><nav class="nav"><a href="/">Home</a><a href="/prospects/{prospect_id}/contact-prep">Contact Prep</a><button data-tool="notes">Notes</button><button data-tool="marketing">Marketing</button><button data-tool="sales coach">Sales Coach</button><button data-tool="opportunity">Opportunities</button><a href="/intelligence/scenario-rescue">BeaconMatch</a></nav></div></header><main class="page"><section class="account"><div><div class="eyebrow">Prospect</div><h1>{_esc(company)}</h1><div class="meta-line">{f'<span>NMLS {_esc(nmls)}</span>' if nmls else ''}{f'<span>{_esc(location)}</span>' if location else ''}{f'<span>Status: {_esc(status)}</span>' if status else ''}</div></div><div class="count">{len(contacts)} loan officer{'' if len(contacts)==1 else 's'}</div></section><section><div class="intro"><h2>Loan Officers</h2><p>Call or email the right person without hunting through account data.</p></div><div class="list">{contact_rows}</div></section><section class="secondary"><h2>Account tools</h2><nav class="tools"><a href="/prospects/{prospect_id}/contact-prep">Contact Prep</a><button data-tool="notes">Notes</button><button data-tool="marketing">Marketing</button><button data-tool="sales coach">Sales Coach</button><button data-tool="opportunity">Opportunities</button><a href="/intelligence/scenario-rescue">BeaconMatch</a></nav><details class="account-summary"><summary>Brokerage intelligence</summary><div class="account-grid">{account_meta}</div></details><details class="account-summary"><summary>All stored account data</summary><div class="account-grid">{raw_rows}</div></details><div class="verify">Verify licensing and contact details through NMLS Consumer Access or the appropriate state regulator before relying on them for outreach.</div></section></main><script>(function(){{function openTool(name){{sessionStorage.setItem('bb-contact-prep-open-tool',name);location.href='/'}}document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>openTool(b.dataset.tool))}})();</script></body></html>'''
        return Response(body, mimetype="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    @app.after_request
    def simplify_prospect_clicks(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-prospect-intelligence-navigation" in body or "</body>" not in body.lower():
            return response
        script = r'''<script id="brokerbeacon-prospect-intelligence-navigation">(function(){function report(id){if(id)location.href='/prospects/'+id+'/intelligence-report'}function wire(){document.querySelectorAll('[data-prospect-id]').forEach(el=>{if(el.dataset.bbIntelWired)return;const id=el.getAttribute('data-prospect-id');if(!id)return;el.dataset.bbIntelWired='1';el.style.cursor='pointer';el.title='Open loan officer contacts';el.addEventListener('click',ev=>{if(ev.target.closest('a,button,input,select,textarea'))return;ev.preventDefault();ev.stopImmediatePropagation();report(id)},true)});document.querySelectorAll('a[href]').forEach(a=>{const m=a.getAttribute('href').match(/^\/prospects?\/(\d+)(?:\/)?$/i);if(m){a.setAttribute('href','/prospects/'+m[1]+'/intelligence-report');a.title='Open loan officer contacts'}})}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true})})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("PROSPECT_DETAIL installed loan-officer-first prospect experience")
    return app


__all__ = ["install_prospect_intelligence_report"]
