"""Production safety tuning for Ember's always-on worker.

The worker historically promoted a requested six-company cycle to a minimum of
50 companies, causing each state hunt to fan out into too many search/crawl
operations. Clamp the runtime pipeline to a small continuous batch instead.
"""
from __future__ import annotations


def install_ember_runtime_patch(app=None) -> None:
    import ember_worker
    import ember_pipeline

    original = ember_pipeline.launch

    def bounded_launch(conn, *, state="", company_limit=50, contact_limit=1000):
        # Small batches finish reliably and allow the national queue to advance.
        # Repeated cycles provide breadth without long-running single jobs.
        effective_companies = max(6, min(int(company_limit or 12), 12))
        effective_contacts = max(100, min(int(contact_limit or 300), 500))
        return original(
            conn,
            state=state,
            company_limit=effective_companies,
            contact_limit=effective_contacts,
        )

    ember_worker.launch = bounded_launch
    if app is not None:
        app.logger.warning("EMBER_RUNTIME bounded_hunts company_limit=12 contact_limit=500")


__all__ = ["install_ember_runtime_patch"]
