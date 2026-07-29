# BrokerBeacon Automated Campaign Setup

## 1. Email delivery
Add these Render environment variables:

- `SMTP_HOST` — your SMTP server
- `SMTP_PORT` — usually `587`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL` — approved sender address
- `APP_BASE_URL` — your public BrokerBeacon URL, for open/click tracking

For Gmail, use an app password rather than your normal password.

## 2. Text delivery
Add:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

In Twilio, set the incoming-message webhook to:

`https://YOUR-BROKERBEACON-DOMAIN/webhooks/twilio/sms`

BrokerBeacon sends automated texts only when the contact has recorded SMS consent and has not opted out.

## 3. Automatic processing
Add a long random Render environment variable:

- `CAMPAIGN_AUTOMATION_SECRET`

Create a Render Cron Job that runs every 5–15 minutes and executes:

```bash
curl -fsS "https://YOUR-BROKERBEACON-DOMAIN/api/automation/run?secret=$CAMPAIGN_AUTOMATION_SECRET"
```

A separate paid Render Cron Job may be required. Manual **Process due queue** remains available in BrokerBeacon.

## 4. Optional controls

- `SMS_QUIET_START=20`
- `SMS_QUIET_END=9`
- `CAMPAIGN_MAX_ATTEMPTS=3`

Quiet hours use the server's configured local time. Confirm your Render timezone before activating SMS automation.

## 5. Launching a drip sequence
Open **Templates & Sequences**, choose a sequence, edit its steps if needed, then select **Launch sequence**. BrokerBeacon creates dated campaign steps and automatically stops remaining messages after a reply, opt-out, meeting, approval, or funding status.
