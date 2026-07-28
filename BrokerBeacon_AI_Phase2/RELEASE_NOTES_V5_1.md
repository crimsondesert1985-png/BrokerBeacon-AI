# BrokerBeacon AI 5.1 — Loan Officer Rosters

## Implemented

- Separate roster sections for:
  - Decision-makers
  - Individual loan officers
  - Company contact desk
- Individual loan-officer fields:
  - Name and role
  - Direct phone and mobile
  - Email
  - NMLS ID
  - Office location
  - Specialties
  - Languages
  - Preferred communication method
  - Public profile and source URL
  - Verification date and roster status
  - Notes
- Search within each company roster by name, NMLS, specialty, language, location, phone, or email.
- Individual Call, Email, Profile, Source Verification, Copy, Edit, and AI Outreach controls.
- Approval-based company-website review:
  - Checks only the company's own configured public website.
  - Looks for structured Person records and public business email/phone details.
  - Stages discoveries for review.
  - Requires explicit approval before saving them to the CRM.
  - Supports rejecting unsuitable or duplicate discoveries.
- Expanded database model for many loan officers per company.
- Existing contact data preserved and migrated.

## Included data at build time

- 25 companies
- 25 existing contact records
- 15 named contact records
- 25 contact records with a phone, mobile, or email
- Database integrity: ok

## Important limitation

No website can guarantee a complete employee roster. Some companies do not publish every loan officer, use JavaScript-only directories, or block automated requests. BrokerBeacon therefore labels public rosters as potentially incomplete and never invents names or contact details.

## Deployment

Replace the files inside the existing `BrokerBeacon_AI_Phase2` GitHub folder, commit, and push. Render should then show:

`VERSION 5.1 · LO ROSTERS`
