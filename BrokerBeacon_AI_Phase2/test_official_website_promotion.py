import sqlite3

import ember_pipeline
from autonomous_prospecting import initialize as initialize_autonomous
from official_website_promotion import promote_official_website_contacts
from national_warehouse import create_import_job, create_source, ingest_companies, initialize


def test_official_website_contact_without_nmls_is_promoted():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize(conn)
    initialize_autonomous(conn)
    conn.executescript(
        """
        create table prospects(
            id integer primary key,company text,nmls text,website text,phone text,email text,
            city text,state text,status text,score integer,signal text,source_name text,
            source_url text,verification_status text,ai_summary text,next_best_action text,
            created_at text,updated_at text
        );
        create table contacts(
            id integer primary key,prospect_id integer,name text,role text,email text,phone text,
            nmls text,city text,state text,roster_status text,source_name text,source_url text,
            created_at text,updated_at text
        );
        """
    )
    source_id = create_source(
        conn, "Mortgage Matchup", "Public verified broker directory", "Public listing", "https://mortgagematchup.com"
    )
    job_id = create_import_job(conn, source_id, "NC")
    ingest_companies(conn, job_id, source_id, [{
        "legal_name": "Beacon Mortgage Group", "nmls_id": "123456",
        "website": "https://beaconmortgage.example/", "state": "NC",
        "source_record_id": "https://mortgagematchup.com/Company/beacon",
    }])
    company_id = conn.execute("select id from warehouse_companies").fetchone()[0]
    prospect_id = conn.execute("insert into prospects(company,nmls,state) values('Beacon Mortgage Group','123456','NC')").lastrowid
    conn.execute(
        """insert into autonomous_prospect_links(
           warehouse_company_id,prospect_id,promotion_reason,promoted_at,updated_at)
           values(?,?,?,datetime('now'),datetime('now'))""",
        (company_id, prospect_id, "Official website test"),
    )
    conn.execute(
        """insert into warehouse_officers(
           company_id,canonical_key,full_name,normalized_name,nmls_id,title,phone,public_email,
           city,state,verification_status,first_seen_at,last_seen_at,created_at,updated_at)
           values(?,?,'Jane Broker','jane broker','','Mortgage Loan Originator','7045553434',
                  'jane@beaconmortgage.example','Charlotte','NC','Public company website - verify identity and licensing',
                  datetime('now'),datetime('now'),datetime('now'),datetime('now'))""",
        (company_id, f"officer:{company_id}:jane-broker"),
    )
    conn.commit()

    result = promote_official_website_contacts(conn, state="NC")

    contact = conn.execute("select * from contacts").fetchone()
    assert result["created"] == 1
    assert contact["name"] == "Jane Broker"
    assert contact["role"] == "Mortgage Loan Originator"
    assert contact["email"] == "jane@beaconmortgage.example"
    assert contact["source_url"] == "https://beaconmortgage.example/"


def test_pipeline_crawls_resolved_company_website_after_ingest(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize(conn)
    captured = {}
    monkeypatch.setattr(ember_pipeline, "launch_hunt", lambda *args, **kwargs: {
        "search_run_id": 9, "state": "NC", "new_contacts": 0,
    })
    monkeypatch.setattr(ember_pipeline, "ingest_matchup_results", lambda *args, **kwargs: {
        "officers_created": 0,
        "companies": [{
            "legal_name": "Beacon Mortgage Group", "nmls_id": "123456",
            "website": "https://beaconmortgage.example/", "city": "Charlotte", "state": "NC",
        }],
    })

    def fake_crawl(_conn, seeds, *, state, max_pages):
        captured.update({"seeds": seeds, "state": state, "max_pages": max_pages})
        return {"officers_created": 1, "pages_fetched": 3}

    monkeypatch.setattr(ember_pipeline, "crawl_and_ingest", fake_crawl)

    result = ember_pipeline.launch(conn, state="NC", company_limit=10)

    assert captured["seeds"][0]["website"] == "https://beaconmortgage.example/"
    assert captured["state"] == "NC"
    assert captured["max_pages"] == 3
    assert result["new_contacts"] == 1

