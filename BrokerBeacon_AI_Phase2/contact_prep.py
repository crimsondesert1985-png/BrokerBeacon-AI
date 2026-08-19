"""Dedicated contact-prep workspace for BrokerBeacon prospects."""
from __future__ import annotations

import html
import re
import sqlite3
from contextlib import closing

from flask import Response, g, request


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


def _first(record: dict, *names: str) -> str:
    for name in names:
        value = _text(record.get(name))
        if value:
            return value
    return ""


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone())


def _columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _digits(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit() or ch == "+")


def _contact_card(contact: dict, index: int) -> str:
    name = _first(contact, "name", "full_name", "contact_name") or f"Contact {index}"
    title = _first(contact, "title", "job_title", "role") or "Loan Officer / Brokerage Contact"
    nmls = _first(contact, "nmls", "nmls_id", "license_number")
    city = _first(contact, "city")
    state = _first(contact, "state")
    location = ", ".join(v for v in (city, state) if v)

    phones = []
    seen_phones = set()
    for label, field in (("Mobile", "mobile_phone"), ("Direct", "direct_phone"), ("Phone", "phone"), ("Office", "office_phone")):
        value = _text(contact.get(field))
        normalized = _digits(value)
        if value and normalized and normalized not in seen_phones:
            seen_phones.add(normalized)
            phones.append((label, value))

    emails = []
    seen_emails = set()
    for field in ("email", "public_email", "work_email"):
        value = _text(contact.get(field))
        lowered = value.lower()
        if value and lowered not in seen_emails:
            seen_emails.add(lowered)
            emails.append(value)

    badges = []
    if bool(contact.get("is_primary")):
        badges.append('<span class="badge primary">Primary contact</span>')
    if bool(contact.get("is_decision_maker")):
        badges.append('<span class="badge decision">Decision maker</span>')
    if nmls:
        badges.append(f'<span class="badge">NMLS {_esc(nmls)}</span>')

    phone_html = "".join(
        f'<a class="contact-method" href="tel:{_esc(_digits(phone))}"><span>{_esc(label)}</span><strong>{_esc(phone)}</strong><em>Call</em></a>'
        for label, phone in phones
    ) or '<div class="contact-method unavailable"><span>Phone</span><strong>Not available</strong></div>'

    email_html = "".join(
        f'<a class="contact-method" href="mailto:{_esc(email)}"><span>Email</span><strong>{_esc(email)}</strong><em>Email</em></a>'
        for email in emails
    ) or '<div class="contact-method unavailable"><span>Email</span><strong>Not available</strong></div>'

    shown = {
        "id", "prospect_id", "name", "full_name", "contact_name", "title", "job_title", "role",
        "phone", "mobile_phone", "direct_phone", "office_phone", "email", "public_email", "work_email",
        "nmls", "nmls_id", "license_number", "city", "state", "is_primary", "is_decision_maker",
        "created_at", "updated_at",
    }
    extras = []
    for key, value in contact.items():
        if key in shown or value in (None, "", False) or isinstance(value, (dict, list, tuple)):
            continue
        extras.append(f'<div><b>{_esc(key.replace("_", " ").title())}</b><span>{_esc(value)}</span></div>')

    extra_html = f'<details><summary>More contact details</summary><div class="detail-grid">{"".join(extras)}</div></details>' if extras else ""
    first_email = emails[0] if emails else ""

    return f'''<article class="contact-card" data-name="{_esc(name)}" data-email="{_esc(first_email)}">
      <div class="contact-head"><div><h2>{_esc(name)}</h2><p>{_esc(title)}{f" · {_esc(location)}" if location else ""}</p></div><div class="badges">{''.join(badges)}</div></div>
      <div class="contact-methods">{phone_html}{email_html}</div>
      <div class="prep-actions"><button type="button" data-kind="email">Draft email</button><button type="button" data-kind="call">Call prep</button><button type="button" data-kind="text">Text draft</button></div>
      {extra_html}
    </article>'''


