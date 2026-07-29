# BrokerBeacon AI v8.10.1 — Ash Underwriter Deployment Fix

- Corrects every visible and API build identifier to v8.10.1.
- Adds `/api/version` with guideline-index counts so the deployed build can be verified immediately.
- Updates `/health` to report the current build instead of the stale v8.3.2 value.
- Adds `X-BrokerBeacon-Version` and `X-BrokerBeacon-Build` response headers.
- Disables browser/proxy caching for the application shell and guideline endpoints.
- Removes stale `__pycache__` and `.pyc` files from the deployment package.
- Corrects the Loan Guidelines description to state that search uses the local official-guide index.
- Preserves the v8.10 local FTS index, FHA handbook, existing database, and all prior BrokerBeacon features.
