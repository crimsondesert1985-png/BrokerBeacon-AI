# BrokerBeacon AI Voice Agent setup

The voice agent is disabled until Twilio credentials are configured in Render.

Required environment variables:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

Optional:
- `TWILIO_VOICE` (default `Polly.Joanna`, a female voice)
- `TWILIO_VOICE_LANGUAGE` (default `en-US`)
- `OPENAI_API_KEY` for AI-generated concise conversational replies
- `OPENAI_TEXT_MODEL` (default `gpt-4.1-mini`)

The public Render URL must be reachable by Twilio webhooks. Calls are blocked unless the contact has explicit voice consent recorded in BrokerBeacon. The agent identifies itself as automated at the start of each live call, honors verbal opt-outs, detects voicemail, and schedules appointments inside BrokerBeacon.

Before production use, have company counsel/compliance approve the scripts, consent process, calling hours, recording/transcription notice, DNC handling, and applicable federal/state rules.
