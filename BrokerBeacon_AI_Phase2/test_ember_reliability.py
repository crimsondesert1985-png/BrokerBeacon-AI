import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import multi_search_provider
import public_search_connector
from ember_prospects_bridge import install_ember_prospects_bridge


class _Response:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class EmberReliabilityTests(unittest.TestCase):
    def test_main_prospects_is_strictly_filtered_by_state(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "prospects.db"
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    """
                    create table warehouse_companies(
                        id integer primary key, legal_name text, nmls_id text, website text,
                        phone text, public_email text, city text, state text,
                        verification_status text, created_at text, updated_at text
                    );
                    create table discovered_contacts(
                        id integer primary key, person_name text, phone text, public_email text,
                        source_url text, source_domain text, confidence integer,
                        review_status text, state text, company_name text
                    );
                    """
                )
                conn.executemany(
                    """insert into warehouse_companies
                       (legal_name,nmls_id,website,city,state,verification_status,updated_at)
                       values(?,?,?,?,?,?,?)""",
                    [
                        ("Texas Mortgage LLC", "123456", "https://texasmortgage.example", "Austin", " tx ", "Verified", "2026-08-03"),
                        ("California Home Loans LLC", "654321", "https://california.example", "Fresno", "CA", "Verified", "2026-08-03"),
                    ],
                )
                conn.commit()
            app = Flask(__name__)
            install_ember_prospects_bridge(app, db_path)
            response = app.test_client().get("/api/ember/main-prospects?state=TX")
            payload = response.get_json()
            self.assertEqual("TX", payload["selected_state"])
            self.assertEqual(["TX"], [item["state"] for item in payload["items"]])

    def test_bridge_owns_search_and_state_refresh_without_losing_hourly_refresh(self):
        source = Path(__file__).with_name("ember_prospects_bridge.py").read_text(encoding="utf-8")
        self.assertIn("q.oninput=null", source)
        self.assertIn("window.load=loadEmber", source)
        self.assertIn("setInterval(()=>loadEmber(true),HOURLY)", source)
        self.assertIn("state.addEventListener('change',()=>loadEmber(true))", source)

    def test_one_failed_query_does_not_abort_a_state_search(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        calls = []

        def search(query, count=20):
            calls.append(query)
            if query == "first":
                raise RuntimeError("temporary provider failure")
            return {
                "results": [{
                    "url": "https://acme-mortgage.example/",
                    "title": "Acme Mortgage Brokerage",
                    "description": "Independent mortgage broker NMLS 123456",
                    "providers": [{"provider": "duckduckgo", "rank": 1}],
                }],
                "provider_stats": {"duckduckgo": {"status": "Completed"}},
            }

        with patch.object(public_search_connector, "build_queries", return_value=["first", "second"]), patch.object(
            public_search_connector, "search_provider", side_effect=search
        ):
            result = public_search_connector.run_public_search(
                conn, connector_id=None, state="TX", results_per_query=10, delay_seconds=0
            )
        self.assertEqual(["first", "second"], calls)
        self.assertEqual(1, result["queries"])
        self.assertEqual(2, result["queries_attempted"])
        self.assertEqual(1, len(result["query_failures"]))
        self.assertEqual(1, result["accepted"])

    def test_duckduckgo_retries_with_lite_html(self):
        lite = '<a class="result-link" href="https://broker.example/">Broker Example</a>'
        with patch.object(
            multi_search_provider.urllib.request,
            "urlopen",
            side_effect=[OSError("GET blocked"), OSError("POST blocked"), _Response(lite)],
        ) as request:
            results = multi_search_provider._duckduckgo("mortgage broker Texas", 10)
        self.assertEqual(3, request.call_count)
        self.assertEqual("https://broker.example/", results[0]["url"])


if __name__ == "__main__":
    unittest.main()

