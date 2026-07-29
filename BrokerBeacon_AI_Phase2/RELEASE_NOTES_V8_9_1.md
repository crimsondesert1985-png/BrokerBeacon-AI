# BrokerBeacon AI 8.9.1 — Guide Search Fix

- Replaced the single fragile DuckDuckGo HTML scraper with a two-stage search strategy.
- Added Bing RSS search as the primary no-key search backend.
- Added DuckDuckGo HTML and Lite layouts as fallbacks.
- Relaxed result parsing so layout changes no longer silently return an empty list.
- Added query-aware official fallback links.
- Added clearer source-specific connectivity diagnostics.
