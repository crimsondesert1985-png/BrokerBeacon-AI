# BrokerBeacon AI 22.0 — Production Security

Sprint 30 protects the founding owner and customer workspaces as BrokerBeacon moves into production.

## Included

- One-time, expiring email-verification and password-reset links delivered through SMTP.
- Password resets revoke every existing session by advancing the user's authentication version.
- Persistent login throttling blocks repeated attempts for 15 minutes without exposing account existence.
- Security-sensitive login, verification, reset, membership, and owner actions are audit logged.
- Secure response headers prevent framing, MIME sniffing, permissive referrers, and unnecessary browser permissions.
- Every automatic and manual backup is restored into an isolated temporary database and integrity checked.
- Platform-owner recovery-check endpoint and structured optional webhook alerts.
- Recovery runbook with required environment variables and a non-destructive restore procedure.
- Pull-request, main-branch, weekly dependency scanning and test automation with Dependabot.

## Owner protection

Existing production users are marked verified during the additive schema upgrade so the founding owner
is never locked out. New accounts must verify their email before a later login. Password-reset and
verification tokens are hashed in SQLite and are never written to application logs.
