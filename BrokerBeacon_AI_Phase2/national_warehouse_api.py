"""Owner-only REST API for the Sprint 37 national prospect warehouse."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from national_warehouse import (
    create_import_job,
    create_source,
    dashboard,
    ingest_companies,
    initialize,
    search,
)


def install_national_warehouse(app, db_path):
    bp = Blueprint("national_warehouse", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        initialize(conn)

    def owner_context():
        candidates = [
            getattr(g, "saas_user", None),
            getattr(g, "current_user", None),
            getattr(g, "user", None),
        ]
        for user in candidates:
            if user is None:
                continue
            try:
                value = user["is_platform_owner"]
            except (KeyError, TypeError):
                value = getattr(user, "is_platform_owner", 0)
            if bool(value):
                return True
        return bool(session.get("is_platform_owner"))

    def platform_owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not owner_context():
                return jsonify({
                    "error": "Platform owner access required",
                    "code": "platform_owner_required",
                }), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/warehouse")
    @platform_owner_required
    def warehouse_dashboard():
        with connect() as conn:
            return jsonify(dashboard(conn))

    @bp.get("/api/platform/warehouse/search")
    @platform_owner_required
    def warehouse_search():
        query = (request.args.get("q") or "").strip()[:160]
        state = (request.args.get("state") or "").strip().upper()[:2]
        limit = min(max(int(request.args.get("limit") or 50), 1), 200)
        with connect() as conn:
            return jsonify(search(conn, query=query, state=state, limit=limit))

    @bp.post("/api/platform/warehouse/sources")
    @platform_owner_required
    def warehouse_create_source():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name") or "").strip()
        source_type = str(payload.get("source_type") or "").strip()
        authorization_basis = str(payload.get("authorization_basis") or "").strip()
        source_url = str(payload.get("source_url") or "").strip()
        if not name or not source_type or not authorization_basis:
            return jsonify({"error": "Name, source type, and authorization basis are required"}), 400
        with connect() as conn:
            source_id = create_source(conn, name, source_type, authorization_basis, source_url)
        return jsonify({"source_id": source_id, "status": "ready"}), 201

    @bp.post("/api/platform/warehouse/imports")
    @platform_owner_required
    def warehouse_import():
        payload = request.get_json(silent=True) or {}
        records = payload.get("records") or []
        if not isinstance(records, list) or not records:
            return jsonify({"error": "A non-empty records array is required"}), 400
        if len(records) > 5000:
            return jsonify({"error": "Imports are limited to 5,000 records per request"}), 413
        source_id = payload.get("source_id")
        state = str(payload.get("state") or "").strip().upper()[:2]
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            return jsonify({"error": "A valid source_id is required"}), 400
        with connect() as conn:
            source = conn.execute(
                "select id,active,authorization_basis from warehouse_sources where id=?", (source_id,)
            ).fetchone()
            if not source or not source["active"]:
                return jsonify({"error": "The selected data source is unavailable"}), 400
            if not str(source["authorization_basis"] or "").strip():
                return jsonify({"error": "The data source must document its authorization basis"}), 400
            job_id = create_import_job(conn, source_id, state)
            try:
                counts = ingest_companies(conn, job_id, source_id, records)
            except Exception as exc:
                now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    "update warehouse_import_jobs set status='Failed',error=?,finished_at=?,updated_at=? where id=?",
                    (str(exc)[:500], now, now, job_id),
                )
                conn.commit()
                app.logger.exception("National warehouse import failed")
                return jsonify({"job_id": job_id, "status": "Failed", "error": "Import failed"}), 500
        return jsonify({"job_id": job_id, "status": "Completed", "counts": counts}), 201

    app.register_blueprint(bp)
    app.extensions["national_warehouse"] = {"db_path": str(db_path)}
    return bp
