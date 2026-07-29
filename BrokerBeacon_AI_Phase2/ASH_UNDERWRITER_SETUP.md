# Ash Underwriter setup

Ash Underwriter searches BrokerBeacon’s locally indexed official-agency material first. The optional OpenAI reasoner converts those retrieved passages into a concise, plain-English answer.

## Render environment variable

Add:

```
OPENAI_API_KEY=your_key
```

Optional:

```
OPENAI_TEXT_MODEL=gpt-4.1-mini
```

Without an OpenAI key, BrokerBeacon uses its conservative local answer logic.

## Verify the deployed build

Open:

```
https://brokerbeacon-ai.onrender.com/api/version
```

The response should show:

```
"version": "10.1"
"build": "CONVERSATIONAL ASH UNDERWRITER"
```

The Render logs should include:

```
BrokerBeacon startup: VERSION 10.1 · CONVERSATIONAL ASH UNDERWRITER
```

If the sidebar still shows an older version, replace the complete application folder and choose **Manual Deploy → Clear build cache & deploy**.
