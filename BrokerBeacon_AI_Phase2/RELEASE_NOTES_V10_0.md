# BrokerBeacon AI v10.0 — Ash Underwriter Reasoner

- Replaces the research-summary-first panel with a direct answer-first response.
- Adds Yes / No / Conditional / Needs More Information classification.
- Shows key conditions, missing scenario facts, cautions, confidence, and exact source citations.
- Uses retrieved official-guide excerpts only when OpenAI synthesis is configured.
- Adds a conservative deterministic fallback for common guideline questions.
- Keeps full official source cards below the answer for verification.
- Loads the displayed version dynamically from `/api/version`.
