# BrokerBeacon AI Version 26.0

## Sprint 34 · PostgreSQL Cutover Rehearsal

- Restores the validated PostgreSQL shadow copy into isolated transactional schemas.
- Verifies every portable table by row count and deterministic SHA-256 checksum.
- Compares the restored PostgreSQL data with the current authoritative SQLite databases.
- Persists a safe readiness report for health and platform-owner visibility.
- Leaves PostgreSQL cutover disabled and requires explicit owner approval for any future switch.
