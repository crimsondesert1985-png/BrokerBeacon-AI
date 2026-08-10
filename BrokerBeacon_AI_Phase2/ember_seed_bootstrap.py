"""Seed Ember with a small set of public, verified Mortgage Matchup company pages.

This is a resilience bridge for periods when third-party search providers are
rate-limited. Records remain marked for NMLS verification and are processed by
the normal Ember pipeline; this module does not promote them directly to CRM.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from ember_jobs import enqueue, initialize as initialize_jobs

NOW = lambda: datetime.now().isoformat(timespec="seconds")

SEEDS = (
    ("257862", "Mortgage First Direct, Inc.", "", "NY", "https://mortgagematchup.com/Company/MortgageFirstDirectInc52332"),
    ("2343805", "Answer Home Lending, Inc.", "Granite Bay", "CA", "https://mortgagematchup.com/Company/AnswerHomeLendingInc24532"),
    ("1640242", "Motto Mortgage Above & Beyond", "Westlake", "OH", "https://mortgagematchup.com/Company/AboveBeyondMortgageCompany77222"),
    ("2275128", "Nations Mortgage LLC", "Southfield", "MI", "https://mortgagematchup.com/Company/NationsMortgageLLC88423"),
    ("212405", "CMS Mortgage Solutions, Inc.", "Virginia Beach", "VA", "https://mortgagematchup.com/Company/CMSMortgageSolutionsInc86362"),
    ("1550836", "Loan Inc", "", "MD", "https://mortgagematchup.com/Company/LoanVerifyInc37666"),
    ("1761573", "Adcom Group Inc", "Kirkland", "WA", "https://mortgagematchup.com/Company/AdcomGroupInc45686"),
    ("1729528", "Answer Home Loans, Inc", "Granite Bay", "CA", "https://mortgagematchup.com/Company/AnswerHomeLoansInc34743"),
    ("1865339", "Modern Mortgage Lending, Inc.", "", "CA", "https://mortgagematchup.com/Company/ModernLendingTeam55362"),
    ("2190509", "Rate Republic Inc.", "Chula Vista", "CA", "https://mortgagematchup.com/Company/RateRepublicInc72327"),
)


def install_verified_seed_bootstrap(app, db_path):
    """Insert idempotent source seeds and queue one bounded verification hunt."""
    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("pragma busy_timeout=30000")
            columns = {row[1] for row in conn.execute("pragma table_info(national_broker_index)")}
            required = {"nmls", "company", "city", "state", "source_name", "source_url", "verification_status", "indexed_at", "updated_at"}
            if not required.issubset(columns):
                app.logger.warning("EMBER_BOOTSTRAP skipped: national broker index schema not ready")
                return
            created = 0
            now = NOW()
            for nmls, company, city, state, url in SEEDS:
                exists = conn.execute(
                    "select 1 from national_broker_index where lower(source_url)=lower(?) or nmls=? limit 1",
                    (url, nmls),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    """insert into national_broker_index(
                       nmls,company,city,state,source_name,source_url,verification_status,indexed_at,updated_at
                       ) values(?,?,?,?,?,?,?,?,?)""",
                    (nmls, company, city, state, "Mortgage Matchup verified seed", url,
                     "Mortgage Matchup public listing - verify in NMLS", now, now),
                )
                created += 1
            initialize_jobs(conn)
            active = conn.execute(
                "select id from crawl_jobs where job_type='discovery_cycle' and status in ('Queued','Running') order by id limit 1"
            ).fetchone()
            queued = 0
            if not active:
                queued = enqueue(
                    conn,
                    "discovery_cycle",
                    payload={"state": "NY", "company_limit": 6, "contact_limit": 250},
                    priority=200,
                    max_attempts=3,
                )
            conn.commit()
            app.logger.warning("EMBER_BOOTSTRAP seeded=%s queued_job=%s", created, queued or "existing")
    except Exception:
        app.logger.exception("EMBER_BOOTSTRAP failed")
