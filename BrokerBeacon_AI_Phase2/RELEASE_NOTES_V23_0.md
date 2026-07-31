# BrokerBeacon AI 23.0 — Customer Onboarding

Sprint 31 turns the secured production application into a controlled first-customer pilot platform.

## Included

- Guided onboarding for every new non-founding workspace.
- Founding workspace migration protection; Clay's owner workspace bypasses customer onboarding and billing gates.
- Fourteen-day trials with expiration enforcement and a clear pricing route.
- Workspace billing status with seats, monthly AI-action allowance, and configuration readiness.
- Stripe Checkout, customer portal, and signed webhook support using environment-held secrets.
- Customer invitation delivery through the production SMTP channel.
- Platform-owner customer roster and guarded plan/status administration.
- Starter limits of 10 seats and 2,500 monthly AI-assisted actions.

## Controlled launch

Stripe routes remain unavailable until the platform owner deliberately configures `STRIPE_SECRET_KEY`,
`STRIPE_PRICE_ID`, and `STRIPE_WEBHOOK_SECRET`. No customer is charged and no plan is activated merely
by deploying this release. Signed Stripe events or Clay's protected platform controls are required.
