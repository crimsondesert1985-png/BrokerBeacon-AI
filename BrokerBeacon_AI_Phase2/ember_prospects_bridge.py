"""Stable clean BrokerBeacon prospect catalog and navigation bridge."""
from __future__ import annotations

import html
import sqlite3
from contextlib import closing

from flask import jsonify, request, Response
from prospect_quality import is_publishable_prospect

STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY".split())
STATE_SET = set(STATE_CODES)


def install_ember_prospects_bridge(app, db_path):
    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def load_items(state: str = "", query: str = "", limit: int = 5000):
        state = state if state in STATE_SET else ""
        query = (query or "").strip()[:120]
        like = f"%{query.lower()}%"
        with closing(connect()) as conn:
            rows = conn.execute("""select p.* from prospects p
                where trim(coalesce(p.company,''))<>''
                  and (?='' or upper(trim(coalesce(p.state,'')))=?)
                  and (?='' or lower(coalesce(p.company,'')) like ?
                               or lower(coalesce(p.city,'')) like ?
                               or lower(coalesce(p.nmls,'')) like ?)
                order by upper(coalesce(p.state,'')), lower(p.company), p.id limit ?""",
                (state, state, query, like, like, like, min(max(int(limit), 1), 5000))).fetchall()
            items = []
            for p in rows:
                if not is_publishable_prospect(p["company"], p["nmls"], p["source_name"]):
                    continue
                contacts = conn.execute("select * from contacts where prospect_id=? order by coalesce(is_primary,0) desc, coalesce(is_decision_maker,0) desc, id", (p["id"],)).fetchall()
                primary = contacts[0] if contacts else None
                items.append({
                    "id": int(p["id"]), "company_name": p["company"] or "", "nmls_id": p["nmls"] or "",
                    "phone": p["phone"] or (primary["phone"] if primary else "") or "",
                    "public_email": p["email"] or (primary["email"] if primary else "") or "",
                    "city": p["city"] or "", "state": (p["state"] or "").upper(),
                    "source": p["source_name"] or "BrokerBeacon CRM",
                    "review_status": p["verification_status"] or "Verify in NMLS",
                    "pipeline_status": p["status"] or "New", "opportunity_score": int(p["score"] or 75),
                    "loan_officer_count": len(contacts), "primary_contact": primary["name"] if primary else "",
                })
            coverage = {code: 0 for code in STATE_CODES}
            for item in items:
                if item["state"] in coverage:
                    coverage[item["state"]] += 1
        return items, coverage

    @app.get("/api/ember/main-prospects")
    def main_prospects():
        state = str(request.args.get("state") or "").strip().upper()
        query = str(request.args.get("q") or "")
        items, coverage = load_items(state, query, request.args.get("limit") or 5000)
        return jsonify(items=items, states=list(STATE_CODES), coverage=coverage, count=len(items), selected_state=state if state in STATE_SET else "")

    @app.get("/prospects/catalog")
    def prospect_catalog():
        state = str(request.args.get("state") or "").strip().upper()
        query = str(request.args.get("q") or "")
        items, coverage = load_items(state, query, 5000)
        options = ['<option value="">All 50 states</option>']
        for code in STATE_CODES:
            sel = ' selected' if state == code else ''
            options.append(f'<option value="{code}"{sel}>{code} ({coverage.get(code, 0)})</option>')
        rows = []
        for item in items:
            contact = item["primary_contact"] or "Contact research pending"
            details = " · ".join(x for x in [item["phone"], item["public_email"]] if x)
            rows.append("<tr>"
                f"<td><strong>{html.escape(item['company_name'])}</strong><small>NMLS {html.escape(item['nmls_id'])}</small></td>"
                f"<td>{html.escape(contact)}<small>{html.escape(details)}</small></td>"
                f"<td><span class='pill'>{html.escape(item['source'])}</span></td>"
                f"<td>{html.escape(', '.join(x for x in [item['city'], item['state']] if x))}</td>"
                f"<td class='score'>{item['opportunity_score']}</td>"
                f"<td>{html.escape(item['review_status'])}</td>"
                f"<td><span class='pill'>{html.escape(item['pipeline_status'])}</span></td></tr>")
        body = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BrokerBeacon Prospects</title><style>
:root{{--b:#060916;--p:#10182f;--p2:#0b1226;--l:#ffffff18;--t:#f7f8ff;--m:#9aa5c8;--v:#7c5cff;--c:#23d4fd;--g:#43dfa7}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 12% 0,#5d3fff55,transparent 28%),radial-gradient(circle at 100% 15%,#23d4fd22,transparent 24%),var(--b);color:var(--t);font:14px Inter,Segoe UI,Arial,sans-serif}}header{{background:#080d1dee;border-bottom:1px solid var(--l);padding:22px 28px;display:flex;justify-content:space-between;align-items:center}}main{{padding:24px}}.filters{{display:flex;gap:10px;margin:0 0 16px}}input,select,button{{padding:11px 12px;border:1px solid var(--l);border-radius:10px;background:#0c142a;color:white}}input{{flex:1}}button{{background:linear-gradient(135deg,var(--v),#5a9cff);border:0;cursor:pointer}}table{{width:100%;border-collapse:collapse;background:#111a34dd;border:1px solid var(--l);border-radius:17px;overflow:hidden;box-shadow:0 22px 60px #0005}}th,td{{padding:13px;border-bottom:1px solid var(--l);text-align:left;vertical-align:top}}th{{font-size:10px;text-transform:uppercase;color:var(--m);background:#0b1226;position:sticky;top:0}}small{{display:block;color:var(--m);margin-top:4px}}.count{{font-weight:800;color:var(--c)}}.pill{{display:inline-block;padding:5px 8px;border-radius:999px;background:#23d4fd15;color:#8cecff;font-size:10px}}.score{{color:var(--g);font-weight:800}}a{{color:var(--c);text-decoration:none}}@media(max-width:800px){{.filters{{flex-direction:column}}table{{font-size:12px}}th,td{{padding:8px}}}}
</style></head><body><header><div><strong>BrokerBeacon AI</strong><div>Prospect Catalog</div></div><div class="count">{len(items)} clean prospects</div><a href="/">Back to app</a></header><main><form class="filters" method="get"><input name="q" value="{html.escape(query)}" placeholder="Search company, city, or NMLS"><select name="state">{''.join(options)}</select><button type="submit">Filter</button></form><table><thead><tr><th>Company</th><th>Contact</th><th>Source</th><th>Location</th><th>Score</th><th>Verification</th><th>Status</th></tr></thead><tbody>{''.join(rows) if rows else '<tr><td colspan="7">No clean prospects match this filter.</td></tr>'}</tbody></table></main></body></html>'''
        return Response(body, mimetype="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    # Navigation stays inside the main Ash Workplace shell (light theme).
    # Standalone /prospects/catalog remains available for direct links,
    # but is no longer forced when the user clicks Prospects in the primary nav.

    try:
        items, coverage = load_items("", "", 5000)
        app.logger.warning("PROSPECT_CATALOG clean_ready visible=%s states_with_records=%s states_in_filter=%s", len(items), sum(1 for v in coverage.values() if v), len(STATE_CODES))
    except Exception:
        app.logger.exception("PROSPECT_CATALOG verification failed")
    return app


__all__ = ["install_ember_prospects_bridge"]
