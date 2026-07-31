# BrokerBeacon PostgreSQL Cutover Rehearsal

Sprint 34 verifies that the validated Sprint 33 shadow copy can be restored and still matches
the live SQLite source. It does not switch production traffic or enable PostgreSQL writes.

## Rehearsal command

Run from the Render web shell after a successful shadow migration:

```bash
python postgres_migration.py rehearse \
  --source /var/data/brokerbeacon.db \
  --validation /var/data/postgres-shadow-validation.json \
  --output /var/data/postgres-cutover-rehearsal.json
```

The command creates isolated `bb_restore_*` schemas inside one transaction, copies every
validated portable table, compares row counts and SHA-256 checksums, compares the restored copy
to the current live SQLite files, and then rolls the transaction back. Pass `--keep-restore` only
during an explicitly approved maintenance exercise.

## Backup layers

- Render PostgreSQL managed backups protect the database service.
- Sprint 33 shadow schemas are the validated logical source for this rehearsal.
- The JSON reports are deployment evidence, not substitutes for managed backups.
- SQLite backups remain required until PostgreSQL cutover is complete.

## Cutover gate

A report with `restore_valid`, `parity_valid`, and `cutover_ready` set to `true` means the technical
rehearsal passed. It never activates cutover. `POSTGRES_CUTOVER_ENABLED` remains false until a
separate release, maintenance window, rollback rehearsal, and Clay's explicit approval.
