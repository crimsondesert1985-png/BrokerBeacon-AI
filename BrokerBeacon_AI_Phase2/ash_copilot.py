"""Responsive in-product Ash copilot for BrokerBeacon.

Ash reasons over live BrokerBeacon context, delegates to specialist agents, and
stores approved conversation memory. The implementation uses OpenAI when
configured and a fast deterministic fallback otherwise.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

from ai_orchestrator import agent_context, initialize as init_agents, route_task
from autonomy_engine import dashboard as autonomy_dashboard
from growth_mission import dashboard as growth_dashboard
from intelligence_network import dashboard as network_dashboard

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists copilot_conversations(
    id integer primary key,
    user_key text not null,
    title text default '',
    created_at text not null,
    updated_at text not null
);
create table if not exists copilot_messages(
    id integer primary key,
    conversation_id integer not null,
    role text not null,
    content text not null,
    agent_key text default 'ash',
    metadata_json text not null default '{}',
    created_at text not null,
    foreign key(conversation_id) references copilot_conversations(id)
);
create table if not exists copilot_preferences(
    id integer primary key,
    user_key text not null,
    preference_key text not null,
    value_json text not null,
    approved integer not null default 0,
    created_at text not null,
    updated_at text not null,
    unique(user_key,preference_key)
);
create index if not exists idx_copilot_messages_conversation on copilot_messages(conversation_id,id);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    init_agents(conn)
    conn.commit()


def _extract_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    return ""


def _live_context(conn: sqlite3.Connection) -> dict:
    def scalar(sql: str) -> int:
        try:
            return int(conn.execute(sql).fetchone()[0] or 0)
        except sqlite3.DatabaseError:
            return 0
    return {
        "warehouse_companies": scalar("select count(*) from warehouse_companies"),
        "warehouse_officers": scalar("select count(*) from warehouse_loan_officers"),
        "discovered_contacts": scalar("select count(*) from discovered_contacts"),
        "pending_review": scalar("select count(*) from discovered_contacts where review_status='Pending review'"),
        "high_opportunity": scalar("select count(*) from ai_contact_insights where opportunity_score>=75"),
        "autonomy": autonomy_dashboard(conn),
        "growth": growth_dashboard(conn),
        "network": network_dashboard(conn),
    }


def _preferences(conn: sqlite3.Connection, user_key: str) -> dict:
    rows = conn.execute(
        "select preference_key,value_json from copilot_preferences where user_key=? and approved=1",
        (user_key,),
    ).fetchall()
    result = {}
    for row in rows:
        try:
            result[row[0]] = json.loads(row[1])
        except Exception:
            result[row[0]] = row[1]
    return result


def _history(conn: sqlite3.Connection, conversation_id: int, limit: int = 12) -> list[dict]:
    rows = conn.execute(
        """select role,content,agent_key from copilot_messages where conversation_id=?
           order by id desc limit ?""",
        (conversation_id, min(max(int(limit), 1), 40)),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def _fallback_answer(message: str, specialist: str, context: dict) -> str:
    lower = message.lower()
    if "how many" in lower or "count" in lower:
        return (
            f"BrokerBeacon currently has {context['warehouse_companies']:,} warehouse companies, "
            f"{context['warehouse_officers']:,} warehouse loan officers, and "
            f"{context['discovered_contacts']:,} discovered contacts. "
            f"{context['pending_review']:,} are waiting for review."
        )
    if "next" in lower or "recommend" in lower:
        plan = (context.get("autonomy") or {}).get("plan") or {}
        if plan.get("status") == "Ready":
            return f"My recommended next move is to process {plan.get('state', 'the next approved state')} using the planned guarded actions, then review the highest-opportunity results before expanding further."
        return "My recommended next move is to configure approved states and a daily budget in the Control Tower, then run one guarded growth cycle and review the results."
    return (
        f"I routed this to {specialist.title()}. I can answer from BrokerBeacon's live database, "
        "but the full conversational model is not configured yet. Add OPENAI_API_KEY to enable richer reasoning and faster specialist collaboration."
    )


def answer(conn: sqlite3.Connection, *, user_key: str, conversation_id: int,
           message: str) -> dict:
    initialize(conn)
    specialist = route_task(message)
    context = _live_context(conn)
    preferences = _preferences(conn, user_key)
    history = _history(conn, conversation_id)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_COPILOT_MODEL", "gpt-5").strip()
    response_text = ""
    confidence = 70
    if key:
        agent = agent_context(conn, specialist)
        instructions = (
            "You are Ash, BrokerBeacon's executive AI copilot. Be warm, decisive, concise, and honest. "
            "Use only the supplied BrokerBeacon context for factual claims. Delegate mentally to the named specialist, "
            "but answer as one coherent assistant. Never claim an action happened unless context confirms it. "
            "Do not initiate outreach, change permissions, or bypass owner guardrails. When uncertain, say what must be verified. "
            "Return plain text, not JSON."
        )
        payload = {
            "model": model,
            "store": False,
            "instructions": instructions,
            "input": json.dumps({
                "message": message,
                "delegated_specialist": specialist,
                "specialist_profile": agent,
                "approved_preferences": preferences,
                "conversation_history": history,
                "live_brokerbeacon_context": context,
            }, ensure_ascii=True, default=str),
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                response_text = _extract_text(json.loads(response.read().decode("utf-8"))).strip()
            confidence = 85
        except Exception as exc:
            response_text = _fallback_answer(message, specialist, context)
            confidence = 55
            context["model_error"] = str(exc)[:160]
    else:
        response_text = _fallback_answer(message, specialist, context)
        model = "deterministic-fallback"
        confidence = 55

    now = NOW()
    conn.execute(
        "insert into copilot_messages(conversation_id,role,content,agent_key,metadata_json,created_at) values(?,?,?,?,?,?)",
        (conversation_id, "user", message, "user", "{}", now),
    )
    conn.execute(
        "insert into copilot_messages(conversation_id,role,content,agent_key,metadata_json,created_at) values(?,?,?,?,?,?)",
        (conversation_id, "assistant", response_text, specialist,
         json.dumps({"model": model, "confidence": confidence}, sort_keys=True), NOW()),
    )
    conn.execute("update copilot_conversations set updated_at=? where id=?", (NOW(), conversation_id))
    conn.commit()
    return {"answer": response_text, "specialist": specialist, "model": model, "confidence": confidence}


def install_ash_copilot(app, db_path):
    bp = Blueprint("ash_copilot", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        initialize(conn)
        return conn

    def user_key() -> str:
        for key in ("user_id", "email", "username"):
            value = session.get(key)
            if value:
                return str(value)
        return "platform-owner" if session.get("is_platform_owner") else "anonymous"

    def owner_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            allowed = bool(session.get("is_platform_owner"))
            for user in (getattr(g, "saas_user", None), getattr(g, "current_user", None), getattr(g, "user", None)):
                if user is None:
                    continue
                try:
                    allowed = allowed or bool(user["is_platform_owner"])
                except (KeyError, TypeError):
                    allowed = allowed or bool(getattr(user, "is_platform_owner", 0))
            if not allowed:
                return jsonify(error="Platform owner access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    @bp.post("/api/platform/copilot/conversations")
    @owner_required
    def create_conversation():
        payload = request.get_json(silent=True) or {}
        now = NOW()
        with connect() as conn:
            cur = conn.execute(
                "insert into copilot_conversations(user_key,title,created_at,updated_at) values(?,?,?,?)",
                (user_key(), str(payload.get("title") or "New conversation")[:160], now, now),
            )
            conn.commit()
            return jsonify(conversation_id=int(cur.lastrowid)), 201

    @bp.post("/api/platform/copilot/chat")
    @owner_required
    def chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message") or "").strip()
        if not message:
            return jsonify(error="Message is required"), 400
        with connect() as conn:
            conversation_id = payload.get("conversation_id")
            if not conversation_id:
                now = NOW()
                conversation_id = int(conn.execute(
                    "insert into copilot_conversations(user_key,title,created_at,updated_at) values(?,?,?,?)",
                    (user_key(), message[:80], now, now),
                ).lastrowid)
                conn.commit()
            result = answer(conn, user_key=user_key(), conversation_id=int(conversation_id), message=message)
        return jsonify({"conversation_id": int(conversation_id), **result})

    @bp.post("/api/platform/copilot/preferences")
    @owner_required
    def save_preference():
        payload = request.get_json(silent=True) or {}
        key = str(payload.get("key") or "").strip()
        if not key:
            return jsonify(error="Preference key is required"), 400
        now = NOW()
        with connect() as conn:
            conn.execute(
                """insert into copilot_preferences(user_key,preference_key,value_json,approved,created_at,updated_at)
                   values(?,?,?,?,?,?) on conflict(user_key,preference_key) do update set
                   value_json=excluded.value_json,approved=excluded.approved,updated_at=excluded.updated_at""",
                (user_key(), key, json.dumps(payload.get("value"), default=str), int(bool(payload.get("approved", True))), now, now),
            )
            conn.commit()
        return jsonify(ok=True)

    app.register_blueprint(bp)
    return bp
