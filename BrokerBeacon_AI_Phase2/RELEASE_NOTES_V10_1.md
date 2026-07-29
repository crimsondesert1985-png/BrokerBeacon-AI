# BrokerBeacon AI v10.1 — Conversational Ash Underwriter

## New underwriting answer experience

- Leads with a direct short answer instead of a retrieval summary.
- Uses clearer Yes / No / It depends / More facts needed labels.
- Separates key conditions, missing facts, and cautions.
- Adds “How I’d explain this to a broker” language that can be used in a sales conversation.
- Adds clickable follow-up choices that append missing scenario facts and immediately rerun the official-guide search.
- Keeps exact official-guide citations and full source cards below the answer.
- Gives scenario mode a preliminary scenario-opinion layout.

## Source grounding

Ash continues to reason only from the locally retrieved official-guide excerpts. It is instructed not to invent limits, exceptions, approvals, or underwriting rules. The conservative local fallback remains available when OpenAI is not configured or unavailable.

## Deployment identification

- Build: `10.1 · CONVERSATIONAL ASH UNDERWRITER`
- The sidebar version is populated from `/api/version` using a cache-busted, `no-store` request.
- `/api/version` includes a deployment identifier.
- Render startup logs print the running version and build name.

## Deployment

Replace the entire `BrokerBeacon_AI_Phase2` directory and use Render’s **Clear build cache & deploy** option.
