"""Create all Sprint 37 schemas deterministically during application startup."""
import sqlite3

from ai_intelligence import initialize as init_ai_intelligence
from ai_orchestrator import initialize as init_ai_agents
from ash_copilot import initialize as init_copilot
from autonomy_engine import initialize as init_autonomy
from growth_mission import initialize as init_growth
from intelligence_network import initialize as init_network
from multi_search_provider import initialize as init_multi_search
from public_search_connector import initialize as init_public_search
from state_connectors import initialize as init_state_connectors
from website_enrichment import initialize as init_website_enrichment


def bootstrap_release(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    initializers = (
        init_public_search,
        init_multi_search,
        init_website_enrichment,
        init_state_connectors,
        init_ai_intelligence,
        init_ai_agents,
        init_autonomy,
        init_growth,
        init_network,
        init_copilot,
    )
    for initializer in initializers:
        initializer(conn)
    conn.commit()
    conn.close()
