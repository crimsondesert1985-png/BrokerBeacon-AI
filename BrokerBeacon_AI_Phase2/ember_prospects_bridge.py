"""Stable database-backed prospect catalog for BrokerBeacon.

The original single-page Prospects view is not reliably connected to the current CRM
catalog. This module provides a dedicated authenticated catalog page, keeps the JSON
API, and redirects the existing Prospects navigation button to the working page.
"""
from __future__ import annotations

import html
import re
import sqlite3
from contextlib import closing

from flask import jsonify, request, Response

STATE_CODES = tuple(
    "AL AK AZ AR CA CO CT DC DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY".split()
)
STATE_SET = set(STATE_CODES)
GENERIC_PATTERNS = (
    "annual report", "best mortgage brokers", "top loan officers", "broker near me",
    "department of savings", "division of banks", "real estate in ", "nmls esb",
    "cyber fbi", "mortgage lenders loan officers", "mortgage broker directory",
    "search results", "consumer access",
)


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _is_generic_name(name: object) -> bool:
    value = _norm(name)
    return not value or any(pattern in value for pattern in GENERIC_PATTERNS)


def install_ember_prospects_bridge(app, db_path):
    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def catalog(state: str = "", query: str = "", limit: int = 5000):
        state = state if state in STATE_SET else ""
        query = query[:120]
        like = f"%{query.lower()}%"
        with closing(connect()) as conn:
            rows = conn.execute(
                """select p.* from prospects p
                   where trim(coalesce(p.company,''))<>''
                     and (?='' or upper(trim(coalesce(p.state,'')))=?)
                     and (?='' or lower(coalesce(p.company,'')) like ?
                                  or lower(coalesce(p.city,'')) like ?
                                  or lower(coalesce(p.nmls,'')) like ?)
                   order by upper(coalesce(p.state,'')),lower(p.company),p.id
                   limit ?""",
                (state, state, query, like, like, like, min(max(limit, 1), 5000)),
            ).fetchall()
            items = []
            for p in rows:
                if _is_generic_name(p["company"]):
                    continue
                contacts = conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,
                                coalesce(is_decision_maker,0) desc,id""",
                    (p["id"],),
                ).fetchall()
                primary = contacts[0] if contacts else None
                items.append({
                    "id": int(p["id"]),
                    "company_name": p["company"] or "",
                    "nmls_id": p["nmls"] or "",
                    "source_url": p["source_url"] or p["website"] or "",
                    "phone": p["phone"] or (primary["phone"] if primary else "") or "",
                    "public_email": p["email"] or (primary["email"] if primary else "") or "",
                    "city": p["city"] or "",
                    "state": (p["state"] or "").upper(),
                    "review_status": p["verification_status"] or "Verify in NMLS",
                    "pipeline_status": p["status"] or "New",
                    "opportunity_score": int(p["score"] or 75),
                    "loan_officer_count": len(contacts),
                    "primary_contact": primary["name"] if primary else "",
                    "source": p["source_name"] or "BrokerBeacon CRM",
                })
            coverage = {str(row[0] or ""): int(row[1]) for row in conn.execute(
                """select upper(state),count(*) from prospects
                   where length(trim(coalesce(state,'')))=2
                   group by upper(state) order by upper(state)"""
            ).fetchall()}
        return items, coverage

    @app.get("/api/ember/main-prospects")
    def main_prospects():
        requested = str(request.args.get("state") or "").strip().upper()
        state = requested if requested in STATE_SET else ""
        query = str(request.args.get("q") or "").strip()
        try:
            limit = int(request.args.get("limit") or 1000)
        except ValueError:
            limit = 1000
        items, coverage = catalog(state, query, limit)
        return jsonify(items=items, states=list(STATE_CODES), coverage=coverage,
                       count=len(items), selected_state=state,
                       source="database_backed_prospect_catalog")

    @app.get("/prospects-catalog")
    def prospects_catalog():
        requested = str(request.args.get("state") or "").strip().upper()
        state = requested if requested in STATE_SET else ""
        query = str(request.args.get("q") or "").strip()
        items, coverage = catalog(state, query, 5000)
        options = ['<option value="">All states</option>'] + [
            f'<option value="{code}"{" selected" if code == state else ""}>{code} ({coverage.get(code, 0)})</option>'
            for code in STATE_CODES if coverage.get(code, 0)
        ]
        rows = []
        for p in items:
            location = ", ".join(v for v in (p["city"], p["state"]) if v)
            contact = "<br>".join(v for v in (
                html.escape(p["primary_contact"]), html.escape(p["phone"]), html.escape(p["public_email"])
            ) if v) or '<span class="muted">Contact research pending</span>'
            company = html.escape(p["company_name"])
            if p["source_url"]:
                company = f'<a href="{html.escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">{company}</a>'
            rows.append(
                f'<tr><td><strong>{company}</strong><div class="sub">NMLS {html.escape(p["nmls_id"] or "Pending verification")}</div></td>'
                f'<td>{contact}</td><td>{html.escape(location)}</td><td>{p["loan_officer_count"]}</td>'
                f'<td>{html.escape(p["source"])}</td><td>{html.escape(p["pipeline_status"])}</td></tr>'
            )
        body = "".join(rows) or '<tr><td colspan="6" class="empty">No prospects match this filter.</td></tr>'
        page = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BrokerBeacon Prospects</title><style>
:root{{--bg:#f4fbf6;--panel:#fff;--ink:#16251d;--muted:#6b7c72;--line:#dfe9e2;--green:#176b45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}}
header{{position:sticky;top:0;z-index:3;background:#fff;border-bottom:1px solid var(--line);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
header h1{{margin:0;font-size:22px}}header a{{color:var(--green);font-weight:700;text-decoration:none}}
main{{padding:22px;max-width:1500px;margin:auto}}.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:14px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}.card strong{{font-size:28px;display:block}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}input,select,button{{border:1px solid var(--line);background:#fff;border-radius:10px;padding:11px 12px;font:inherit}}
input{{min-width:280px;flex:1}}button{{background:var(--green);color:#fff;border-color:var(--green);font-weight:700;cursor:pointer}}
.tablewrap{{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:1050px}}th,td{{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{position:sticky;top:70px;background:#f8fbf9;color:var(--muted);font-size:11px;text-transform:uppercase}}a{{color:#176b45}}.sub,.muted{{color:var(--muted);font-size:11px;margin-top:4px}}.empty{{text-align:center;padding:35px}}.note{{color:var(--muted);margin:10px 2px}}
@media(max-width:700px){{header{{padding:14px}}main{{padding:12px}}.summary{{grid-template-columns:1fr}}input{{min-width:0;width:100%}}}}
</style></head><body><header><div><h1>BrokerBeacon Prospects</h1><div class="sub">Clean CRM and licensed mortgage-broker catalog</div></div><a href="/">Back to BrokerBeacon</a></header>
<main><section class="summary"><div class="card"><span>Visible prospects</span><strong>{len(items)}</strong></div><div class="card"><span>States represented</span><strong>{len([v for v in coverage.values() if v])}</strong></div><div class="card"><span>Daily growth</span><strong>Enabled</strong></div></section>
<form class="filters" method="get"><input name="q" value="{html.escape(query, quote=True)}" placeholder="Search company, city, or NMLS"><select name="state">{"".join(options)}</select><button type="submit">Apply filters</button></form>
<div class="note">Generic website-return titles are excluded. Verify licensing and contact details before outreach.</div>
<div class="tablewrap"><table><thead><tr><th>Company</th><th>Company / primary contact</th><th>Location</th><th>Loan officers</th><th>Source</th><th>Status</th></tr></thead><tbody>{body}</tbody></table></div></main></body></html>'''
        return Response(page, content_type="text/html; charset=utf-8")

    @app.after_request
    def route_prospects_navigation(response):
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            page = response.get_data(as_text=True)
        except Exception:
            return response
        if "brokerbeacon-prospects-route-v1" in page or "</body>" not in page.lower():
            return response
        script = '''<script id="brokerbeacon-prospects-route-v1">(function(){function wire(){document.querySelectorAll('nav button,aside button,[data-view]').forEach(function(b){var t=(b.textContent||'').trim().toLowerCase();if(t==='prospects'||t.startsWith('prospects ')){b.onclick=function(e){e.preventDefault();location.href='/prospects-catalog'}}})}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire()})();</script>'''
        pos = page.lower().rfind("</body>")
        page = page[:pos] + script + page[pos:]
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("PROSPECT_UI stable catalog route installed at /prospects-catalog")
    return app


__all__ = ["install_ember_prospects_bridge"]
