# BrokerBeacon AI 20.0 — Tenant Isolation

Sprint 28 turns the SaaS foundation into an enforceable workspace boundary.

## Included

- Private operational database for every non-founding workspace.
- Automatic preservation of Clay's pre-SaaS prospect and activity data in the founding workspace.
- Isolation for prospects, contacts, outreach, campaigns, inbox, production, integrations, and future operational tables.
- Shared National Broker Index remains available through the central SaaS data store.
- Visible Account control with profile, workspace, role, and sign-out actions.
- Owner and Manager team roster with invitations and pending-invitation status.
- Complete invitation acceptance for new and existing BrokerBeacon users.
- Owner controls for changing roles and removing members.
- Workspace-switch membership enforcement and tenant-isolation regression tests.
- Safe post-login redirects and escaped invitation content.

## Validation

The Sprint 28 test suite proves that:

1. Founding records are preserved and hidden from customer workspaces.
2. Customer writes cannot be read by the founding workspace.
3. Non-members cannot switch into another workspace.
4. Invitation acceptance grants only the invited workspace and role.

## Deferred

- Transactional email delivery for invitation and password-reset links.
- Billing and subscription enforcement.
- Moving from per-workspace SQLite files to managed PostgreSQL when scale requires it.
