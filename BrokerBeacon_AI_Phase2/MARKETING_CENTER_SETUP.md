# Marketing Center setup

1. Open **Marketing Center** from the left navigation.
2. Generate or enter approved marketing content.
3. Save it as a template or submit it for compliance review.
4. After review, use **Use in campaign** to load it into Campaigns.
5. Configure SMTP and/or Twilio environment variables described in the existing campaign setup guides for real delivery.
6. Configure the Render Cron Job for `/api/automation/run` so queued campaigns process automatically.

Marketing triggers are stored and manageable in this release. Trigger execution should be enabled only after your organization defines the approved event rules and compliance requirements.
