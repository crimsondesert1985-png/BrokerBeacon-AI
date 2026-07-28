# BrokerBeacon Compliant Importer

## Supported sources
Use CSV exports you are authorized to store and use, including employer CRM exports, approved vendor files, and regulator-provided downloadable files whose terms permit your intended use.

Do not use the importer to bypass access controls or bulk-copy sites that prohibit automated extraction or commercial reuse.

## Supported states
NC, SC, VA, GA, TN, and MI.

## How to import
1. Start BrokerBeacon and click **Compliant Import**.
2. Choose a CSV file.
3. Enter a source name and source URL when the CSV does not contain them.
4. Confirm authorization.
5. Click **Preview & validate**.
6. Review the detected mapping and invalid rows.
7. Click **Import approved rows**.
8. Download the import report for your records.

## Automatic column recognition
The importer recognizes common variations including Company Name, Legal Name, Business Name, Business City, Business State, NMLS ID, License Number, Email Address, Business Phone, Website, License Type, Verification Date, and Source URL.

## Deduplication
Records are matched by NMLS ID first. If no NMLS ID is present, BrokerBeacon matches Company + City + State. Existing records are updated rather than duplicated.
