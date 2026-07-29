# BrokerBeacon AI 8.3.2 — Start My Day API Fix

## Root cause

The Start My Day request declared `Content-Type: application/json` but sent no request body. With Flask 3.x, accessing `request.json` can reject an empty JSON request with HTTP 400 before the workflow executes.

## Fixes

- The browser now sends an explicit `{}` JSON body.
- Flask uses `request.get_json(silent=True) or {}`.
- The button uses a direct event listener with no inline-handler/name collision.
- Failures are written to the browser console and displayed through the app toast.
- Version updated to 8.3.2.

## Expected behavior

Clicking Start My Day prioritizes up to five accounts, creates non-duplicate drafts and follow-ups, refreshes the relevant screens, and opens Daily Plan. On repeat clicks the counts may be zero because the workflow intentionally avoids duplicate same-day records; it should still open Daily Plan.
