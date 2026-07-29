# BrokerBeacon AI 8.3.3 — Mission Control Fix

## Fixed
- Corrected `/api/mission-control` to count Reply Inbox items using the existing `status` column.
- Added compatibility handling for databases that may contain the older `needs_attention` field.
- Prevented the Mission Control refresh from failing after Start My Day completes.
- Improved browser API error messages when a server endpoint returns HTML instead of JSON.

## Expected Start My Day flow
1. Prioritize up to five accounts.
2. Create non-duplicate outreach drafts and follow-ups.
3. Refresh Mission Control, Daily Plan, Outreach, and Follow-ups.
4. Open Daily Plan and show the completion message.
