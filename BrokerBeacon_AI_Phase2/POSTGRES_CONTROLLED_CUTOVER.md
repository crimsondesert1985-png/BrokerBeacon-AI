# Sprint 35 — Controlled PostgreSQL Cutover Gate

Sprint 35 prepares BrokerBeacon for a production PostgreSQL cutover while keeping SQLite
authoritative until Clay separately approves the maintenance-window switch.

## What this release does

- Requires a successful Sprint 34 restore and live-parity rehearsal.
- Creates a transactionally consistent rollback copy of the central SQLite database and every
  isolated workspace database.
- Runs SQLite integrity checks and compares every portable table by row count and SHA-256 checksum.
- Writes an atomic rollback manifest and a durable cutover-preparation report.
- Exposes a safe readiness summary through the platform-owner PostgreSQL readiness endpoint.
- Fails closed: an environment flag alone cannot report PostgreSQL traffic as active.

## Prepare the approval package

Run from the Render web shell after refreshing both the Sprint 33 shadow validation and Sprint 34
rehearsal against the current durable SQLite databases:

```bash
python postgres_migration.py prepare \
  --source /var/data/brokerbeacon.db \
  --rehearsal /var/data/postgres-cutover-rehearsal.json \
  --backup-root /var/data/backups \
  --preparation /var/data/postgres-cutover-preparation.json
```

The command stops immediately unless the rehearsal is valid. A successful run creates:

- `/var/data/backups/postgres-cutover-<timestamp>/` with verified SQLite rollback databases
- a backup `manifest.json`
- `/var/data/postgres-cutover-preparation.json`

## Approval gate

A preparation report may say `cutover_ready: true`; that means the technical prerequisites and
rollback package passed. It does not grant approval and does not switch application traffic.

Before any production switch:

1. Clay explicitly approves the exact maintenance window.
2. The latest row and checksum totals are recorded.
3. The rollback manifest is retained on the persistent disk.
4. Founding-owner and customer test accounts are available for smoke tests.
5. SQLite remains untouched until the PostgreSQL soak period completes.

## Rollback contract

If any production validation fails, disable the PostgreSQL switch, restore the pre-cutover
environment, and continue from the verified SQLite bundle. Do not delete the live SQLite files,
the backup bundle, shadow schemas, or rehearsal evidence during the cutover window.
