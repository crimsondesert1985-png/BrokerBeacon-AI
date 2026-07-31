# BrokerBeacon Production Recovery

## Required production configuration

- `SECRET_KEY`: generated once and retained by Render.
- `BROKERBEACON_DATA_DIR=/var/data`: persistent-disk location.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and
  `SECURITY_EMAIL_FROM`: password-reset and verification delivery.
- `SECURITY_ALERT_WEBHOOK_URL`: optional operator alert destination.

Never place secrets in GitHub, screenshots, logs, support messages, or the database.

## Routine checks

1. Confirm `/health` returns `status: ok`, persistent storage, integrity `ok`, and a retained backup.
2. As platform owner, call `POST /api/platform/recovery-check`. This restores the newest backup
   into an isolated temporary database, runs SQLite integrity checks, and confirms application tables.
3. Review `/api/saas/audit` for failed or blocked logins, password resets, verification, membership,
   and owner actions.
4. Keep the GitHub Security workflow and Dependabot updates passing before release.

## Recovery procedure

1. Stop writes by placing the Render service in maintenance mode.
2. Download and preserve the current database and every tenant workspace database.
3. Choose the newest backup that passes the recovery check; never overwrite the only copy.
4. Restore into a new file, run `pragma quick_check`, and confirm `schema_migrations` and core tables.
5. Atomically replace the damaged database only after verification, then restart the service.
6. Confirm `/health`, owner login, tenant isolation, prospect counts, and audit history.
7. Record the incident and recovery in the owner audit log and rotate exposed credentials if applicable.

The automated recovery check is deliberately non-destructive. Production replacement remains an
explicit operator action so a remote request cannot overwrite the live database.
