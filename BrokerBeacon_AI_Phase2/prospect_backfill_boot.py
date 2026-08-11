"""Maintain a clean BrokerBeacon prospect catalog with restart-safe daily imports."""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from autonomous_prospecting import promote_warehouse_companies
from official_roster_import import import_missouri_broker_roster, promote_official_roster
from official_website_promotion import promote_official_website_contacts
from prospect_quality import is_publishable_prospect

_started = False
_lock = threading.Lock()
SCHEDULE_SCHEMA = """
create table if not exists prospect_import_schedule(
 id integer primary key check(id=1), status text not null default 'Never',
 started_at text default '', completed_at text default '', last_error text default '',
 last_total integer not null default 0
);
insert or ignore into prospect_import_schedule(id,status) values(1,'Never');
"""


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _parse(value: str):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _ensure_schedule_columns(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEDULE_SCHEMA)
    cols = _columns(conn, "prospect_import_schedule")
    if "last_missing_contacts" not in cols:
        conn.execute("alter table prospect_import_schedule add column last_missing_contacts integer not null default -1")
    if "last_contact_coverage" not in cols:
        conn.execute("alter table prospect_import_schedule add column last_contact_coverage integer not null default 0")
    conn.commit()


def _catalog_metrics(conn: sqlite3.Connection) -> dict:
    clean_total = sum(
        1 for r in conn.execute("select company,nmls,source_name from prospects")
        if is_publishable_prospect(r[0], r[1], r[2])
    )
    missing_contacts = int(conn.execute(
        """select count(*) from prospects p
           where trim(coalesce(p.company,''))<>''
             and not exists (select 1 from contacts c where c.prospect_id=p.id)"""
    ).fetchone()[0])
    with_contacts = max(0, clean_total - missing_contacts)
    coverage = int(round((with_contacts / clean_total) * 100)) if clean_total else 0
    return {
        "clean_total": clean_total,
        "missing_contacts": missing_contacts,
        "with_contacts": with_contacts,
        "contact_coverage": coverage,
    }


def _clean_catalog(conn: sqlite3.Connection) -> int:
    rows = conn.execute("select id,company,nmls,source_name from prospects").fetchall()
    bad = [int(r["id"]) for r in rows if not is_publishable_prospect(r["company"], r["nmls"], r["source_name"])]
    if not bad:
        return 0
    marks = ",".join("?" for _ in bad)
    conn.execute(f"delete from contacts where prospect_id in ({marks})", bad)
    conn.execute(f"delete from autonomous_prospect_links where prospect_id in ({marks})", bad)
    conn.execute(f"delete from prospects where id in ({marks})", bad)
    conn.commit()
    return len(bad)


def _guess_contact_name(company: str, email: str) -> str:
    local = (email or "").split("@", 1)[0].strip().lower()
    local = re.sub(r"[^a-z0-9._+-]+", "", local)
    if local and not any(token in local for token in ("info", "office", "contact", "loan", "mortgage", "admin", "support", "hello", "team", "sales", "noreply")):
        parts = re.split(r"[._+-]+", local)
        parts = [p for p in parts if p and not p.isdigit()]
        if 1 <= len(parts) <= 3 and all(2 <= len(p) <= 20 for p in parts):
            pretty = []
            for p in parts:
                pretty.append(p.upper() if len(p) <= 2 and p.isalpha() else p.title())
            if len(parts) == 1 and len(parts[0]) >= 5:
                first, rest = parts[0][0], parts[0][1:]
                if rest.isalpha():
                    return f"{first.upper()} {rest.title()}"
            return " ".join(pretty)
    company = (company or "").strip() or "Company"
    return f"{company} main office"


def seed_contacts_from_prospect_records(conn: sqlite3.Connection, *, limit: int = 5000) -> dict:
    """Create review-gated contacts only when a real public phone/email already exists."""
    contact_columns = _columns(conn, "contacts")
    if "prospect_id" not in contact_columns:
        return {"examined": 0, "created": 0, "skipped": 0}
    now = datetime.now().isoformat(timespec="seconds")
    rows = conn.execute(
        """select p.id,p.company,p.phone,p.email,p.city,p.state,p.nmls,p.website,p.source_name
           from prospects p
           where not exists (select 1 from contacts c where c.prospect_id=p.id)
           order by p.id limit ?""",
        (max(1, min(int(limit), 20000)),),
    ).fetchall()
    created = skipped = 0
    for row in rows:
        phone = str(row["phone"] or "").strip()
        email = str(row["email"] or "").strip()
        if not phone and not email:
            skipped += 1
            continue
        values = {
            "prospect_id": int(row["id"]),
            "name": _guess_contact_name(str(row["company"] or ""), email),
            "title": "Company contact",
            "role": "Company contact",
            "email": email,
            "phone": phone,
            "nmls": str(row["nmls"] or ""),
            "city": str(row["city"] or ""),
            "state": str(row["state"] or ""),
            "roster_status": "Company channel - verify person before outreach",
            "source_name": str(row["source_name"] or "Prospect record"),
            "source_url": str(row["website"] or ""),
            "created_at": now,
            "updated_at": now,
            "is_primary": 1,
        }
        payload = {k: v for k, v in values.items() if k in contact_columns}
        names = list(payload)
        conn.execute(
            f"insert into contacts({','.join(names)}) values({','.join('?' for _ in names)})",
            tuple(payload[n] for n in names),
        )
        created += 1
    conn.commit()
    return {"examined": len(rows), "created": created, "skipped": skipped}


