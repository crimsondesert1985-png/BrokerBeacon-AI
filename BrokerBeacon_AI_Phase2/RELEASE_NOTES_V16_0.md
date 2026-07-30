# BrokerBeacon AI v16.0 — Autopilot Control Tower

Sprint 24 turns Scout Autopilot into a supervised, measurable AI workforce.

## Control Tower

- Shows live status for Scout, Researcher, Compliance, and Ash.
- Adds a controlled one-state pilot runner, defaulting to Maine.
- Displays recent runs, agent handoffs, errors, and result counts.
- Adds an emergency stop that pauses Autopilot and blocks manual pilot runs.

## Cost and quality controls

- Tracks Google queries and estimated spend for the current day.
- Enforces both the existing query budget and a configurable daily estimated-cost ceiling.
- Reports discovered, researched, duplicate, approved, rejected, and ready-for-review totals.
- Keeps clear failure and warning details in the run history.

## Safety

- Pilot runs use ordinary public Google Places results only.
- NMLS and regulator portals remain human verification sources, not scraping targets.
- Candidates still require Clay's explicit source review before entering Prospects.
- No outreach, messages, or automatic prospect approvals are performed.
