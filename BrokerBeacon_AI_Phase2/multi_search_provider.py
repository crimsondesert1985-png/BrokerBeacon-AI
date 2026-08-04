"""Multi-provider public search orchestration with a no-key fallback provider."""
from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SCHEMA = """
create table if not exists search_provider_runs(
    id integer primary key,
    public_search_run_id integer,
    provider text not null,
    query_text text not null,
    result_count integer not null default 0,
    unique_count integer not null default 0,
    duplicate_count integer not null default 0,
    status text not null default 'Queued',
    latency_ms integer not null default 0,
    error text default '',
    created_at text not null,
    finished_at text default ''
);
create table if not exists search_result_providers(
    id integer primary key,
    public_search_result_id integer not null,
    provider text not null,
    provider_rank integer not null default 0,
    provider_url text not null,
    created_at text not null,
    unique(public_search_result_id,provider)
);
create index if not exists idx_provider_runs_provider on search_provider_runs(provider,status,id desc);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
    query = [(k, v) for k, v in query if k.lower() not in tracking]
    return urllib.parse.urlunparse(("https", host, path, "", urllib.parse.urlencode(query), ""))


def configured_providers() -> list[str]:
    providers = []
    if os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        providers.append("brave")
    if os.getenv("TAVILY_API_KEY", "").strip():
        providers.append("tavily")
    if os.getenv("FIRECRAWL_API_KEY", "").strip():
        providers.append("firecrawl")
    if os.getenv("SERPAPI_API_KEY", "").strip():
        providers.append("serpapi")
    if os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_ID", "").strip():
        providers.append("google_cse")
    # Always retain a no-key fallback so one expired API key cannot stop Ember discovery.
    providers.append("duckduckgo")
    return providers


def _json_request(url: str, *, method: str = "GET", headers: dict | None = None,
                  payload: dict | None = None, timeout: int = 25) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 BrokerBeacon/1.0")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _brave(query: str, limit: int) -> list[dict]:
    key = os.environ["BRAVE_SEARCH_API_KEY"]
    results = []
    for offset in range(min(10, max(1, (limit + 19) // 20))):
        params = urllib.parse.urlencode({"q": query, "count": min(20, limit - len(results)), "offset": offset,
                                         "country": "US", "search_lang": "en", "safesearch": "moderate"})
        payload = _json_request("https://api.search.brave.com/res/v1/web/search?" + params,
                                headers={"X-Subscription-Token": key})
        page = (payload.get("web") or {}).get("results") or []
        results.extend({"title": x.get("title", ""), "description": x.get("description", ""), "url": x.get("url", "")} for x in page)
        if not (payload.get("query") or {}).get("more_results_available") or len(results) >= limit:
            break
    return results[:limit]


def _tavily(query: str, limit: int) -> list[dict]:
    payload = _json_request("https://api.tavily.com/search", method="POST",
                            headers={"Authorization": "Bearer " + os.environ["TAVILY_API_KEY"]},
                            payload={"query": query, "max_results": min(limit, 20), "search_depth": "advanced",
                                     "include_answer": False, "include_raw_content": False})
    return [{"title": x.get("title", ""), "description": x.get("content", ""), "url": x.get("url", "")}
            for x in payload.get("results") or []]


def _firecrawl(query: str, limit: int) -> list[dict]:
    payload = _json_request("https://api.firecrawl.dev/v2/search", method="POST",
                            headers={"Authorization": "Bearer " + os.environ["FIRECRAWL_API_KEY"]},
                            payload={"query": query, "limit": min(limit, 100), "sources": ["web"],
                                     "country": "US", "ignoreInvalidURLs": True})
    web = (payload.get("data") or {}).get("web") or []
    return [{"title": x.get("title", ""), "description": x.get("description", ""), "url": x.get("url", "")} for x in web]


def _serpapi(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"engine": "google", "q": query, "api_key": os.environ["SERPAPI_API_KEY"],
                                     "num": min(limit, 100), "hl": "en", "gl": "us"})
    payload = _json_request("https://serpapi.com/search.json?" + params)
    return [{"title": x.get("title", ""), "description": x.get("snippet", ""), "url": x.get("link", "")}
            for x in payload.get("organic_results") or []]


def _google_cse(query: str, limit: int) -> list[dict]:
    results = []
    for start in range(1, min(limit, 100) + 1, 10):
        params = urllib.parse.urlencode({"key": os.environ["GOOGLE_CSE_API_KEY"], "cx": os.environ["GOOGLE_CSE_ID"],
                                         "q": query, "start": start, "num": min(10, limit - len(results))})
        payload = _json_request("https://customsearch.googleapis.com/customsearch/v1?" + params)
        results.extend({"title": x.get("title", ""), "description": x.get("snippet", ""), "url": x.get("link", "")}
                       for x in payload.get("items") or [])
        if not (payload.get("queries") or {}).get("nextPage") or len(results) >= limit:
            break
    return results[:limit]


def _duckduckgo(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    attempts = (
        ("https://html.duckduckgo.com/html/?" + params, None),
        ("https://html.duckduckgo.com/html/", params.encode("utf-8")),
        ("https://lite.duckduckgo.com/lite/?" + params, None),
    )
    bodies, errors = [], []
    for url, data in attempts:
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
        req.add_header("Accept", "text/html,application/xhtml+xml")
        if data:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                body = response.read().decode("utf-8", "ignore")
            if body:
                bodies.append(body)
            if "result__a" in body or "result-link" in body:
                break
        except Exception as exc:
            errors.append(str(exc))
    if not bodies:
        raise RuntimeError("DuckDuckGo fallback failed: " + "; ".join(errors[-2:]))
    body = bodies[-1]
    anchors = re.findall(r'<a[^>]+class="[^"]*(?:result__a|result-link)[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.I | re.S)
    snippets = re.findall(r'<(?:a|div|td)[^>]+class="[^"]*(?:result__snippet|result-snippet)[^"]*"[^>]*>(.*?)</(?:a|div|td)>', body, re.I | re.S)
    results = []
    for index, (href, title_html) in enumerate(anchors):
        href = html.unescape(href)
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            href = urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        title = html.unescape(re.sub(r"<[^>]+>", " ", title_html))
        snippet_html = snippets[index] if index < len(snippets) else ""
        snippet = html.unescape(re.sub(r"<[^>]+>", " ", snippet_html))
        if href.startswith(("http://", "https://")):
            results.append({"title": re.sub(r"\s+", " ", title).strip(),
                            "description": re.sub(r"\s+", " ", snippet).strip(), "url": href})
        if len(results) >= limit:
            break
    return results


PROVIDERS = {
    "brave": _brave,
    "tavily": _tavily,
    "firecrawl": _firecrawl,
    "serpapi": _serpapi,
    "google_cse": _google_cse,
    "duckduckgo": _duckduckgo,
}


def search_all(query: str, *, limit_per_provider: int = 20, providers: list[str] | None = None) -> dict:
    providers = providers or configured_providers()
    merged: dict[str, dict] = {}
    stats = {}
    for provider in providers:
        fn = PROVIDERS.get(provider)
        if fn is None:
            continue
        started = datetime.now()
        try:
            raw = fn(query, limit_per_provider)
            duplicates = unique = 0
            for rank, item in enumerate(raw, start=1):
                url = canonical_url(item.get("url", ""))
                if not url:
                    continue
                if url in merged:
                    duplicates += 1
                    merged[url]["providers"].append({"provider": provider, "rank": rank})
                else:
                    unique += 1
                    merged[url] = {"url": url, "title": str(item.get("title") or ""),
                                   "description": str(item.get("description") or ""),
                                   "providers": [{"provider": provider, "rank": rank}]}
            stats[provider] = {"status": "Completed", "results": len(raw), "unique": unique,
                               "duplicates": duplicates,
                               "latency_ms": int((datetime.now() - started).total_seconds() * 1000)}
        except Exception as exc:
            stats[provider] = {"status": "Failed", "results": 0, "unique": 0, "duplicates": 0,
                               "latency_ms": int((datetime.now() - started).total_seconds() * 1000),
                               "error": str(exc)[:500]}
    ordered = sorted(merged.values(), key=lambda x: (-len(x["providers"]), min(p["rank"] for p in x["providers"])))
    return {"query": query, "providers": providers, "results": ordered, "provider_stats": stats,
            "total_unique": len(ordered)}


def provider_leaderboard(conn: sqlite3.Connection) -> list[dict]:
    initialize(conn)
    rows = conn.execute(
        """select provider,count(*) runs,sum(result_count) results,sum(unique_count) unique_results,
           sum(duplicate_count) duplicates,avg(latency_ms) avg_latency_ms,
           sum(case when status='Failed' then 1 else 0 end) failures
           from search_provider_runs group by provider order by unique_results desc,failures,avg_latency_ms"""
    ).fetchall()
    return [dict(row) for row in rows]

