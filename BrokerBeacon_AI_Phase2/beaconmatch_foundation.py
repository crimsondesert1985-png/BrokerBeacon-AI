"""BeaconMatch enterprise foundation for lender-specific scenario intelligence.

This module stores lender profiles, programs, guideline sources, sanitized
scenario memories, and auditable match runs. It supports an AE's own lender
only and never represents final eligibility or approval.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from flask import g, jsonify, request

from scenario_rescue_engine import extract_facts

DISCLAIMER = (
    "Potential lender-fit guidance only. Final eligibility, pricing, approval, "
    "and underwriting decisions require current guideline verification and a "
    "qualified human review."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workspace_id() -> int:
    return int(getattr(g, "workspace_id", 0) or 0)


def _user_id() -> int:
    return int(getattr(g, "user_id", 0) or 0)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value: str | None, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _score_program(program: dict, facts: dict) -> dict:
    score = 50
    reasons: list[str] = []
    blockers: list[str] = []
    cautions: list[str] = []

    fico = facts.get("fico")
    min_fico = program.get("min_fico")
    max_fico = program.get("max_fico")
    if fico is not None and min_fico is not None:
        if fico < min_fico:
            blockers.append(f"FICO {fico} is below configured minimum {min_fico}")
            score -= 45
        else:
            score += 12
            reasons.append("FICO is within the configured program range")
    elif min_fico is not None:
        cautions.append("FICO is missing")
        score -= 6
    if fico is not None and max_fico is not None and fico > max_fico:
        cautions.append("FICO is above the configured range; verify this field")

    state = facts.get("state")
    states = program.get("states") or []
    if state and states:
        if state in states:
            score += 10
            reasons.append(f"Program is configured for {state}")
        else:
            blockers.append(f"Program is not configured for {state}")
            score -= 40
    elif states:
        cautions.append("Property state is missing")
        score -= 5

    transaction = facts.get("transaction")
    transactions = program.get("transactions") or []
    if transaction and transactions:
        if transaction in transactions:
            score += 8
            reasons.append(f"{transaction.title()} is supported")
        else:
            blockers.append(f"{transaction.title()} is not configured for this program")
            score -= 35

    occupancy = facts.get("occupancy")
    occupancies = program.get("occupancies") or []
    if occupancy and occupancies:
        if occupancy in occupancies:
            score += 8
            reasons.append(f"{occupancy.replace('_', ' ').title()} occupancy is supported")
        else:
            blockers.append("Occupancy is not configured for this program")
            score -= 35

    income_type = facts.get("income_type")
    income_types = program.get("income_types") or []
    if income_type and income_types:
        if income_type in income_types:
            score += 7
            reasons.append("Income type is supported")
        else:
            blockers.append("Income type is not configured for this program")
            score -= 30

    down = facts.get("down_payment_percent")
    min_down = program.get("min_down_payment_percent")
    if down is not None and min_down is not None:
        if float(down) >= float(min_down):
            score += 6
            reasons.append("Down payment meets the configured minimum")
        else:
            blockers.append(f"Down payment is below configured minimum {min_down}%")
            score -= 30

    if facts.get("recent_late"):
        cautions.append("Recent late payment requires exact dates and guideline review")
        score -= 8
    if facts.get("bankruptcy") or facts.get("foreclosure"):
        cautions.append("Major derogatory event requires seasoning verification")
        score -= 12

    guideline_state = program.get("guideline_state") or "unverified"
    if guideline_state == "verified":
        score += 5
        reasons.append("A verified guideline source is linked")
    else:
        cautions.append("No currently verified guideline source is linked")
        score -= 8

    score = max(0, min(100, score))
    status = "blocked" if blockers else "review" if cautions else "potential_fit"
    return {
        "program_id": program["id"],
        "program_name": program["name"],
        "program_code": program.get("code"),
        "score": score,
        "status": status,
        "reasons": reasons,
        "blockers": blockers,
        "cautions": cautions,
        "guideline_state": guideline_state,
    }


def install_beaconmatch_foundation(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.executescript(
            """
            create table if not exists beaconmatch_lenders(
                id integer primary key,
                workspace_id integer not null unique,
                name text not null,
                nmls_id text default '',
                notes text default '',
                created_at text not null,
                updated_at text not null
            );
            create table if not exists beaconmatch_guideline_sources(
                id integer primary key,
                workspace_id integer not null,
                title text not null,
                source_url text default '',
                source_type text not null default 'internal',
                effective_date text default '',
                expires_at text default '',
                verification_state text not null default 'unverified',
                verified_by integer not null default 0,
                verified_at text default '',
                created_at text not null,
                updated_at text not null
            );
            create table if not exists beaconmatch_programs(
                id integer primary key,
                workspace_id integer not null,
                lender_id integer not null,
                name text not null,
                code text default '',
                active integer not null default 1,
                min_fico integer,
                max_fico integer,
                min_down_payment_percent real,
                states_json text not null default '[]',
                transactions_json text not null default '[]',
                occupancies_json text not null default '[]',
                income_types_json text not null default '[]',
                tags_json text not null default '[]',
                guideline_source_id integer,
                created_at text not null,
                updated_at text not null
            );
            create table if not exists beaconmatch_match_runs(
                id integer primary key,
                workspace_id integer not null,
                user_id integer not null,
                scenario_text text not null,
                facts_json text not null,
                results_json text not null,
                disclaimer text not null,
                created_at text not null
            );
            create table if not exists beaconmatch_memories(
                id integer primary key,
                workspace_id integer not null,
                program_id integer,
                title text not null,
                sanitized_summary text not null,
                facts_json text not null default '{}',
                outcome text not null,
                lesson text default '',
                source_case_id integer,
                created_by integer not null default 0,
                created_at text not null,
                updated_at text not null
            );
            create index if not exists idx_bm_programs_workspace on beaconmatch_programs(workspace_id,active,id);
            create index if not exists idx_bm_sources_workspace on beaconmatch_guideline_sources(workspace_id,id);
            create index if not exists idx_bm_runs_workspace on beaconmatch_match_runs(workspace_id,id desc);
            create index if not exists idx_bm_memories_workspace on beaconmatch_memories(workspace_id,id desc);
            """
        )

    def lender_for_workspace(conn, workspace_id):
        return conn.execute(
            "select * from beaconmatch_lenders where workspace_id=?", (workspace_id,)
        ).fetchone()

    @app.get("/api/beaconmatch/foundation")
    def beaconmatch_foundation_status():
        workspace_id = _workspace_id()
        with connect() as conn:
            lender = lender_for_workspace(conn, workspace_id)
            counts = {
                "programs": conn.execute("select count(*) from beaconmatch_programs where workspace_id=?", (workspace_id,)).fetchone()[0],
                "sources": conn.execute("select count(*) from beaconmatch_guideline_sources where workspace_id=?", (workspace_id,)).fetchone()[0],
                "memories": conn.execute("select count(*) from beaconmatch_memories where workspace_id=?", (workspace_id,)).fetchone()[0],
                "match_runs": conn.execute("select count(*) from beaconmatch_match_runs where workspace_id=?", (workspace_id,)).fetchone()[0],
            }
        return jsonify(lender=dict(lender) if lender else None, counts=counts, disclaimer=DISCLAIMER)

    @app.put("/api/beaconmatch/lender")
    def beaconmatch_upsert_lender():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()[:160]
        if not name:
            return jsonify(error="Lender name is required"), 400
        workspace_id = _workspace_id()
        now = _now()
        with connect() as conn:
            conn.execute(
                """insert into beaconmatch_lenders(workspace_id,name,nmls_id,notes,created_at,updated_at)
                values(?,?,?,?,?,?)
                on conflict(workspace_id) do update set
                name=excluded.name,nmls_id=excluded.nmls_id,notes=excluded.notes,updated_at=excluded.updated_at""",
                (workspace_id, name, str(data.get("nmls_id") or "")[:80], str(data.get("notes") or "")[:2000], now, now),
            )
            lender = lender_for_workspace(conn, workspace_id)
        return jsonify(ok=True, lender=dict(lender))

    @app.post("/api/beaconmatch/guideline-sources")
    def beaconmatch_create_source():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()[:200]
        if not title:
            return jsonify(error="Source title is required"), 400
        state = (data.get("verification_state") or "unverified").lower()
        if state not in {"unverified", "verified", "stale", "retired"}:
            return jsonify(error="Invalid verification state"), 400
        now = _now()
        verified_at = now if state == "verified" else ""
        with connect() as conn:
            cur = conn.execute(
                """insert into beaconmatch_guideline_sources
                (workspace_id,title,source_url,source_type,effective_date,expires_at,verification_state,verified_by,verified_at,created_at,updated_at)
                values(?,?,?,?,?,?,?,?,?,?,?)""",
                (_workspace_id(), title, str(data.get("source_url") or "")[:1000], str(data.get("source_type") or "internal")[:50], str(data.get("effective_date") or "")[:30], str(data.get("expires_at") or "")[:30], state, _user_id() if state == "verified" else 0, verified_at, now, now),
            )
        return jsonify(ok=True, id=cur.lastrowid), 201

    @app.get("/api/beaconmatch/guideline-sources")
    def beaconmatch_list_sources():
        with connect() as conn:
            rows = conn.execute(
                "select * from beaconmatch_guideline_sources where workspace_id=? order by id desc", (_workspace_id(),)
            ).fetchall()
        return jsonify(items=[dict(row) for row in rows])

    @app.post("/api/beaconmatch/programs")
    def beaconmatch_create_program():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()[:200]
        if not name:
            return jsonify(error="Program name is required"), 400
        workspace_id = _workspace_id()
        now = _now()
        with connect() as conn:
            lender = lender_for_workspace(conn, workspace_id)
            if not lender:
                return jsonify(error="Configure the workspace lender before adding programs"), 409
            source_id = data.get("guideline_source_id")
            if source_id:
                source = conn.execute(
                    "select id from beaconmatch_guideline_sources where id=? and workspace_id=?", (int(source_id), workspace_id)
                ).fetchone()
                if not source:
                    return jsonify(error="Guideline source not found"), 404
            cur = conn.execute(
                """insert into beaconmatch_programs
                (workspace_id,lender_id,name,code,active,min_fico,max_fico,min_down_payment_percent,states_json,transactions_json,occupancies_json,income_types_json,tags_json,guideline_source_id,created_at,updated_at)
                values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (workspace_id, lender["id"], name, str(data.get("code") or "")[:80], 1 if data.get("active", True) else 0, data.get("min_fico"), data.get("max_fico"), data.get("min_down_payment_percent"), _json(data.get("states") or []), _json(data.get("transactions") or []), _json(data.get("occupancies") or []), _json(data.get("income_types") or []), _json(data.get("tags") or []), int(source_id) if source_id else None, now, now),
            )
        return jsonify(ok=True, id=cur.lastrowid), 201

    def program_rows(conn, workspace_id):
        rows = conn.execute(
            """select p.*,coalesce(s.verification_state,'unverified') as guideline_state
            from beaconmatch_programs p left join beaconmatch_guideline_sources s
            on s.id=p.guideline_source_id and s.workspace_id=p.workspace_id
            where p.workspace_id=? and p.active=1 order by p.id""", (workspace_id,)
        ).fetchall()
        programs = []
        for row in rows:
            item = dict(row)
            for column, key in [
                ("states_json", "states"), ("transactions_json", "transactions"),
                ("occupancies_json", "occupancies"), ("income_types_json", "income_types"),
                ("tags_json", "tags"),
            ]:
                item[key] = _loads(item.pop(column), [])
            programs.append(item)
        return programs

    @app.get("/api/beaconmatch/programs")
    def beaconmatch_list_programs():
        with connect() as conn:
            programs = program_rows(conn, _workspace_id())
        return jsonify(items=programs)

    @app.post("/api/beaconmatch/match")
    def beaconmatch_match():
        data = request.get_json(silent=True) or {}
        scenario = (data.get("scenario") or "").strip()
        if len(scenario) < 20:
            return jsonify(error="Enter a fuller scenario before matching"), 400
        workspace_id = _workspace_id()
        facts = extract_facts(scenario)
        with connect() as conn:
            programs = program_rows(conn, workspace_id)
            results = sorted((_score_program(program, facts) for program in programs), key=lambda item: item["score"], reverse=True)
            cur = conn.execute(
                """insert into beaconmatch_match_runs
                (workspace_id,user_id,scenario_text,facts_json,results_json,disclaimer,created_at)
                values(?,?,?,?,?,?,?)""",
                (workspace_id, _user_id(), scenario, _json(facts), _json(results), DISCLAIMER, _now()),
            )
        return jsonify(run_id=cur.lastrowid, facts=facts, results=results, disclaimer=DISCLAIMER)

    @app.get("/api/beaconmatch/match-runs")
    def beaconmatch_match_runs():
        with connect() as conn:
            rows = conn.execute(
                """select id,user_id,facts_json,results_json,created_at from beaconmatch_match_runs
                where workspace_id=? order by id desc limit 100""", (_workspace_id(),)
            ).fetchall()
        return jsonify(items=[{
            "id": row["id"], "user_id": row["user_id"], "facts": _loads(row["facts_json"], {}),
            "results": _loads(row["results_json"], []), "created_at": row["created_at"]
        } for row in rows])

    @app.post("/api/beaconmatch/memories")
    def beaconmatch_create_memory():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()[:200]
        summary = (data.get("sanitized_summary") or "").strip()[:4000]
        outcome = (data.get("outcome") or "").lower()
        if not title or not summary:
            return jsonify(error="Title and sanitized summary are required"), 400
        if outcome not in {"reviewed", "submitted", "approved", "denied", "withdrawn", "funded"}:
            return jsonify(error="Invalid memory outcome"), 400
        workspace_id = _workspace_id()
        program_id = data.get("program_id")
        now = _now()
        with connect() as conn:
            if program_id:
                program = conn.execute(
                    "select id from beaconmatch_programs where id=? and workspace_id=?", (int(program_id), workspace_id)
                ).fetchone()
                if not program:
                    return jsonify(error="Program not found"), 404
            cur = conn.execute(
                """insert into beaconmatch_memories
                (workspace_id,program_id,title,sanitized_summary,facts_json,outcome,lesson,source_case_id,created_by,created_at,updated_at)
                values(?,?,?,?,?,?,?,?,?,?,?)""",
                (workspace_id, int(program_id) if program_id else None, title, summary, _json(data.get("facts") or {}), outcome, str(data.get("lesson") or "")[:3000], data.get("source_case_id"), _user_id(), now, now),
            )
        return jsonify(ok=True, id=cur.lastrowid), 201

    @app.get("/api/beaconmatch/memories")
    def beaconmatch_list_memories():
        with connect() as conn:
            rows = conn.execute(
                """select id,program_id,title,sanitized_summary,facts_json,outcome,lesson,source_case_id,created_at,updated_at
                from beaconmatch_memories where workspace_id=? order by id desc limit 100""", (_workspace_id(),)
            ).fetchall()
        return jsonify(items=[{**dict(row), "facts": _loads(row["facts_json"], {})} for row in rows])

    return app


__all__ = ["install_beaconmatch_foundation", "DISCLAIMER", "_score_program"]
