# BrokerBeacon AI 21.0 — Data Durability

Sprint 29 moves BrokerBeacon's central and tenant-isolated SQLite databases onto Render's
persistent disk and adds recovery safeguards for production operation.

## Included

- Automatic first-run seeding of `/var/data/brokerbeacon.db` from the packaged founding database.
- Existing durable databases always win on restart or redeploy; seed data never overwrites them.
- Every private workspace database remains beside the central database on the same durable disk.
- SQLite integrity validation before application startup.
- Transactionally consistent pre-deploy and on-demand backups with seven-snapshot retention.
- Platform-owner storage health and manual-backup endpoints.
- Thirty-second SQLite busy timeouts and foreign-key enforcement for safer concurrent access.
- Render health checks and explicit `/var/data` configuration.
- Automated coverage for first deployment, restart survival, backup integrity, and retention.

## Deployment behavior

The first 21.0 deployment seeds the attached disk from the repository database. Clay creates the
founding account once after that deployment. All later deployments reopen the durable copy and
preserve accounts, workspace memberships, prospects, campaigns, and private tenant databases.
