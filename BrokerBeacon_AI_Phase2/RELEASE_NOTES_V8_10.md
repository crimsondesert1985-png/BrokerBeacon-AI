# BrokerBeacon AI v8.10 — Ash Underwriter Index

## Implemented
- Replaced fragile public search-engine scraping with a local SQLite FTS5 guideline index.
- Bundled and indexed the official FHA Single Family Housing Policy Handbook 4000.1 page-by-page.
- Added indexed official-section records for common Fannie Mae, Freddie Mac, VA, and USDA topics with direct controlling-source links.
- Added exact section/page citations, highlighted matching text, program filtering, index counts, and source metadata.
- Added `/api/guidelines/index-status` and a protected `/api/guidelines/reindex` endpoint.
- Search now works without Bing or DuckDuckGo and returns deterministic local results.

## Important
This workspace supports initial scenario research. Users must still verify the current effective guide language, AUS findings, lender/investor overlays, and underwriting decisions.
