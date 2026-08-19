"""Simple contact-first intelligence report for BrokerBeacon prospects.

The report is intentionally optimized for the field user: click a prospect,
see the account, then immediately see every stored loan officer/contact with
clickable phone and email information. Lower-value metadata is kept below the
contact section instead of competing with it.
"""
from __future__ import annotations

import html
import sqlite3
from contextlib import closing
from urllib.parse import quote

from flask import g, Response


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
        if name in record and _text(record.get(name)):
            return _text(record.get(name))
    return ""


def _contact_card(contact: dict, index: int) -> str:
    name = _first(contact, "name", "full_name", "contact_name") or f"Contact {index}"
    title = _first(contact, "title", "job_title", "role") or "Loan officer / account contact"
    phone = _first(contact, "phone", "mobile_phone", "direct_phone", "office_phone")
    email = _first(contact, "email", "public_email", "work_email")
    nmls = _first(contact, "nmls", "nmls_id", "license_number")
    city = _first(contact, "city")
    state = _first(contact, "state")
    location = ", ".join(v for v in (city, state) if v)
    primary = bool(contact.get("is_primary"))
    decision = bool(contact.get("is_decision_maker"))

    phone_html = (
        f'<a class="contact-action phone" href="tel:{html.escape("".join(ch for ch in phone if ch.isdigit() or ch == "+"))}">'
        f'<span>Phone</span><strong>{_esc(phone)}</strong></a>'
        if phone else '<div class="contact-action missing"><span>Phone</span><strong>Not found yet</strong></div>'
    )
    email_html = (
        f'<a class="contact-action email" href="mailto:{_esc(email)}">'
        f'<span>Email</span><strong>{_esc(email)}</strong></a>'
        if email else '<div class="contact-action missing"><span>Email</span><strong>Not found yet</strong></div>'
    )
    badges = []
    if primary:
        badges.append('<span class="badge primary">Primary</span>')
    if decision:
        badges.append('<span class="badge decision">Decision maker</span>')
    if nmls:
        badges.append(f'<span class="badge">NMLS {_esc(nmls)}</span>')

    extra_rows = []
    shown = {"id", "prospect_id", "name", "full_name", "contact_name", "title", "job_title", "role", "phone", "mobile_phone", "direct_phone", "office_phone", "email", "public_email", "work_email", "nmls", "nmls_id", "license_number", "city", "state", "is_primary", "is_decision_maker", "created_at", "updated_at"}
    for key, value in contact.items():
        if key in shown or value in (None, "", 0, False):
            continue
        if isinstance(value, (dict, list, tuple)):
            continue
        extra_rows.append(f'<div><b>{_esc(key.replace("_", " ").title())}</b><span>{_esc(value)}</span></div>')

    return f'''<article class="contact-card">
      <div class="contact-head"><div><h2>{_esc(name)}</h2><p>{_esc(title)}{f" · {_esc(location)}" if location else ""}</p></div><div class="badges">{''.join(badges)}</div></div>
      <div class="contact-actions">{phone_html}{email_html}</div>
      {f'<details><summary>More contact details</summary><div class="detail-grid">{"".join(extra_rows)}</div></details>' if extra_rows else ''}
    </article>'''


