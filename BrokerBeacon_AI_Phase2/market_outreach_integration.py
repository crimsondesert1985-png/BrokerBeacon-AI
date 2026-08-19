"""Integrate daily mortgage-market context into BrokerBeacon outreach workflows.

The integration is deliberately suggestion-first: approved drip copy is never
silently rewritten after approval. Instead, due-message payloads, AI coaching
jobs, and outreach surfaces receive a current market angle plus guardrails.
"""
from __future__ import annotations

from functools import wraps

from flask import jsonify

from market_productivity import market_context_payload


_INSTALLED = False


def _market_suggestion(context: dict, item: dict) -> dict:
    channel = str(item.get("channel") or "email").lower()
    angle = context.get("email_angle") if channel == "email" else context.get("call_angle")
    return {
        "date": context.get("date"),
        "angle": angle or context.get("talking_point", ""),
        "headline": (context.get("headlines") or [""])[0],
        "guardrail": context.get("guardrail", ""),
        "usage": "Optional suggestion. Review before adding to approved campaign copy.",
    }


def install_market_outreach_integration(app, db_path):
    global _INSTALLED
    if _INSTALLED:
        return app
    _INSTALLED = True

    # Enrich the existing due-message endpoint without changing approved bodies.
    original_due = app.view_functions.get("due_drip_messages")
    if original_due is not None:
        @wraps(original_due)
        def due_with_market_context(*args, **kwargs):
            response = original_due(*args, **kwargs)
            # Flask view functions may return Response or (Response, status).
            status = None
            headers = None
            raw = response
            if isinstance(response, tuple):
                raw = response[0]
                if len(response) > 1:
                    status = response[1]
                if len(response) > 2:
                    headers = response[2]
            try:
                payload = raw.get_json(silent=True) or {}
            except Exception:
                return response
            try:
                context = market_context_payload(db_path)
            except Exception:
                context = {"headlines": [], "talking_point": "Market context unavailable", "guardrail": "Review all claims before outreach."}
            payload["market_context"] = context
            for item in payload.get("items") or []:
                item["market_suggestion"] = _market_suggestion(context, item)
            updated = jsonify(payload)
            if status is not None and headers is not None:
                return updated, status, headers
            if status is not None:
                return updated, status
            return updated
        app.view_functions["due_drip_messages"] = due_with_market_context

    # Make newly queued sales-coach/outreach AI tasks market-aware. We patch both
    # the orchestrator module and autonomy_engine's imported reference when loaded.
    try:
        import ai_orchestrator
        original_queue = ai_orchestrator.queue_task
        if not getattr(original_queue, "_bb_market_aware", False):
            @wraps(original_queue)
            def queue_task_with_market(conn, agent_key, task_type, payload, entity_type="", entity_id=None, priority=50):
                enriched = dict(payload or {})
                task_text = str(task_type or "").lower()
                if agent_key == "coach" or any(token in task_text for token in ("outreach", "email", "call", "script", "coach", "marketing", "campaign")):
                    try:
                        enriched.setdefault("market_context", market_context_payload(db_path))
                    except Exception:
                        pass
                return original_queue(conn, agent_key, task_type, enriched, entity_type, entity_id, priority)
            queue_task_with_market._bb_market_aware = True
            ai_orchestrator.queue_task = queue_task_with_market
            try:
                import autonomy_engine
                autonomy_engine.queue_task = queue_task_with_market
            except Exception:
                pass
    except Exception:
        app.logger.exception("MARKET_OUTREACH AI queue integration failed safely")

    app.logger.warning("MARKET_OUTREACH integrated market context into drip suggestions and coaching AI tasks")
    return app


__all__ = ["install_market_outreach_integration"]
