# Version 27.0 — Controlled PostgreSQL Cutover Gate

- Adds verified rollback bundles for the central and tenant-isolated SQLite databases.
- Requires a successful Sprint 34 PostgreSQL restore and parity rehearsal.
- Validates backup integrity, table counts, row counts, and deterministic checksums.
- Persists atomic preparation and rollback manifests on the durable disk.
- Exposes fail-closed cutover readiness to platform owners.
- Keeps production traffic on SQLite and requires Clay's separate explicit approval for cutover.