def install_prospect_intelligence_report(app, db_path):
    @app.get("/prospects/<int:prospect_id>/intelligence-report")
    def prospect_intelligence_report(prospect_id: int):
        with closing(_connect(db_path)) as conn:
            if not _table_exists(conn, "prospects"):
                return Response("Prospects are not initialized.", status=404, mimetype="text/plain")
            prospect = conn.execute("select * from prospects where id=?", (prospect_id,)).fetchone()
            if not prospect:
                return Response("Prospect not found.", status=404, mimetype="text/plain")
            account = dict(prospect)
            contacts = []
            if _table_exists(conn, "contacts") and "prospect_id" in _columns(conn, "contacts"):
                contacts = [dict(row) for row in conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id""",
                    (prospect_id,),
                ).fetchall()]

        company = _first(account, "company", "company_name", "legal_name") or f"Prospect {prospect_id}"
        company_phone = _first(account, "phone", "main_phone")
        company_email = _first(account, "email", "public_email")
        nmls = _first(account, "nmls", "nmls_id")
        city = _first(account, "city")
        state = _first(account, "state")
        website = _first(account, "website", "url")
        score = _first(account, "score", "opportunity_score")
        status = _first(account, "status", "pipeline_status") or "New"
        source = _first(account, "source_name", "source")
        verification = _first(account, "verification_status", "review_status") or "Verify in NMLS before relying on this record"

        account_actions = []
        if company_phone:
            account_actions.append(f'<a href="tel:{_esc("".join(ch for ch in company_phone if ch.isdigit() or ch == "+"))}">Call main line · {_esc(company_phone)}</a>')
        if company_email:
            account_actions.append(f'<a href="mailto:{_esc(company_email)}">Email account · {_esc(company_email)}</a>')
        if website:
            safe_url = website if website.lower().startswith(("http://", "https://")) else "https://" + website
            account_actions.append(f'<a target="_blank" rel="noopener noreferrer" href="{_esc(safe_url)}">Open website</a>')

        cards = ''.join(_contact_card(contact, i + 1) for i, contact in enumerate(contacts))
        if not cards:
            cards = '''<div class="empty"><strong>No individual loan-officer contacts are stored yet.</strong><p>The account-level phone/email is shown above. Ember can continue enriching this account in the background.</p></div>'''

        account_meta = []
        for label, value in (
            ("NMLS", nmls), ("Location", ", ".join(v for v in (city, state) if v)),
            ("Opportunity score", score), ("Pipeline status", status), ("Source", source),
            ("Verification", verification),
        ):
            if value:
                account_meta.append(f'<div><b>{_esc(label)}</b><span>{_esc(value)}</span></div>')

        # Preserve full stored account data, but keep it collapsed so the main
        # experience remains contact-first and intuitive.
        raw_rows = []
        for key, value in account.items():
            if value in (None, "") or isinstance(value, (dict, list, tuple)):
                continue
            raw_rows.append(f'<div><b>{_esc(key.replace("_", " ").title())}</b><span>{_esc(value)}</span></div>')

        body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(company)} · Intelligence · BrokerBeacon</title><style>
:root{{--navy:#07162e;--blue:#174ea6;--ink:#17283d;--muted:#697b90;--line:#dce6f1;--bg:#f5f8fc;--green:#0d7a5f}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}}header{{background:linear-gradient(135deg,#07162e,#102b52);color:white;padding:22px 28px}}header a{{color:#a9ddff;text-decoration:none}}.wrap{{max-width:1180px;margin:auto;padding:24px}}.hero{{background:white;border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 12px 34px #17365f10}}.eyebrow{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#4774aa;font-weight:900}}h1{{margin:5px 0 8px;font-size:30px}}.subtitle{{color:var(--muted)}}.account-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}}.account-actions a{{display:inline-flex;padding:10px 12px;border-radius:10px;background:#eef5ff;color:var(--blue);text-decoration:none;font-weight:750;border:1px solid #d4e4f8}}.meta-grid,.detail-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:16px}}.meta-grid>div,.detail-grid>div{{border-top:1px solid var(--line);padding-top:9px}}.meta-grid b,.detail-grid b{{display:block;font-size:9px;text-transform:uppercase;color:var(--muted);letter-spacing:.06em}}.meta-grid span,.detail-grid span{{display:block;margin-top:3px;word-break:break-word}}.section-head{{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:26px 0 12px}}.section-head h2{{margin:0;font-size:22px}}.count{{padding:6px 9px;border-radius:999px;background:#e9f7f2;color:var(--green);font-weight:850;font-size:11px}}.contacts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.contact-card{{background:white;border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 8px 22px #17365f0d}}.contact-head{{display:flex;justify-content:space-between;gap:10px}}.contact-head h2{{margin:0;font-size:19px}}.contact-head p{{margin:4px 0 0;color:var(--muted)}}.badges{{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}}.badge{{height:max-content;padding:4px 7px;border-radius:999px;background:#eef3f8;color:#4f6074;font-size:9px;font-weight:800}}.badge.primary{{background:#e7f7f0;color:#126b55}}.badge.decision{{background:#fff2d9;color:#8a5b00}}.contact-actions{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:14px}}.contact-action{{display:block;padding:12px;border-radius:12px;border:1px solid #d8e5f3;text-decoration:none;background:#f8fbff;color:var(--ink)}}.contact-action span{{display:block;font-size:9px;text-transform:uppercase;color:var(--muted);font-weight:850}}.contact-action strong{{display:block;margin-top:4px;font-size:15px;word-break:break-word}}.contact-action.phone:hover,.contact-action.email:hover{{border-color:#8bb4e6;background:#eef6ff}}.contact-action.missing{{opacity:.55}}details{{margin-top:12px}}summary{{cursor:pointer;color:var(--blue);font-weight:750}}.empty{{background:white;border:1px dashed #bdcad9;border-radius:15px;padding:22px;color:var(--muted)}}.raw{{margin-top:22px;background:white;border:1px solid var(--line);border-radius:14px;padding:14px}}.notice{{margin-top:14px;padding:11px 13px;border-radius:11px;background:#fff8e8;color:#765a13;font-size:12px}}@media(max-width:780px){{.contacts{{grid-template-columns:1fr}}.meta-grid,.detail-grid{{grid-template-columns:1fr 1fr}}.contact-actions{{grid-template-columns:1fr}}}}@media(max-width:520px){{.meta-grid,.detail-grid{{grid-template-columns:1fr}}h1{{font-size:24px}}}}
</style></head><body><header><a href="/prospects/catalog">← Back to Prospects</a></header><main class="wrap"><section class="hero"><div class="eyebrow">Prospect Intelligence</div><h1>{_esc(company)}</h1><div class="subtitle">Everything you need to contact this account, with loan-officer information shown first.</div><div class="account-actions">{''.join(account_actions) or '<span class="subtitle">No account-level phone/email is stored yet.</span>'}</div><div class="meta-grid">{''.join(account_meta)}</div><div class="notice">Verify licensing and contact details through NMLS Consumer Access or the appropriate state regulator before relying on them for outreach.</div></section><div class="section-head"><div><h2>Loan Officers & Contacts</h2><div class="subtitle">Phone and email are intentionally the most prominent information on this page.</div></div><div class="count">{len(contacts)} contact{'s' if len(contacts) != 1 else ''}</div></div><section class="contacts">{cards}</section><details class="raw"><summary>All stored account data</summary><div class="detail-grid">{''.join(raw_rows)}</div></details></main></body></html>'''
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
        script = r'''<script id="brokerbeacon-prospect-intelligence-navigation">(function(){
function report(id){if(id)location.href='/prospects/'+id+'/intelligence-report'}
function wire(){document.querySelectorAll('[data-prospect-id]').forEach(el=>{if(el.dataset.bbIntelWired)return;const id=el.getAttribute('data-prospect-id');if(!id)return;el.dataset.bbIntelWired='1';el.style.cursor='pointer';el.title='Open prospect intelligence and contact information';el.addEventListener('click',ev=>{if(ev.target.closest('a,button,input,select,textarea'))return;ev.preventDefault();ev.stopImmediatePropagation();report(id)},true)});document.querySelectorAll('a[href]').forEach(a=>{const m=a.getAttribute('href').match(/^\/prospects?\/(\d+)(?:\/)?$/i);if(m){a.setAttribute('href','/prospects/'+m[1]+'/intelligence-report');a.title='Open prospect intelligence and contact information'}})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("PROSPECT_INTELLIGENCE_REPORT installed contact-first prospect navigation")
    return app


__all__ = ["install_prospect_intelligence_report"]
