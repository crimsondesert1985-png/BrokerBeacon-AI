# BrokerBeacon AI 8.1 — Sprint 2: Opportunity Intelligence

## Implemented

- Explainable 0–100 opportunity scoring
- Hot, Warm, Developing, and Research priority tiers
- Confidence rating for every score
- Point-by-point score explanations
- Next-best-action recommendations
- Product matching against an editable Union Home product catalog
- Scoring-weight controls in the application
- Full-database recalculation and historical score snapshots
- Idempotent SQLite migration runner (`migrations.py`)
- Business logic separated into `intelligence.py`
- Mission Control-compatible score updates

## Scoring inputs

The engine uses stored BrokerBeacon data only, including verification status, recent-license signals, contact-roster size, product specialties, relationship stage, follow-up urgency, and time since the last recorded activity. It does not claim production volume or licensing facts that are not in the database.

## Deploy

Replace the contents of the existing `BrokerBeacon_AI_Phase2` directory, commit, and let Render redeploy. The database migration runs automatically at application startup.
