"""Platform-owner API for state connector operations in the unified Control Tower."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from state_connectors import (
    control_tower_status,
    initialize,
    mark_connector_health,
    queue_state_import,
    register_connector,
)


def install_state_connectors(app, db_path):
    bp = Blueprint("state_connectors", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        initialize(conn)

    def is_platform_owner():
        for user in (
            getattr(g, "saas_user", None),
            getattr(g, "current_user", None),
            getattr(g, "user", None),
        ):
            if user is None:
                continue
            try:
                if bool(user["is_platform_owner"]):
                    return True
            except (KeyError, TypeError):
                if bool(getattr(user, "is_platform_owner", 0)):
                    return True
        return bool(session.get("is_platform_owner"))

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not is_platform_owner():
                return jsonify(error="Platform owner access required", code="platform_owner_required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/connectors")
    @owner_required
    def connector_status():
        with connect() as conn:
            return jsonify(control_tower_status(conn))

    @bp.post("/api/platform/connectors")
    @owner_required
    def connector_create():
        payload = request.get_json(silent=True) or {}
        try:
            source_id = int(payload.get("source_id"))
            with connect() as conn:
                source = conn.execute(
                    "select id,active,authorization_basis from warehouse_sources where id=?", (source_id,)
                ).fetchone()
                if not source or not source["active"]:
                    return jsonify(error="The selected source is unavailable"), 400
                if not str(source["authorization_basis"] or "").strip():
                    return jsonify(error="The source must document its authorization basis"), 400
                connector_id = register_connector(
                    conn,
                    source_id=source_id,
                    connector_key=str(payload.get("connector_key") or "").strip(),
                    label=str(payload.get("label") or "").strip(),
                    connector_type=str(payload.get("connector_type") or "").strip(),
                    states=payload.get("states") or [],
                    refresh_hours=int(payload.get("refresh_hours") or 168),
                    status=str(payload.get("status") or "Draft"),
                )
            return jsonify(connector_id=connector_id, status="saved"), 201
        except (TypeError, ValueError) as exc:
            return jsonify(error=str(exc)), 400

    @bp.post("/api/platform/connectors/<int:connector_id>/queue")
    @owner_required
    def connector_queue(connector_id):
        payload = request.get_json(silent=True) or {}
        try:
            with connect() as conn:
                queue_id = queue_state_import(
                    conn,
                    connector_id,
                    str(payload.get("state") or ""),
                    requested_by=str(payload.get("requested_by") or "Platform Owner"),
                    priority=int(payload.get("priority") or 50),
                )
            return jsonify(queue_id=queue_id, status="Queued"), 201
        except (TypeError, ValueError) as exc:
            return jsonify(error=str(exc)), 400

    @bp.post("/api/platform/connectors/<int:connector_id>/health")
    @owner_required
    def connector_health(connector_id):
        payload = request.get_json(silent=True) or {}
        healthy = bool(payload.get("healthy"))
        error = str(payload.get("error") or "")
        with connect() as conn:
            exists = conn.execute("select id from state_connectors where id=?", (connector_id,)).fetchone()
            if not exists:
                return jsonify(error="Connector not found"), 404
            mark_connector_health(conn, connector_id, healthy=healthy, error=error)
        return jsonify(ok=True, health_status="Healthy" if healthy else "Error")

    @bp.post("/api/platform/connector-queue/<int:queue_id>/retry")
    @owner_required
    def retry_queue_item(queue_id):
        with connect() as conn:
            row = conn.execute("select id,status from state_import_queue where id=?", (queue_id,)).fetchone()
            if not row:
                return jsonify(error="Queue item not found"), 404
            if row["status"] not in ("Failed", "Completed", "Cancelled"):
                return jsonify(error="Only completed, failed, or cancelled items can be queued again"), 400
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            conn.execute(
                """update state_import_queue set status='Queued',error='',next_attempt_at='',
                   started_at='',finished_at='',updated_at=? where id=?""",
                (now, queue_id),
            )
            conn.commit()
        return jsonify(ok=True, status="Queued")

    @bp.post("/api/platform/connector-queue/<int:queue_id>/cancel")
    @owner_required
    def cancel_queue_item(queue_id):
        with connect() as conn:
            row = conn.execute("select id,status from state_import_queue where id=?", (queue_id,)).fetchone()
            if not row:
                return jsonify(error="Queue item not found"), 404
            if row["status"] == "Running":
                return jsonify(error="Running imports cannot be cancelled from this control"), 409
            now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "update state_import_queue set status='Cancelled',finished_at=?,updated_at=? where id=?",
                (now, now, queue_id),
            )
            conn.commit()
        return jsonify(ok=True, status="Cancelled")

    app.register_blueprint(bp)
    app.extensions["state_connectors"] = {"db_path": str(db_path)}
    return bp
