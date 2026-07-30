# BrokerBeacon AI v17.0 — National Broker Index

Sprint 25 changes BrokerBeacon from a per-user search tool into a shared broker-intelligence platform.

## Shared national catalog

- Creates one canonical Broker Index record per company.
- Migrates stored non-Google Prospects and independently researched Scout discoveries into the shared index.
- Deduplicates nationally by NMLS ID, company website domain, and normalized company/state identity.
- Gives every user fast database search without generating a new Google request.

## Source and freshness controls

- Records field-level source URLs, source types, capture dates, and refresh dates.
- Separates independently sourced company information from Google discovery content.
- Retains Google Place IDs where available while requiring independent sources for permanent broker facts.
- Displays source coverage, verification state, confidence, and freshness for every indexed company.

## Central discovery economics

- Disables customer-triggered Google searches and manual pilots.
- Keeps scheduled central Scout discovery available under Clay's control.
- Adds a 4,000-request monthly platform ceiling alongside existing daily query and estimated-cost ceilings.
- Synchronizes new researched discoveries into the shared catalog once for all users.

## Safety

- Autopilot is paused by default after migration.
- NMLS and regulator portals remain human verification sources, not scraping targets.
- No indexed company becomes an active Prospect without Clay's approval.
- No outreach is generated or sent automatically.
