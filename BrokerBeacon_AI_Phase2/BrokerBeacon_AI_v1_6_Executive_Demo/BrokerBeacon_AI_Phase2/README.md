# BrokerBeacon AI v1.2 — Verified Data Workflow

BrokerBeacon is a local Flask prospect-intelligence and relationship-management prototype.

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`.

## Real-data import policy

BrokerBeacon v1.2 does not create fictional prospect records and does not scrape NMLS Consumer Access. Import only records you are authorized to store and use, such as official downloadable regulator lists, licensed data-vendor exports, company-approved CRM exports, or manually verified records.

Every CSV row must include `authorized_use=yes` (or `true`/`1`). Rows without authorization are skipped. Supported states are NC, SC, VA, GA, TN, and MI.

Records are deduplicated first by NMLS ID, then by company + city + state. Existing matches are updated rather than duplicated.

Use `source_name`, `source_url`, `verification_status`, `verified_at`, `license_type`, and `verification_notes` to document provenance. NMLS Consumer Access may be opened manually for individual verification; automated bulk scraping is not included.

The included `sample_import.csv` is a column template only. Delete its example row before importing real data.
