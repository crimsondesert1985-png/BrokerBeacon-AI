"""Release health checks for BrokerBeacon Sprint 37."""
import sqlite3
from datetime import datetime, timezone
from flask import Blueprint, jsonify

REQUIRED_TABLES = (
    "warehouse_companies",
    "warehouse_loan_officers",
    "public_search_runs",
    "website_enrichment_jobs",
    "discovered_contacts",
    "ai_agents",
    "autonomy_policies",
    "growth_objectives",
)


def install_release_health(app, db_path):
    bp = Blueprint("release_health", __name__)

    @bp.get("/healthz")
    def healthz():
        return jsonify(
            ok=True,
            service="BrokerBeacon-AI",
            release="Sprint 37",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    @bp.get("/readyz")
    def readyz():
        missing = []
        error = ""
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            names = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
            conn.execute("select 1").fetchone()
            conn.close()
            missing = [name for name in REQUIRED_TABLES if name not in names]
        except Exception as exc:
            error = str(exc)[:300]
        ok = not missing and not error
        return jsonify(ok=ok, missing_tables=missing, error=error), 200 if ok else 503

    app.register_blueprint(bp)
    return bp
