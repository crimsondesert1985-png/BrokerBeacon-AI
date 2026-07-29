# Ash Underwriter Index

The guideline search is local and requires no search-engine API key.

## Indexed at deployment
- FHA Handbook 4000.1: bundled PDF indexed page-by-page.
- Fannie Mae, Freddie Mac, VA and USDA: starter official-section index with direct source citations.

## Rebuild
BrokerBeacon builds missing index records during startup. A protected rebuild is also available:

`POST /api/guidelines/reindex`

The endpoint follows BrokerBeacon's existing write protections. It can take several minutes because the FHA handbook is almost 1,900 pages.

## Search
`GET /api/guidelines/search?q=gift+funds&program=fannie`

Valid programs: `all`, `fannie`, `freddie`, `fha`, `va`, `usda`.
