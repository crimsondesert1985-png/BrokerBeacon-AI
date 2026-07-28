# BrokerBeacon Campaign Setup

BrokerBeacon 6.0 ships in approval/queue mode. Campaigns can be created, previewed, scheduled, paused, and processed without storing credentials in source control.

## Email delivery
Set these environment variables in Render:

- `SMTP_HOST`
- `SMTP_PORT` (defaults to `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`

Use a dedicated business mailbox or approved transactional email provider. Do not commit passwords to GitHub.

## Text delivery
Set these environment variables in Render:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `SMS_QUIET_START` (defaults to `20`)
- `SMS_QUIET_END` (defaults to `9`)

Text campaigns only include contacts whose **Documented consent to receive text messages** box is checked. Opted-out destinations are excluded by the suppression list.

## Scheduled processing
The **Process due queue** button sends due messages manually. For unattended automation, configure a secure scheduled job to POST to `/api/campaigns/process`. Before exposing that route publicly, add authentication or a shared secret at the infrastructure layer.

## Operational safeguards

- Preview every audience before saving.
- Start with low daily limits.
- Keep email and SMS opt-out records current.
- Do not treat a publicly listed phone number as consent to receive automated texts.
- Review company policy and applicable outreach rules before enabling live delivery.
