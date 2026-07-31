# BrokerBeacon AI 19.0 — SaaS Foundation

Sprint 27 turns the existing single-company application into a subscription-ready platform
foundation without deleting or rewriting Clay's founding BrokerBeacon data.

## Included

- Secure registration, login, logout, server-side identity checks, and password-reset tokens.
- Isolated company workspaces with Owner, Manager, AE, and Read Only memberships.
- Seven-day team invitations, workspace switching, seat limits, and role enforcement.
- A shared National Broker Index separated from private workspace broker records.
- Clay-only Scout, Population Engine, automation budget, and platform endpoints.
- Tenant-scoped audit records for account, session, workspace, and team actions.
- Plan, trial, billing-customer, billing-subscription, status, and seat fields ready for billing.
- Idempotent SQLite setup that preserves all founding prospect, outreach, and intelligence data.

## Deployment notes

- Set a stable `SECRET_KEY` environment variable in Render before production use.
- The first registered account becomes the platform owner and owns the founding workspace.
- Password-reset delivery is intentionally provider-neutral; configure email delivery before
  exposing self-service resets to customers.
- Existing founding intelligence remains unchanged and is copied into the shared National
  Broker Index on startup.
