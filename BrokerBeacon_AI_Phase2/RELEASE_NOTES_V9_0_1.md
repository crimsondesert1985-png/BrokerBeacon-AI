# BrokerBeacon AI 9.0.1 — Plain-English Ash Underwriter Answers

## New
- Ash now gives a direct, plain-English conclusion before displaying source cards.
- The answer includes a concise explanation, evidence basis, and confidence label.
- When `OPENAI_API_KEY` is configured, the conclusion is synthesized only from retrieved official-guide excerpts.
- Without an OpenAI key, BrokerBeacon uses a conservative evidence-based fallback and clearly identifies limited evidence.
- Supporting official sources remain grouped below the answer.

## Guardrails
- The model is instructed not to invent requirements, numbers, exceptions, or approvals.
- Unclear evidence produces a qualified or insufficient-evidence answer rather than a fabricated decision.
- All answers retain the effective-date, AUS, overlay, and underwriting disclaimer.
