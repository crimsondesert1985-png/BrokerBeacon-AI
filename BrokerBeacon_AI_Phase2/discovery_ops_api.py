"""Owner-only operations API for public search and website enrichment."""
from __future__ import annotations

import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from multi_search_provider import configured_providers, provider_leaderboard, search_all
from public_search_connector import build_queries, classify_result, initialize as init_public
from website_enrichment import dashboard as enrichment_dashboard
from website_enrichment import enqueue_search_results, initialize as init_enrichment, run_batch


def install_discovery_ops(app, db_path):
    bp = Blueprint("discovery_ops", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    with connect() as conn:
        init_public(conn)
        init_enrichment(conn)

    def is_owner():
        for user in (getattr(g, "saas_user", None), getattr(g, "current_user", None), getattr(g, "user", None)):
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
            if not is_owner():
                return jsonify(error="Platform owner access required", code="platform_owner_required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.get("/api/platform/discovery-ops")
    @owner_required
    def status():
        with connect() as conn:
            return jsonify({
                "configured_providers": configured_providers(),
                "provider_leaderboard": provider_leaderboard(conn),
                "enrichment": enrichment_dashboard(conn),
            })

    @bp.post("/api/platform/discovery/search")
    @owner_required
    def run_search():
        payload = request.get_json(silent=True) or {}
        state = str(payload.get("state") or "").strip().upper()
        metro = str(payload.get("metro") or "").strip()
        limit = min(max(int(payload.get("limit_per_provider") or 20), 1), 100)
        requested = payload.get("providers")
        providers = [p for p in (requested or configured_providers()) if p in configured_providers()]
        if not providers:
            return jsonify(error="No configured search providers are available"), 400
        queries = build_queries(state, metro)
        now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        totals = {"queries": 0, "results": 0, "unique": 0, "providers": providers}
        with connect() as conn:
            run_id = int(conn.execute(
                "insert into public_search_runs(state,status,created_at,started_at) values(?,'Running',?,?)",
                (state, now, now),
            ).lastrowid)
            conn.commit()
            try:
                seen = set()
                for query in queries:
                    result = search_all(query, limit_per_provider=limit, providers=providers)
                    totals["queries"] += 1
                    totals["results"] += sum(x.get("results", 0) for x in result["provider_stats"].values())
                    for provider, stats in result["provider_stats"].items():
                        conn.execute(
                            """insert into search_provider_runs(public_search_run_id,provider,query_text,result_count,
                               unique_count,duplicate_count,status,latency_ms,error,created_at,finished_at)
                               values(?,?,?,?,?,?,?,?,?,?,?)""",
                            (run_id, provider, query, stats.get("results", 0), stats.get("unique", 0),
                             stats.get("duplicates", 0), stats.get("status", "Failed"), stats.get("latency_ms", 0),
                             stats.get("error", ""), now, __import__("datetime").datetime.now().isoformat(timespec="seconds")),
                        )
                    for rank, item in enumerate(result["results"], start=1):
                        url = item["url"]
                        if url in seen:
                            continue
                        seen.add(url)
                        parsed = classify_result(item.get("title", ""), item.get("description", ""), url)
                        cur = conn.execute(
                            """insert or ignore into public_search_results(run_id,query_text,result_rank,title,snippet,
                               source_url,source_domain,candidate_type,company_name,person_name,state,nmls_id,phone,
                               public_email,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (run_id, query, rank, item.get("title", ""), item.get("description", ""), url,
                             __import__("urllib.parse").parse.urlparse(url).netloc.lower().removeprefix("www."),
                             parsed["candidate_type"], parsed["company_name"], parsed["person_name"], state,
                             parsed["nmls_id"], parsed["phone"], parsed["public_email"], now),
                        )
                        row = conn.execute("select id from public_search_results where run_id=? and source_url=?", (run_id, url)).fetchone()
                        if row:
                            for source in item.get("providers", []):
                                conn.execute(
                                    "insert or ignore into search_result_providers(public_search_result_id,provider,provider_rank,provider_url,created_at) values(?,?,?,?,?)",
                                    (row[0], source["provider"], source["rank"], url, now),
                                )
                    conn.commit()
                totals["unique"] = len(seen)
                finished = __import__("datetime").datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    """update public_search_runs set status='Completed',query_count=?,result_count=?,accepted_count=?,
                       finished_at=? where id=?""",
                    (totals["queries"], totals["results"], totals["unique"], finished, run_id),
                )
                conn.commit()
            except Exception as exc:
                finished = __import__("datetime").datetime.now().isoformat(timespec="seconds")
                conn.execute("update public_search_runs set status='Failed',error=?,finished_at=? where id=?", (str(exc)[:500], finished, run_id))
                conn.commit()
                raise
        return jsonify({"run_id": run_id, **totals}), 201

    @bp.post("/api/platform/discovery/enrichment/enqueue")
    @owner_required
    def enqueue_enrichment():
        payload = request.get_json(silent=True) or {}
        with connect() as conn:
            count = enqueue_search_results(conn, state=str(payload.get("state") or ""), limit=int(payload.get("limit") or 5000))
        return jsonify(enqueued=count), 201

    @bp.post("/api/platform/discovery/enrichment/run")
    @owner_required
    def execute_enrichment():
        payload = request.get_json(silent=True) or {}
        with connect() as conn:
            result = run_batch(
                conn,
                state=str(payload.get("state") or ""),
                batch_size=min(max(int(payload.get("batch_size") or 100), 1), 1000),
                per_domain_limit=min(max(int(payload.get("per_domain_limit") or 3), 1), 10),
                delay_seconds=max(float(payload.get("delay_seconds") or 0.4), 0.0),
            )
        return jsonify(result), 201

    app.register_blueprint(bp)
    return bp