def install_prospect_backfill_boot(app, db_path):
    global _started
    with _lock:
        if _started:
            return app
        _started = True

    def due(conn) -> bool:
        _ensure_schedule_columns(conn)
        row = conn.execute("select * from prospect_import_schedule where id=1").fetchone()
        metrics = _catalog_metrics(conn)
        if metrics["clean_total"] < 500:
            return True
        completed = _parse(str(row["completed_at"] or ""))
        started = _parse(str(row["started_at"] or ""))
        if row["status"] == "Running" and started and datetime.now() - started < timedelta(hours=2):
            return False
        # Run immediately after this completeness-aware migration, then every four
        # hours while material contact gaps remain. Once coverage is healthy, keep
        # the heavier import/enrichment cycle on its normal daily cadence.
        if int(row["last_missing_contacts"] or -1) != metrics["missing_contacts"]:
            return True
        if metrics["contact_coverage"] < 80:
            return not completed or datetime.now() - completed >= timedelta(hours=4)
        return not completed or datetime.now() - completed >= timedelta(hours=20)

    def claim(conn) -> bool:
        if not due(conn):
            return False
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute("update prospect_import_schedule set status='Running',started_at=?,last_error='' where id=1", (now,))
        conn.commit()
        return True

    def run_contact_seed():
        try:
            with closing(_connect(db_path)) as conn:
                removed = _clean_catalog(conn)
                website = promote_official_website_contacts(conn, state="", limit=5000)
                seeded = seed_contacts_from_prospect_records(conn, limit=5000)
                metrics = _catalog_metrics(conn)
            app.logger.warning(
                "CONTACT_SEED removed_invalid=%s website_created=%s website_updated=%s seeded_created=%s seeded_examined=%s seeded_skipped=%s contacts=%s missing=%s coverage=%s%%",
                removed, website.get("created", 0), website.get("updated", 0),
                seeded.get("created", 0), seeded.get("examined", 0), seeded.get("skipped", 0),
                metrics["with_contacts"], metrics["missing_contacts"], metrics["contact_coverage"],
            )
        except Exception:
            app.logger.exception("CONTACT_SEED failed")

    def run_once():
        try:
            with closing(_connect(db_path)) as conn:
                if not claim(conn):
                    metrics = _catalog_metrics(conn)
                    app.logger.warning(
                        "PROSPECT_DAILY skipped not_due total=%s missing_contacts=%s coverage=%s%%",
                        metrics["clean_total"], metrics["missing_contacts"], metrics["contact_coverage"],
                    )
                    return
                removed_invalid = _clean_catalog(conn)
                matchup = promote_warehouse_companies(conn, state="", limit=1000, minimum_score=85)
                website = promote_official_website_contacts(conn, state="", limit=5000)
                roster = import_missouri_broker_roster(conn, target_minimum=650)
                official = promote_official_roster(conn, target_minimum=650, limit=10000)
                website_after = promote_official_website_contacts(conn, state="", limit=5000)
                seeded = seed_contacts_from_prospect_records(conn, limit=5000)
                removed_after = _clean_catalog(conn)
                metrics = _catalog_metrics(conn)
                state_rows = conn.execute("""select upper(state),count(*) from prospects
                    where length(trim(coalesce(state,'')))=2 group by upper(state) order by upper(state)""").fetchall()
                now = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    """update prospect_import_schedule set status='Completed',completed_at=?,last_total=?,
                       last_missing_contacts=?,last_contact_coverage=?,last_error='' where id=1""",
                    (now, metrics["clean_total"], metrics["missing_contacts"], metrics["contact_coverage"]),
                )
                conn.commit()
            app.logger.warning(
                "PROSPECT_DAILY completed removed_invalid=%s removed_after=%s matchup_created=%s website_contacts_created=%s website_contacts_updated=%s roster_rows=%s official_created=%s official_updated=%s website_after_created=%s seeded_contacts=%s clean_total=%s missing_contacts=%s coverage=%s%% states=%s",
                removed_invalid, removed_after, matchup.get("prospects_created", 0),
                website.get("created", 0), website.get("updated", 0),
                roster.get("source_rows", 0), official.get("created", 0), official.get("updated", 0),
                website_after.get("created", 0), seeded.get("created", 0), metrics["clean_total"],
                metrics["missing_contacts"], metrics["contact_coverage"], len(state_rows),
            )
        except Exception as exc:
            try:
                with closing(_connect(db_path)) as conn:
                    _ensure_schedule_columns(conn)
                    conn.execute("update prospect_import_schedule set status='Failed',last_error=? where id=1", (str(exc)[:1000],))
                    conn.commit()
            except Exception:
                pass
            app.logger.exception("PROSPECT_DAILY failed")

    def loop():
        time.sleep(8)
        run_contact_seed()
        while True:
            run_once()
            time.sleep(3600)
            run_contact_seed()

    threading.Thread(target=loop, name="daily-prospect-import", daemon=True).start()
    app.logger.warning("PROSPECT_AUTOMATION scheduled completeness-aware contact seeding, quality cleanup, import, website promotion, and roster enrichment")
    return app


__all__ = ["install_prospect_backfill_boot", "seed_contacts_from_prospect_records"]
