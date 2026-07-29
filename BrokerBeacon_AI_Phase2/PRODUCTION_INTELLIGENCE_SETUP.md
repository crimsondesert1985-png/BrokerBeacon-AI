# Production Intelligence setup

BrokerBeacon v11.2 adds a source-labeled production intelligence workspace.

## Supported CSV fields

Required:
- `company`
- `period_month` in `YYYY-MM` format
- at least one of `units` or `volume`

Recommended:
- `company_nmls`
- `lo_name`
- `lo_nmls`
- `loan_type`
- `purpose`
- `source_name`
- `data_as_of`

Use the **Download CSV template** button in Production Intelligence for a ready-to-fill example.

## Data-source rules

- Public HMDA-style data should be labeled as company-level unless the approved file itself contains named loan-originator fields.
- Named LO production requires a licensed or internal source that is authorized for use by your company.
- Re-importing the same `source_name` and `data_as_of` snapshot replaces the earlier snapshot to avoid double counting.
- Production totals are imported facts from the selected source. They are not represented as live data unless the source is actually live.

## Recommended workflow

1. Export a permitted company or LO production report.
2. Map the columns to the BrokerBeacon template.
3. Import the CSV.
4. Review the source and data-as-of label.
5. Compare company and LO rankings, product mix, units, and volume.
6. Ask Global Ash questions such as “Who are my largest VA producers?”
