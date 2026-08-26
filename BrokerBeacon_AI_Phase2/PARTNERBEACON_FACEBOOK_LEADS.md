# PartnerBeacon — Facebook home-purchase leads

Drop-in module for BrokerBeacon AI. It does three jobs:

1. Capture **home purchase** leads from Facebook Lead Ads and the PartnerBeacon landing page
2. Track each customer through a purchase pipeline
3. Simplify outreach with 5-minute call tasks, first-touch scripts, Ash summaries, and drip queues

Public product name: **PartnerBeacon**. Code lives next to BrokerBeacon.

## Install

Copy `partnerbeacon_facebook_leads.py` into `BrokerBeacon_AI_Phase2/`.

In `wsgi.py`:

```python
from partnerbeacon_facebook_leads import install_facebook_purchase_leads
from saas import PUBLIC_PATHS

PUBLIC_PATHS.update({
    "/webhooks/facebook/leads",
    "/leads/facebook/apply",
    "/leads/facebook/apply/thanks",
})

install_facebook_purchase_leads(app, DB)
```

Put the install call near the other outreach modules (`install_drip_campaigns`).

Redeploy on Render (root directory stays `BrokerBeacon_AI_Phase2`).

## Environment variables

| Variable | Purpose |
|---|---|
| `FACEBOOK_VERIFY_TOKEN` | Random string you enter in Meta webhook setup |
| `FACEBOOK_APP_SECRET` | Signs inbound webhooks |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Lets PartnerBeacon download the actual lead fields |
| `PB_LO_NAME` | Name used in SMS/email/call drafts |
| `PB_COMPANY_NAME` | Brand in drafts (default PartnerBeacon Lending) |
| `PB_LO_PHONE` | Optional callback number in email |

Do not put tokens in GitHub.

## Facebook setup (Housing category)

1. Meta Business Suite → Page + Ad Account you control.
2. Create a **Lead Ad** campaign. Special ad category: **Housing**.
3. Target **geo only** (example: 25–40 miles around Charlotte). Do not use prohibited Housing targeting.
4. Instant Form questions (keep this list):
   - Full name, email, phone (default)
   - ZIP code
   - When do you want to buy? (`0-3 months` / `3-6 months` / `6-12 months` / `Just researching`)
   - Purchase price range
   - First-time buyer? Yes/No
   - Already pre-approved?
   - Consent checkbox: contact by phone/text/email about a home purchase
5. Webhook: `https://YOUR-DOMAIN/webhooks/facebook/leads`
   - Verify token = `FACEBOOK_VERIFY_TOKEN`
   - Subscribe the Page to `leadgen`
6. Traffic alternative: send ads to `https://YOUR-DOMAIN/leads/facebook/apply`

## Screens after deploy

| URL | Who |
|---|---|
| `/partnerbeacon/leads` | LO workspace: today list, pipeline, scripts, stage changes |
| `/leads/facebook/apply` | Public purchase landing page |
| `/webhooks/facebook/leads` | Meta only |

A **Purchase Leads** button is injected into the existing sidebar after login.

## Pipeline

`New Lead → Contacted → Qualified → Pre-Approved → House Hunting → Under Contract → Clear to Close → Funded`

Side paths: `Nurture`, `Dead`.

- New lead creates a **call-within-5-minutes** task and enrolls the 7-day purchase drip.
- Moving to **Pre-Approved** enrolls the 30-day nurture sequence.
- Moving to **Nurture** enrolls the 90-day warm sequence.
- **Funded** or **Dead** stops queued drips.

Drip rows sit in `fb_drip_queue` as reviewable copy. Wire them to the existing Twilio/SMTP campaign processor only after consent flags are true. Do not auto-text a number that only came from a scraped list.

## Ash

`GET /api/partnerbeacon/ash?lead_id=123` returns:

- one-paragraph summary
- next action
- SMS / email / call drafts
- realtor intro (send only after the buyer consents to the introduction)

## Compliance short list

- Facebook Housing ads: no age/gender/zip-exclusion targeting hacks
- Fair Housing disclaimer is on the landing page
- RESPA: co-marketing with a realtor is fine if each party pays fair market value for the ads they receive. Do not pay per closed referral.
- TCPA: checkbox consent before SMS; STOP language in every text
- Do not scrape Facebook. Official Lead Ads + webhook only

## Manual test without ads

```bash
curl -s -X POST http://127.0.0.1:5000/api/partnerbeacon/leads/manual \
  -H 'Content-Type: application/json' \
  -d '{"first_name":"Ava","last_name":"Cole","email":"ava@example.com","phone":"7045550100","market":"Charlotte, NC","timeframe":"0-3 months","sms_consent":true,"email_consent":true}'
```

Then open `/partnerbeacon/leads`.
