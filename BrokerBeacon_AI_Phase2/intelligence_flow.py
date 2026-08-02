"""Connect completed Ember hunts to the shared intelligence graph.

This layer is deliberately compact: it updates durable company/person relationships,
then returns only the decision-sized facts Mission Control needs.
"""
from __future__ import annotations

import sqlite3

from intelligence_network import dashboard, initialize, sync_discoveries


def advance_intelligence(conn: sqlite3.Connection, *, state: str = "", limit: int = 1500) -> dict:
    """Synchronize recent discoveries without ever breaking the discovery worker."""
    initialize(conn)
    try:
        synced = sync_discoveries(conn, limit=max(1, min(int(limit), 5000)))
    except sqlite3.OperationalError as exc:
        return {
            "status": "Deferred",
            "state": state,
            "reason": str(exc),
            "company_nodes": 0,
            "person_nodes": 0,
            "relationships": 0,
        }

    snapshot = dashboard(conn)
    nodes = snapshot.get("nodes") or {}
    edges = snapshot.get("edges") or {}
    return {
        "status": "Advanced",
        "state": state,
        "company_nodes": int(nodes.get("company", 0) or 0),
        "person_nodes": int(nodes.get("person", 0) or 0),
        "relationships": int(sum(int(value or 0) for value in edges.values())),
        "new_company_links": int(synced.get("company_nodes", 0) or 0),
        "new_person_links": int(synced.get("person_nodes", 0) or 0),
        "next_stage": "Human review",
    }
