"""Runtime resilience patch for Ember public search and bounded hunts.

Adds a second no-key HTML search fallback so transient DuckDuckGo blocking does
not stop official-site resolution or Mortgage Matchup discovery. The normal API
providers remain preferred whenever configured.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

import multi_search_provider as multi


def _bing_html(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "count": min(max(int(limit), 1), 50), "setlang": "en-US"})
    req = urllib.request.Request(
        "https://www.bing.com/search?" + params,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=18) as response:
        body = response.read(2_000_000).decode("utf-8", "ignore")
    blocks = re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', body, re.I | re.S)
    results = []
    for block in blocks:
        anchor = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not anchor:
            anchor = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not anchor:
            continue
        url = html.unescape(anchor.group(1))
        title = html.unescape(re.sub(r"<[^>]+>", " ", anchor.group(2)))
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.I | re.S)
        snippet = html.unescape(re.sub(r"<[^>]+>", " ", snippet_match.group(1))) if snippet_match else ""
        if url.startswith(("http://", "https://")):
            results.append({
                "title": re.sub(r"\s+", " ", title).strip(),
                "description": re.sub(r"\s+", " ", snippet).strip(),
                "url": url,
            })
        if len(results) >= limit:
            break
    if not results:
        raise RuntimeError("Bing HTML fallback returned no parseable results")
    return results


def resilient_providers() -> list[str]:
    providers = []
    if multi.os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        providers.append("brave")
    if multi.os.getenv("TAVILY_API_KEY", "").strip():
        providers.append("tavily")
    if multi.os.getenv("FIRECRAWL_API_KEY", "").strip():
        providers.append("firecrawl")
    if multi.os.getenv("SERPAPI_API_KEY", "").strip():
        providers.append("serpapi")
    if multi.os.getenv("GOOGLE_CSE_API_KEY", "").strip() and multi.os.getenv("GOOGLE_CSE_ID", "").strip():
        providers.append("google_cse")
    providers.extend(["bing_html", "duckduckgo"])
    return providers


def install_search_resilience(app=None) -> None:
    multi.PROVIDERS["bing_html"] = _bing_html
    multi.configured_providers = resilient_providers

    # These modules import configured_providers by name, so update their module
    # references too if they have already been imported by the WSGI graph.
    try:
        import public_search_connector
        public_search_connector.configured_providers = resilient_providers
    except Exception:
        pass
    try:
        import ember_hunt
        ember_hunt.configured_providers = resilient_providers
    except Exception:
        pass

    # Keep each state hunt deliberately small so jobs finish reliably and the
    # national queue advances continuously instead of stalling on 50-company
    # single-state batches.
    try:
        from ember_runtime_patch import install_ember_runtime_patch
        install_ember_runtime_patch(app)
    except Exception:
        if app is not None:
            app.logger.exception("EMBER_RUNTIME patch failed safely")

    if app is not None:
        app.logger.warning("EMBER_SEARCH resilience enabled providers=%s", ",".join(resilient_providers()))


__all__ = ["install_search_resilience", "resilient_providers"]
