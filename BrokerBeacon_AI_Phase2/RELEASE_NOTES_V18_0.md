# BrokerBeacon AI v18.0 — Index Population Engine

Sprint 26 turns the National Broker Index into a controlled, coverage-driven data asset.

## National population queue

- Maintains a ranked queue for all 50 states.
- Prioritizes states that have never been searched, have low broker coverage, or need a freshness refresh.
- Shows the reason and priority behind every queued state.
- Uses the central Scout schedule; customer searches still query BrokerBeacon's database without calling Google.

## Budget protection

- Projects the queries required by the current queue.
- Preserves a configurable monthly query reserve.
- Continues to enforce the 4,000-query platform ceiling, daily query budget, and estimated-cost ceiling.
- Stops scheduling states when the protected monthly allowance is exhausted.

## Control Tower placement

- Moves the Autopilot Control Tower to the top of the Prospects workspace.
- Displays the population queue, next state, projected usage, and protected reserve inside the Control Tower.

## Safety

- Autopilot and the population engine remain paused by default.
- Company facts require independent public evidence before becoming verified index data.
- No discovery enters Prospects or Outreach without human approval.
- No outreach is generated or sent automatically.
