# BrokerBeacon AI 2.1

## Implemented

- Added a dedicated Follow-up Center with overdue, due-today, next-seven-days, and unscheduled counts.
- Added complete-follow-up workflow while preserving the relationship note history.
- Added prospect filtering by pipeline status and minimum opportunity score.
- Strengthened read-only demo enforcement for outreach queueing, imports, integrations, status changes, notes, and follow-up completion.
- Added automatic database initialization when loaded by Gunicorn.
- Updated health response and interface version to 2.1.
- Preserved the compliant CSV import workflow and existing 25-prospect database.

## Deployment

Keep Render Root Directory set to `BrokerBeacon_AI_Phase2` and push these files to the same GitHub repository. Render should redeploy automatically.