def install_contact_prep(app, db_path):
    @app.get("/prospects/<int:prospect_id>/contact-prep")
    def prospect_contact_prep(prospect_id: int):
        if not getattr(g, "user_id", None):
            return Response("Authentication required.", status=401, mimetype="text/plain")

        with closing(_connect(db_path)) as conn:
            if not _table_exists(conn, "prospects"):
                return Response("Prospects are not initialized.", status=404, mimetype="text/plain")
            row = conn.execute("select * from prospects where id=?", (prospect_id,)).fetchone()
            if not row:
                return Response("Prospect not found.", status=404, mimetype="text/plain")
            prospect = dict(row)
            contacts = []
            if _table_exists(conn, "contacts") and "prospect_id" in _columns(conn, "contacts"):
                contacts = [dict(item) for item in conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id""",
                    (prospect_id,),
                ).fetchall()]

        company = _first(prospect, "company", "company_name", "legal_name") or f"Prospect {prospect_id}"
        company_phone = _first(prospect, "phone", "main_phone")
        company_email = _first(prospect, "email", "public_email")
        website = _first(prospect, "website", "url")
        nmls = _first(prospect, "nmls", "nmls_id")
        location = ", ".join(v for v in (_first(prospect, "city"), _first(prospect, "state")) if v)

        account_links = []
        if company_phone:
            account_links.append(f'<a href="tel:{_esc(_digits(company_phone))}">Main line · {_esc(company_phone)}</a>')
        if company_email:
            account_links.append(f'<a href="mailto:{_esc(company_email)}">Account email · {_esc(company_email)}</a>')
        if website:
            safe = website if website.lower().startswith(("http://", "https://")) else "https://" + website
            account_links.append(f'<a href="{_esc(safe)}" target="_blank" rel="noopener noreferrer">Website</a>')

        cards = "".join(_contact_card(contact, i + 1) for i, contact in enumerate(contacts))
        if not cards:
            cards = '<div class="empty"><h2>No individual loan officers stored yet</h2><p>Account-level contact information remains available above while BrokerBeacon continues enrichment.</p></div>'

        body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(company)} · Contact Prep · BrokerBeacon</title><style>
:root{{--navy:#07162e;--blue:#285fe8;--ink:#17283d;--muted:#697b90;--line:#dce6f1;--bg:#f5f8fc;--green:#0d7a5f}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}}.topbar{{position:sticky;top:0;z-index:40;background:linear-gradient(135deg,#07162e,#102b52);color:white}}.topbar-inner{{max-width:1240px;margin:auto;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}}.brand{{font-weight:900}}.tools{{display:flex;gap:6px;flex-wrap:wrap}}.tools a,.tools button{{border:1px solid #ffffff28;background:#ffffff10;color:white;border-radius:9px;padding:8px 10px;text-decoration:none;font:inherit;font-size:11px;font-weight:750;cursor:pointer}}.wrap{{max-width:1240px;margin:auto;padding:24px 20px 50px}}.hero{{background:white;border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 12px 34px #17365f10}}.eyebrow{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#4774aa;font-weight:900}}h1{{margin:5px 0 7px;font-size:30px}}.subtitle{{color:var(--muted)}}.account-links,.workspace-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}.account-links a,.account-links span,.workspace-actions a,.workspace-actions button{{padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:#f7faff;color:var(--ink);text-decoration:none;font:inherit;font-size:12px;font-weight:750;cursor:pointer}}.workspace-actions .primary{{background:var(--blue);color:white;border-color:var(--blue)}}.section-head{{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:26px 0 12px}}.section-head h2{{margin:0;font-size:22px}}.count{{padding:6px 9px;border-radius:999px;background:#e9f7f2;color:var(--green);font-weight:850;font-size:11px}}.contacts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.contact-card{{background:white;border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 8px 22px #17365f0d}}.contact-head{{display:flex;justify-content:space-between;gap:10px}}.contact-head h2{{margin:0;font-size:19px}}.contact-head p{{margin:4px 0 0;color:var(--muted)}}.badges{{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}}.badge{{height:max-content;padding:4px 7px;border-radius:999px;background:#eef3f8;color:#4f6074;font-size:9px;font-weight:800}}.badge.primary{{background:#e7f7f0;color:#126b55}}.badge.decision{{background:#fff2d9;color:#8a5b00}}.contact-methods{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:14px}}.contact-method{{display:block;padding:12px;border-radius:12px;border:1px solid #d8e5f3;text-decoration:none;background:#f8fbff;color:var(--ink)}}.contact-method span{{display:block;font-size:9px;text-transform:uppercase;color:var(--muted);font-weight:850}}.contact-method strong{{display:block;margin-top:4px;font-size:15px;word-break:break-word}}.contact-method em{{display:block;margin-top:7px;color:var(--blue);font-size:10px;font-style:normal;font-weight:850}}.contact-method:hover{{border-color:#8bb4e6;background:#eef6ff}}.contact-method.unavailable{{opacity:.55}}.prep-actions{{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}}.prep-actions button{{border:1px solid var(--line);background:white;border-radius:9px;padding:8px 9px;font:inherit;font-size:11px;font-weight:750;cursor:pointer}}details{{margin-top:12px}}summary{{cursor:pointer;color:var(--blue);font-weight:750}}.detail-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:10px}}.detail-grid>div{{border-top:1px solid var(--line);padding-top:8px}}.detail-grid b{{display:block;font-size:9px;text-transform:uppercase;color:var(--muted)}}.detail-grid span{{display:block;margin-top:3px;word-break:break-word}}.empty{{grid-column:1/-1;background:white;border:1px dashed #bdcad9;border-radius:15px;padding:22px;color:var(--muted)}}.drawer{{position:fixed;top:0;right:0;z-index:100;width:min(480px,100vw);height:100vh;background:#0b1730;color:white;box-shadow:-24px 0 60px #0005;transform:translateX(105%);transition:.2s;padding:20px;overflow:auto}}.drawer.open{{transform:none}}.drawer textarea{{width:100%;min-height:260px;border-radius:10px;padding:12px;font:inherit}}.drawer button{{border:1px solid #ffffff25;background:#ffffff10;color:white;border-radius:9px;padding:8px 10px;cursor:pointer}}.drawer-actions{{display:flex;gap:8px;margin-top:9px}}.notice{{margin-top:18px;color:#748399;font-size:11px}}@media(max-width:800px){{.contacts{{grid-template-columns:1fr}}.topbar-inner{{align-items:flex-start;flex-direction:column}}}}@media(max-width:560px){{.contact-methods,.detail-grid{{grid-template-columns:1fr}}h1{{font-size:24px}}}}
</style></head><body><header class="topbar"><div class="topbar-inner"><div class="brand">BrokerBeacon · Contact Prep</div><nav class="tools"><a href="/">Home</a><a href="/prospects/catalog">Prospects</a><a href="/prospects/{prospect_id}/intelligence-report">Intelligence</a><button data-tool="notes">Notes</button><button data-tool="marketing">Marketing</button><button data-tool="sales coach">Sales Coach</button><button data-tool="opportunity">Opportunities</button><a href="/intelligence/scenario-rescue">BeaconMatch</a></nav></div></header><main class="wrap"><section class="hero"><div class="eyebrow">Contact Prep</div><h1>{_esc(company)}</h1><div class="subtitle">Every available person and contact method for this brokerage, ready before a call or meeting.</div><div class="account-links">{f'<span>NMLS {_esc(nmls)}</span>' if nmls else ''}{f'<span>{_esc(location)}</span>' if location else ''}{''.join(account_links)}</div><div class="workspace-actions"><a class="primary" href="/prospects/{prospect_id}/intelligence-report">View Account Intelligence</a><button data-tool="notes">Open Notes</button><button data-tool="opportunity">Opportunity Actions</button></div></section><div class="section-head"><div><h2>Loan Officers & Contacts</h2><div class="subtitle">Tap a phone number to call or an email address to compose.</div></div><div class="count">{len(contacts)} contact{'s' if len(contacts) != 1 else ''}</div></div><section class="contacts">{cards}</section><div class="notice">Verify licensing and contact details through NMLS Consumer Access or the appropriate state regulator before relying on them for outreach.</div></main><aside id="prep-drawer" class="drawer"><button id="close-prep" style="float:right">Close</button><div id="prep-content"></div></aside><script>
(function(){{const company={company!r};function openTool(name){{sessionStorage.setItem('bb-contact-prep-open-tool',name);location.href='/'}}document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>openTool(b.dataset.tool));function openDrawer(title,content){{const d=document.getElementById('prep-drawer'),c=document.getElementById('prep-content');c.innerHTML='';const h=document.createElement('h2');h.textContent=title;const a=document.createElement('textarea');a.value=content;const actions=document.createElement('div');actions.className='drawer-actions';const copy=document.createElement('button');copy.textContent='Copy';copy.onclick=async()=>{{await navigator.clipboard.writeText(a.value);copy.textContent='Copied'}};actions.appendChild(copy);c.append(h,a,actions);d.classList.add('open');a.focus()}}document.getElementById('close-prep').onclick=()=>document.getElementById('prep-drawer').classList.remove('open');document.querySelectorAll('.prep-actions button').forEach(btn=>btn.onclick=()=>{{const card=btn.closest('.contact-card'),name=card.dataset.name||'there',kind=btn.dataset.kind;let title='',draft='';if(kind==='email'){{title='Email · '+name;draft='Subject: Quick introduction\n\nHi '+name+',\n\nI wanted to introduce myself and offer to be a resource for '+company+'. If you have a wholesale mortgage scenario that needs a second look, an onboarding question, or a file you are trying to place, I am happy to help work through the next step.\n\nIf useful, send over the basics of what you are working on and I will help think through the options.\n\nBest,\n[Your Name]'}}else if(kind==='call'){{title='Call Prep · '+name;draft='Hi '+name+', this is [Your Name] with [Lender]. I wanted to introduce myself and offer to be a resource for '+company+'. If you have a wholesale mortgage scenario you are trying to place, or any onboarding questions, I am happy to help. What are you working on right now?'}}else{{title='Text · '+name;draft='Hi '+name+', this is [Your Name] with [Lender]. Wanted to introduce myself and offer help with any wholesale mortgage scenarios or onboarding questions for '+company+'. Happy to be a resource.'}}openDrawer(title,draft)}})}})();
</script></body></html>'''
        return Response(body, mimetype="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    @app.after_request
    def add_contact_prep_button(response):
        if not getattr(g, "user_id", None):
            return response
        match = re.fullmatch(r"/prospects/(\d+)/intelligence-report/?", request.path)
        if not match:
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-contact-prep-button" in body or "</body>" not in body.lower():
            return response
        prospect_id = match.group(1)
        enhancement = f'''<style id="brokerbeacon-contact-prep-button-style">.bb-contact-prep-primary{{display:inline-flex!important;align-items:center;justify-content:center;background:#285fe8!important;border-color:#285fe8!important;color:#fff!important;padding:11px 16px!important;font-weight:900!important;box-shadow:0 7px 18px #285fe833}}.bb-contact-prep-primary:hover{{background:#174fcf!important}}</style><script id="brokerbeacon-contact-prep-button">(function(){{function add(){{if(document.querySelector('.bb-contact-prep-primary'))return;const actions=document.querySelector('.account-actions');if(!actions)return;const a=document.createElement('a');a.className='bb-contact-prep-primary';a.href='/prospects/{prospect_id}/contact-prep';a.textContent='Contact Prep';a.title='Open every available loan officer and contact method for this brokerage';actions.prepend(a)}}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add()}})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + enhancement + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    @app.after_request
    def restore_contact_prep_tool(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-contact-prep-tool-bridge" in body or "</body>" not in body.lower():
            return response
        script = r'''<script id="brokerbeacon-contact-prep-tool-bridge">(function(){const wanted=sessionStorage.getItem('bb-contact-prep-open-tool');if(!wanted)return;const clean=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();function open(){const target=clean(wanted),controls=[...document.querySelectorAll('aside button,aside a,nav button,nav a')],hit=controls.find(el=>clean((el.textContent||'')+' '+(el.title||'')+' '+(el.id||'')).includes(target));if(!hit)return false;sessionStorage.removeItem('bb-contact-prep-open-tool');hit.click();setTimeout(()=>hit.scrollIntoView({behavior:'smooth',block:'nearest'}),100);return true}if(open())return;const o=new MutationObserver(()=>{if(open())o.disconnect()});o.observe(document.documentElement,{childList:true,subtree:true});setTimeout(()=>o.disconnect(),5000)})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("CONTACT_PREP installed dedicated prospect contact workspace")
    return app


__all__ = ["install_contact_prep"]
