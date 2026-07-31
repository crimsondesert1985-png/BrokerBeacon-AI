import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from sprint36_discovery import install


class Sprint36DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "brokerbeacon.db"
        with sqlite3.connect(self.db_path) as con:
            con.executescript(
                """
                create table prospects(
                    id integer primary key,
                    company text not null,
                    owner text default '',
                    city text default '',
                    metro text default '',
                    state text not null,
                    nmls text default '',
                    website text default '',
                    source text default '',
                    source_name text default '',
                    source_url text default '',
                    signal text default '',
                    verification_status text default '',
                    status text default 'New',
                    created_at text default '',
                    updated_at text default ''
                );
                create table contacts(
                    id integer primary key,
                    prospect_id integer not null,
                    name text default '',
                    title text default '',
                    email text default '',
                    phone text default '',
                    is_primary integer default 0,
                    roster_status text default '',
                    source_url text default '',
                    created_at text default '',
                    updated_at text default ''
                );
                create table scout_runs(
                    id integer primary key,
                    state text not null,
                    metro text default '',
                    status text not null default 'Running',
                    query_count integer not null default 0,
                    result_count integer not null default 0,
                    new_count integer not null default 0,
                    duplicate_count integer not null default 0,
                    error text default '',
                    started_at text not null,
                    finished_at text default ''
                );
                create table scout_candidates(
                    id integer primary key,
                    run_id integer not null,
                    company text not null default '',
                    result_title text not null default '',
                    state text not null,
                    metro text default '',
                    nmls text default '',
                    owner text default '',
                    email text default '',
                    phone text default '',
                    website text default '',
                    linkedin_url text default '',
                    signal text not null default 'Public web discovery',
                    evidence text not null default '',
                    source_name text not null default 'Public web search',
                    source_url text not null,
                    status text not null default 'Pending review',
                    confidence integer not null default 0,
                    duplicate_prospect_id integer default 0,
                    approved_prospect_id integer default 0,
                    discovered_at text not null,
                    reviewed_at text default '',
                    review_notes text default ''
                );
                create table scout_research(
                    candidate_id integer primary key,
                    stage text not null default 'Research queued',
                    ash_score integer not null default 0,
                    ash_reason text default '',
                    updated_at text not null
                );
                insert into scout_runs(id,state,metro,status,result_count,started_at)
                values(1,'NC','Charlotte','Completed',1,'2026-07-31T10:00:00');
                insert into scout_candidates(
                    id,run_id,company,result_title,state,metro,nmls,owner,email,phone,
                    website,source_name,source_url,status,confidence,discovered_at
                ) values(
                    1,1,'Carolina Home Lending','Carolina Home Lending','NC','Charlotte',
                    '123456','Jordan Broker','jordan@example.com','704-555-0100',
                    'https://example.com','Company website','https://example.com/contact',
                    'Pending review',88,'2026-07-31T10:00:00'
                );
                insert into scout_research(candidate_id,stage,ash_score,ash_reason,updated_at)
                values(1,'Researched',91,'Strong public contact evidence','2026-07-31T10:05:00');
                """
            )

        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="sprint-36-test")

        @self.app.get("/")
        def home():
            return '<html><body><div class="app"><aside><nav><button data-v="dashboard">Home</button></nav></aside><main><section id="dashboard" class="view active">Dashboard</section></main><script>function api(){} function esc(x){return x} function msg(){}</script></div></body></html>'

        def connect():
            con = sqlite3.connect(self.db_path)
            con.row_factory = sqlite3.Row
            return con

        install(self.app, connect)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_discovery_ui_is_injected_into_existing_application_shell(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Prospect Discovery', response.data)
        self.assertIn(b'id="discovery"', response.data)
        self.assertIn(b'data-v="discovery"', response.data)

    def test_state_search_returns_ranked_candidate_and_verification_warning(self):
        response = self.client.get("/api/discovery-center?state=NC")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["company"], "Carolina Home Lending")
        self.assertEqual(data["results"][0]["ash_score"], 91)
        self.assertEqual(data["results"][0]["verification_status"], "Needs NMLS verification")
        empty = self.client.get("/api/discovery-center?state=SC").get_json()
        self.assertEqual(empty["results"], [])

    def test_saved_search_and_csv_export(self):
        saved = self.client.post("/api/discovery-center/saved-searches", json={
            "name": "North Carolina brokers", "state": "NC", "active_only": True,
        })
        self.assertEqual(saved.status_code, 201)
        listing = self.client.get("/api/discovery-center?state=NC").get_json()
        self.assertEqual(listing["saved_searches"][0]["name"], "North Carolina brokers")
        exported = self.client.get("/api/discovery-center/export.csv?state=NC")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.content_type)
        self.assertIn(b"Carolina Home Lending", exported.data)
        self.assertIn(b"jordan@example.com", exported.data)

    def test_selected_candidate_imports_prospect_and_contact_once(self):
        response = self.client.post("/api/discovery-center/import", json={"candidate_ids": [1]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"imported": 1, "skipped": 0})
        with sqlite3.connect(self.db_path) as con:
            prospect = con.execute("select company,state,nmls,verification_status from prospects").fetchone()
            contact = con.execute("select name,email,phone from contacts").fetchone()
            candidate = con.execute("select status,approved_prospect_id from scout_candidates where id=1").fetchone()
        self.assertEqual(prospect, ("Carolina Home Lending", "NC", "123456", "Needs NMLS verification"))
        self.assertEqual(contact, ("Jordan Broker", "jordan@example.com", "704-555-0100"))
        self.assertEqual(candidate[0], "Approved")
        self.assertGreater(candidate[1], 0)
        duplicate = self.client.post("/api/discovery-center/import", json={"candidate_ids": [1]})
        self.assertEqual(duplicate.get_json(), {"imported": 0, "skipped": 1})


if __name__ == "__main__":
    unittest.main()
