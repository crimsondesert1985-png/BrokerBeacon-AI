# BrokerBeacon AI 8.7 — Automated Drip Campaigns

## Implemented
- Production email delivery through SMTP and SMS delivery through Twilio.
- Scheduled one-time campaigns and multi-step email/SMS/task sequences.
- Secure `/api/automation/run` endpoint for Render Cron Jobs.
- Daily campaign throttling based on messages actually sent that day.
- SMS quiet-hour enforcement and recorded-consent requirement.
- Automatic suppression for replies, STOP requests, opt-outs, and progressed relationships.
- Retry handling with exponential delay for temporary provider failures.
- Concurrency-safe recipient claiming to reduce duplicate sends.
- Recovery of jobs interrupted while marked Processing.
- Automatic campaign completion when no queued work remains.
- Automation/provider health indicators in Campaigns.
- Persistent automation run history.

## Required provider configuration
See `DRIP_CAMPAIGN_SETUP.md`.
