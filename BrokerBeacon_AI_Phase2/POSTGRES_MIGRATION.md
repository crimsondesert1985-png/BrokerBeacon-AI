# BrokerBeacon PostgreSQL Migration Runbook

Sprint 33 introduces a non-destructive shadow migration. Production continues reading and writing
SQLite until every central and workspace table has matching row counts and SHA-256 checksums in
PostgreSQL. Each workspace is copied into its own schema to preserve tenant isolation.

## Safety model

- Source SQLite files are opened read-only.
- Every migration creates new, run-specific `bb_shadow_*` schemas.
- No source file, existing PostgreSQL schema, or production environment variable is replaced.
- A failed table checksum rolls back the entire PostgreSQL transaction.
- `POSTGRES_CUTOVER_ENABLED` defaults to false and this release contains no automatic cutover.

## Plan locally

```bash
python postgres_migration.py plan --source /var/data/brokerbeacon.db
```

Review the database, table, and row totals before provisioning infrastructure.

## Run the shadow copy

Set `DATABASE_URL` to the Render PostgreSQL internal URL, then run:

```bash
python postgres_migration.py migrate \
  --source /var/data/brokerbeacon.db \
  --output /var/data/postgres-shadow-validation.json
```

The command succeeds only when every target table matches its source row count and checksum.
Keep the validation report with the deployment record.

## Rollback

Because Sprint 33 does not switch application traffic, rollback is simply leaving
`POSTGRES_CUTOVER_ENABLED=false` and removing `DATABASE_URL` from the web service if necessary.
SQLite remains authoritative throughout the shadow phase.

## Cutover gate

Do not enable PostgreSQL application traffic until all of the following are true:

1. Shadow validation succeeds against a production backup and the live durable database.
2. Tenant schemas match the expected workspace roster.
3. Backup and restore procedures are tested for PostgreSQL.
4. A maintenance window and rollback owner are named.
5. Clay explicitly approves the final cutover.
