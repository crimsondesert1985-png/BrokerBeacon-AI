"""Clean prospect catalog API without replacing BrokerBeacon's native Prospects UI.

The native Prospects screen already reads the CRM tables. Earlier versions injected a
second JavaScript renderer into every HTML response; that renderer could select the
wrong table, overwrite native rows, and repeatedly bind during worker restarts. This
module now leaves the application UI untouched and only provides a stable JSON API.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing

from flask import jsonify, request

STATE_CODES = tuple(
    "AL AK AZ AR CA CO CT DC DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA VT WA WV WI WY".split()
)
STATE_SET = set(STATE_CODES)
GENERIC_PATTERNS = (
    "annual report",
    "best mortgage brokers",
    "top loan officers",
    "broker near me",
    "department of savings",
    "division of banks",
    "real estate in ",
    "nmls esb",
    "cyber fbi",
    "mortgage lenders loan officers",
    "mortgage broker directory",
    "search results",
    "consumer access",
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

    @app.get("/api/ember/main-prospects")
    def main_prospects():
        requested = str(request.args.get("state") or "").strip().upper()
        state = requested if requested in STATE_SET else ""
        query = str(request.args.get("q") or "").strip()[:120]
        like = f"%{query.lower()}%"
        limit = min(max(int(request.args.get("limit") or 1000), 1), 5000)

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
                (state, state, query, like, like, like, limit),
            ).fetchall()

            items = []
            for prospect in rows:
                if _is_generic_name(prospect["company"]):
                    continue
                contacts = conn.execute(
                    """select * from contacts where prospect_id=?
                       order by coalesce(is_primary,0) desc,
                                coalesce(is_decision_maker,0) desc,id""",
                    (prospect["id"],),
                ).fetchall()
                primary = contacts[0] if contacts else None
                items.append(
                    {
                        "id": prospect["id"],
                        "crm_prospect_id": prospect["id"],
                        "company_name": prospect["company"],
                        "nmls_id": prospect["nmls"] or "",
                        "source_url": prospect["source_url"] or prospect["website"] or "",
                        "phone": prospect["phone"] or (primary["phone"] if primary else "") or "",
                        "public_email": prospect["email"] or (primary["email"] if primary else "") or "",
                        "city": prospect["city"] or "",
                        "state": prospect["state"] or "",
                        "review_status": prospect["verification_status"] or "Verify in NMLS",
                        "pipeline_status": prospect["status"] or "New",
                        "opportunity_score": int(prospect["score"] or 75),
                        "loan_officer_count": len(contacts),
                        "primary_contact": primary["name"] if primary else "",
                        "source": prospect["source_name"] or "BrokerBeacon CRM",
                        "record_type": "crm",
                    }
                )

            coverage = {
                row[0]: int(row[1])
                for row in conn.execute(
                    """select upper(state),count(*) from prospects
                       where upper(state) in (%s)
                       group by upper(state)"""
                    % ",".join("?" for _ in STATE_CODES),
                    STATE_CODES,
                ).fetchall()
            }

        return jsonify(
            items=items,
            states=list(STATE_CODES),
            coverage=coverage,
            count=len(items),
            selected_state=state,
            source="native_crm_catalog",
        )

    app.logger.warning(
        "PROSPECT_UI native screen restored; injected replacement renderer disabled"
    )
    return app


__all__ = ["install_ember_prospects_bridge"]
