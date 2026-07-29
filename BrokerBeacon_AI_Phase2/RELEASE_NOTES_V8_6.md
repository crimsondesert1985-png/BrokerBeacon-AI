# BrokerBeacon AI v8.6 · AI Voice Agent

## Added
- Consent-first outbound calling through Twilio Programmable Voice.
- Professional female text-to-speech voice (`Polly.Joanna` by default).
- Answering-machine detection and complete voicemail delivery.
- Disclosed automated live-call flow with speech and keypad input.
- Optional OpenAI-generated conversational responses grounded in BrokerBeacon account context.
- Verbal opt-out handling that immediately blocks future automated calls.
- Appointment selection and scheduling inside BrokerBeacon.
- Voice-call history, disposition, transcript, and appointment records.
- Voice Agent workspace with connection status and per-contact consent controls.

## Guardrails
- A call cannot be placed without an explicit voice-consent flag.
- Opted-out contacts cannot be called.
- The agent identifies itself as automated at the start of a live call.
- No cloned or impersonated voice is included.
- Production use requires Twilio credentials and organizational legal/compliance approval.
