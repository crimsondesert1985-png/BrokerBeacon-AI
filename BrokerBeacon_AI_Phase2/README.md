# BrokerBeacon AI 2.0

A prospect intelligence and workflow demo for wholesale mortgage account executives.

## Included

- Executive command center and KPI summaries
- Public-web prospect profiles with source and verification fields
- AI opportunity scoring and product-fit recommendations
- Outreach drafting workflow
- Pipeline board
- Territory intelligence view
- Full-feature read-only executive demo at `/demo`
- Health check at `/health`
- Compliant CSV importer

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000/` for the editable local app and `http://127.0.0.1:5000/demo` for the read-only executive demo.

## Render settings

- Root Directory: `BrokerBeacon_AI_Phase2`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`

The existing public URL remains unchanged after deployment.

## Data note

Prospects sourced from public web information should remain marked **Needs verification** until confirmed before outreach. Do not import data from sources whose terms prohibit scraping, bulk extraction, or solicitation use.
