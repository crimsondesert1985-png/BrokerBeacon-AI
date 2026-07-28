# BrokerBeacon AI 7.0.1 — AI Outreach Fix

## Fixed

The loan-officer **AI outreach** button previously referenced:

- a nonexistent browser field named `ochannel`
- a nonexistent JavaScript function named `build()`

That JavaScript error stopped the button before a draft could be generated.

## Updated behavior

- The button now calls the working `/api/generate` endpoint directly.
- The selected loan officer's `contact_id` is sent to the server.
- Email is selected when that officer has an email address; otherwise Phone is selected.
- The generated greeting uses the selected officer's name rather than only the company-level owner.
- The draft opens in Outreach with its subject and body populated.
- **Approve & queue** is enabled after generation.
- Browser and API failures now show a visible error message.

## Deployment

Replace the files in the existing `BrokerBeacon_AI_Phase2` directory and push to GitHub.

Expected version:

`VERSION 7.0.1 · OUTREACH FIX`
