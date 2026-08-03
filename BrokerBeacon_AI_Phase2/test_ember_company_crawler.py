import sqlite3

import ember_company_crawler as crawler
from national_warehouse import dashboard, initialize


HTML_HOME = """
<html><head><title>Beacon Mortgage Group | Home Loans</title></head>
<body>
<a href='/contact'>Contact</a><a href='/about'>About Us</a>
<footer>NMLS #123456</footer>
</body></html>
"""

HTML_CONTACT = """
<html><body>
<h1>Contact Beacon Mortgage Group</h1>
<p>1200 Main Street, Charlotte, NC 28202</p>
<p>(704) 555-1212</p>
<a href='mailto:info@beaconmortgage.example'>Email</a>
</body></html>
"""


def test_crawl_company_extracts_public_business_fields(monkeypatch):
    pages = {
        "https://beaconmortgage.example/": HTML_HOME,
        "https://beaconmortgage.example/contact": HTML_CONTACT,
        "https://beaconmortgage.example/about": "<html><body>Independent mortgage broker.</body></html>",
    }

    monkeypatch.setattr(crawler, "_allowed", lambda url, cache: True)
    monkeypatch.setattr(crawler, "_fetch", lambda url, **kwargs: (url, pages[url]))

    result = crawler.crawl_company(
        {
            "company": "Beacon Mortgage Group",
            "source_url": "https://beaconmortgage.example/",
            "state": "NC",
        },
        max_pages=3,
    )

    assert result["status"] == "Completed"
    assert result["pages_fetched"] == 3
    record = result["record"]
    assert record["legal_name"] == "Beacon Mortgage Group"
    assert record["nmls_id"] == "123456"
    assert record["phone"] == "(704) 555-1212"
    assert record["public_email"] == "info@beaconmortgage.example"
    assert record["city"] == "Charlotte"
    assert record["state"] == "NC"
    assert record["postal_code"] == "28202"


def test_crawl_and_ingest_deduplicates_by_nmls(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize(conn)

    records = iter([
        {
            "status": "Completed",
            "reason": "",
            "pages_fetched": 2,
            "record": {
                "legal_name": "Beacon Mortgage Group",
                "nmls_id": "123456",
                "website": "https://beaconmortgage.example/",
                "phone": "7045551212",
                "public_email": "info@beaconmortgage.example",
                "city": "Charlotte",
                "state": "NC",
                "postal_code": "28202",
                "source_record_id": "beaconmortgage.example",
            },
        },
        {
            "status": "Completed",
            "reason": "",
            "pages_fetched": 2,
            "record": {
                "legal_name": "Beacon Mortgage Group LLC",
                "nmls_id": "123456",
                "website": "https://beaconmortgage.example/",
                "phone": "7045551212",
                "public_email": "hello@beaconmortgage.example",
                "city": "Charlotte",
                "state": "NC",
                "postal_code": "28202",
                "source_record_id": "beaconmortgage.example",
            },
        },
    ])
    monkeypatch.setattr(crawler, "crawl_company", lambda seed, max_pages=5: next(records))

    outcome = crawler.crawl_and_ingest(
        conn,
        [
            {"company": "Beacon Mortgage Group", "source_url": "https://beaconmortgage.example/", "state": "NC"},
            {"company": "Beacon Mortgage Group LLC", "source_url": "https://beaconmortgage.example/", "state": "NC"},
        ],
        state="NC",
    )

    assert outcome["warehouse"]["created"] == 1
    assert outcome["warehouse"]["updated"] == 1
    assert dashboard(conn)["companies"] == 1
