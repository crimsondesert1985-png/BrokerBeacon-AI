# BrokerBeacon AI v15.0 — Scout Autopilot

Sprint 23 turns Scout into a controlled, repeatable broker-discovery pipeline.

## Agent handoff

1. Scout rotates through the least-recently-searched enabled territories.
2. Researcher reviews public company websites for business contacts, NMLS clues, and growth signals.
3. Compliance flags duplicates, missing licensing evidence, unconfirmed decision-makers, and missing public contacts.
4. Ash ranks researched candidates for Clay's review.
5. Clay must inspect the source and explicitly approve a candidate before it enters Prospects.

No candidate is added to Outreach and no message is sent by Autopilot.

## Controls

- Enable or pause Autopilot.
- Select any combination of all 50 states.
- Set a 6-hour to 7-day cadence.
- Limit states searched per run.
- Set a daily Google query budget.
- Limit how many discoveries Researcher enriches per run.
- Run the pipeline manually at any time.

## Runtime

The in-process worker checks for due work every 15 minutes while the Render service is awake. The database is authoritative for next-run timing, coverage, and daily query usage. Set `ENABLE_SCOUT_AUTOPILOT_WORKER=0` to disable the worker.

## Validation

- Python compilation
- Embedded JavaScript syntax validation
- Flask render and API smoke tests
- 50-state settings validation
- query-budget and territory-rotation tests
- Researcher and Ash queue tests
- confirmation gate test
- verified zero automatic Prospect and Outreach creation
