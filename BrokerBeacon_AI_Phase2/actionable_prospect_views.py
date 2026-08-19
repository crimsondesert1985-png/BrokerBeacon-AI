"""Contact-first prospect views for BrokerBeacon.

Only prospects with a real public phone or email are exposed as actionable.
Incomplete but otherwise valid companies remain in the warehouse/CRM for
background enrichment instead of appearing as sales-ready records.
"""
from __future__ import annotations

import html
import sqlite3
from contextlib import closing

from flask import jsonify, request, Response

from prospect_quality import is_publishable_prospect

STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY".split())
STATE_SET = set(STATE_CODES)


def _text(value) -> str:
    return str(value or "").strip()


def install_actionable_prospect_views(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def load_items(state: str = "", query: str = "", limit: int = 5000):
        state = state if state in STATE_SET else ""
        query = (query or "").strip()[:120]
        like = f"%{query.lower()}%"
        items = []
        coverage = {code: 0 for code in STATE_CODES}
        with closing(connect()) as conn:
            rows = conn.execute(
                """select p.* from prospects p
                   where trim(coalesce(p.company,''))<>''
                     and (?='' or upper(trim(coalesce(p.state,'')))=?)
                     and (?='' or lower(coalesce(p.company,'')) like ?
                                  or lower(coalesce(p.city,'')) like ?
                                  or lower(coalesce(p.nmls,'')) like ?)
                   order by upper(coalesce(p.state,'')),lower(p.company),p.id limit ?""",
                (state, state, query, like, like, like, min(max(int(limit), 1), 5000)),
            ).fetchall()
            for p in rows:
                if not is_publishable_prospect(p["company"], p["nmls"], p["source_name"]):
                    continue
                contacts = conn.execute(
                    """select * from contacts where prospect_id=?
                       and (trim(coalesce(phone,''))<>'' or trim(coalesce(email,''))<>'')
                       order by coalesce(is_primary,0) desc,coalesce(is_decision_maker,0) desc,id""",
                    (p["id"],),
                ).fetchall()
                primary = contacts[0] if contacts else None
                phone = _text(p["phone"]) or (_text(primary["phone"]) if primary else "")
                email = _text(p["email"]) or (_text(primary["email"]) if primary else "")
                if not phone and not email:
                    continue
                item = {
                    "id": int(p["id"]),
                    "company_name": _text(p["company"]),
                    "nmls_id": _text(p["nmls"]),
                    "phone": phone,
                    "public_email": email,
                    "city": _text(p["city"]),
                    "state": _text(p["state"]).upper(),
                    "source": _text(p["source_name"]) or "BrokerBeacon CRM",
                    "review_status": _text(p["verification_status"]) or "Verify in NMLS",
                    "pipeline_status": _text(p["status"]) or "New",
                    "opportunity_score": int(p["score"] or 75),
                    "loan_officer_count": len(contacts),
                    "primary_contact": _text(primary["name"]) if primary else "Company contact",
                    "actionable": True,
                    "intelligence_url": f"/prospects/{int(p['id'])}/intelligence-report",
                }
                items.append(item)
                if item["state"] in coverage:
                    coverage[item["state"]] += 1
        return items, coverage

    def main_prospects():
        state = _text(request.args.get("state")).upper()
        query = _text(request.args.get("q"))
        items, coverage = load_items(state, query, request.args.get("limit") or 5000)
        return jsonify(
            items=items,
            states=list(STATE_CODES),
            coverage=coverage,
            count=len(items),
            selected_state=state if state in STATE_SET else "",
            quality_standard="Public phone or email required; licensing must be verified before outreach",
        )

    def prospect_catalog():
        state = _text(request.args.get("state")).upper()
        query = _text(request.args.get("q"))
        items, coverage = load_items(state, query, 5000)
        options = ['<option value="">All 50 states</option>']
        for code in STATE_CODES:
            selected = " selected" if state == code else ""
            options.append(f'<option value="{code}"{selected}>{code} ({coverage.get(code, 0)})</option>')
        rows = []
        for item in items:
            details = " · ".join(v for v in (item["phone"], item["public_email"]) if v)
            rows.append(
                f"<tr class='prospect-row' data-prospect-id='{item['id']}' onclick=\"location.href='{item['intelligence_url']}'\">"
                f"<td><a class='company-link' href='{item['intelligence_url']}'><strong>{html.escape(item['company_name'])}</strong><small>NMLS {html.escape(item['nmls_id'])}</small></a></td>"
                f"<td>{html.escape(item['primary_contact'])}<small>{html.escape(details)}</small></td>"
                f"<td>{html.escape(item['city'])}, {html.escape(item['state'])}</td>"
                f"<td>{html.escape(item['source'])}</td>"
                f"<td>{item['opportunity_score']}</td>"
                f"<td>{html.escape(item['review_status'])}</td>"
                f"<td><a class='open-btn' href='{item['intelligence_url']}'>View contacts</a></td>"
                "</tr>"
            )
        body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BrokerBeacon Actionable Prospects</title><style>
body{{font:14px Inter,Arial;background:#07162e;color:#eef4ff;margin:0}}header,main{{padding:22px}}header{{background:#0d2347}}form{{display:flex;gap:8px;margin-bottom:16px}}input,select,button{{padding:10px;border-radius:8px;border:1px solid #ffffff22;background:#102b52;color:white}}input{{flex:1}}table{{width:100%;border-collapse:collapse;background:#0c2040}}th,td{{padding:11px;border-bottom:1px solid #ffffff18;text-align:left;vertical-align:top}}small{{display:block;color:#9fb2d1;margin-top:4px}}a{{color:#8fd7ff;text-decoration:none}}.prospect-row{{cursor:pointer}}.prospect-row:hover{{background:#14315a}}.company-link{{display:block;color:white}}.open-btn{{display:inline-flex;padding:7px 9px;border-radius:8px;background:#174ea6;color:white;font-weight:800;white-space:nowrap}}
</style></head><body><header><strong>BrokerBeacon · Prospects</strong><div>{len(items)} actionable prospects with contact information</div></header><main><p>Click any prospect to open its Intelligence Report and see every stored loan officer and contact first.</p><form method="get"><input name="q" value="{html.escape(query)}" placeholder="Search company, city, or NMLS"><select name="state">{''.join(options)}</select><button>Filter</button></form><table><thead><tr><th>Company</th><th>Primary contact</th><th>Location</th><th>Source</th><th>Score</th><th>Verification</th><th></th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="7">No actionable prospects match this filter yet.</td></tr>'}</tbody></table></main></body></html>'''
        return Response(body, mimetype="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    # The existing rules point at these endpoint names. Replacing the view
    # functions avoids duplicate Flask routes while tightening the data contract.
    app.view_functions["main_prospects"] = main_prospects
    app.view_functions["prospect_catalog"] = prospect_catalog

    try:
        items, coverage = load_items("", "", 5000)
        app.logger.warning(
            "ACTIONABLE_PROSPECTS ready=%s states=%s quality=phone_or_email_required",
            len(items), sum(1 for count in coverage.values() if count),
        )
    except Exception:
        app.logger.exception("ACTIONABLE_PROSPECTS verification failed")
    return app


__all__ = ["install_actionable_prospect_views"]
