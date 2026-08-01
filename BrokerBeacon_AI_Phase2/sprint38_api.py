"""Sprint 38 interactive prospect review and drill-down APIs."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from ai_intelligence import initialize as init_ai
from public_search_connector import initialize as init_public
from website_enrichment import initialize as init_enrichment


def install_sprint38_api(app, db_path):
    bp = Blueprint("sprint38", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        init_public(conn)
        init_enrichment(conn)
        init_ai(conn)

    def is_owner():
        return bool(getattr(g, "is_platform_owner", False) or session.get("is_platform_owner"))

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not is_owner():
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/sprint38/contacts")
    @owner_required
    def contacts():
        status = (request.args.get("status") or "").strip()
        state = (request.args.get("state") or "").strip().upper()[:2]
        high_only = (request.args.get("high") or "") in {"1", "true", "yes"}
        limit = min(max(int(request.args.get("limit") or 100), 1), 500)
        where, args = ["1=1"], []
        if status:
            where.append("d.review_status=?")
            args.append(status)
        if state:
            where.append("d.state=?")
            args.append(state)
        if high_only:
            where.append("coalesce(a.opportunity_score,0)>=75")
        args.append(limit)
        sql = f"""
            select d.*, coalesce(a.opportunity_score,0) opportunity_score,
                   coalesce(a.confidence,d.confidence) ai_confidence,
                   coalesce(a.product_fit,'') product_fit,
                   coalesce(a.next_best_action,'') next_best_action,
                   coalesce(a.reasons_json,'[]') reasons_json,
                   coalesce(a.reviewed_status,d.review_status) ai_review_status
            from discovered_contacts d
            left join ai_contact_insights a on a.discovered_contact_id=d.id
            where {' and '.join(where)}
            order by opportunity_score desc, d.id desc limit ?
        """
        with connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, args).fetchall()]
        return jsonify(items=rows, count=len(rows))

    @bp.get("/api/platform/sprint38/contacts/<int:contact_id>")
    @owner_required
    def contact_detail(contact_id):
        with connect() as conn:
            row = conn.execute("""
                select d.*, coalesce(a.opportunity_score,0) opportunity_score,
                       coalesce(a.confidence,d.confidence) ai_confidence,
                       coalesce(a.product_fit,'') product_fit,
                       coalesce(a.next_best_action,'') next_best_action,
                       coalesce(a.reasons_json,'[]') reasons_json,
                       coalesce(a.canonical_company_name,d.company_name) canonical_company_name,
                       coalesce(a.canonical_person_name,d.person_name) canonical_person_name
                from discovered_contacts d
                left join ai_contact_insights a on a.discovered_contact_id=d.id
                where d.id=?
            """, (contact_id,)).fetchone()
        if not row:
            return jsonify(error="Contact not found"), 404
        return jsonify(dict(row))

    @bp.post("/api/platform/sprint38/contacts/<int:contact_id>/review")
    @owner_required
    def review_contact(contact_id):
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "").strip().lower()
        mapping = {"approve": "Approved", "reject": "Rejected", "pending": "Pending review", "favorite": "Favorite"}
        if action not in mapping:
            return jsonify(error="Action must be approve, reject, pending, or favorite"), 400
        status = mapping[action]
        with connect() as conn:
            exists = conn.execute("select id from discovered_contacts where id=?", (contact_id,)).fetchone()
            if not exists:
                return jsonify(error="Contact not found"), 404
            conn.execute("update discovered_contacts set review_status=? where id=?", (status, contact_id))
            conn.execute("update ai_contact_insights set reviewed_status=? where discovered_contact_id=?", (status, contact_id))
            conn.commit()
        return jsonify(id=contact_id, review_status=status, outreach_performed=False)

    @bp.get("/api/platform/sprint38/companies")
    @owner_required
    def companies():
        state = (request.args.get("state") or "").strip().upper()[:2]
        limit = min(max(int(request.args.get("limit") or 100), 1), 500)
        with connect() as conn:
            rows = conn.execute("""
                select p.company_name, p.state, p.city, p.source_url, p.source_domain,
                       max(p.created_at) discovered_at,
                       count(distinct d.id) contact_count,
                       max(coalesce(a.opportunity_score,0)) top_score,
                       sum(case when d.review_status='Pending review' then 1 else 0 end) pending_count
                from public_search_results p
                left join discovered_contacts d on d.search_result_id=p.id
                left join ai_contact_insights a on a.discovered_contact_id=d.id
                where p.candidate_type='Company' and trim(p.company_name)<>''
                  and (?='' or p.state=?)
                group by p.company_name,p.state,p.city,p.source_url,p.source_domain
                order by top_score desc, contact_count desc, discovered_at desc
                limit ?
            """, (state, state, limit)).fetchall()
        return jsonify(items=[dict(row) for row in rows], count=len(rows))

    @bp.get("/api/platform/sprint38/companies/detail")
    @owner_required
    def company_detail():
        name = (request.args.get("name") or "").strip()
        if not name:
            return jsonify(error="Company name is required"), 400
        with connect() as conn:
            company = conn.execute("""
                select company_name,state,city,source_url,source_domain,max(created_at) discovered_at
                from public_search_results where company_name=? group by company_name,state,city,source_url,source_domain
                order by discovered_at desc limit 1
            """, (name,)).fetchone()
            contacts = conn.execute("""
                select d.*,coalesce(a.opportunity_score,0) opportunity_score,
                       coalesce(a.next_best_action,'') next_best_action
                from discovered_contacts d left join ai_contact_insights a on a.discovered_contact_id=d.id
                where d.company_name=? order by opportunity_score desc,d.id desc
            """, (name,)).fetchall()
        if not company:
            return jsonify(error="Company not found"), 404
        return jsonify(company=dict(company), contacts=[dict(row) for row in contacts])

    app.register_blueprint(bp)
    return bp
