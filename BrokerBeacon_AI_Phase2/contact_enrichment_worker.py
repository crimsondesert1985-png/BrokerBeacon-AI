"""Continuously enrich contactless BrokerBeacon prospects from official websites.

This worker is deliberately conservative: it starts only from an existing clean
prospect identity, uses the official-site resolver/crawler, and writes contacts
only when a public phone or email was actually extracted. It never invents a
person, email, phone, or licensing status.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime

from ember_company_crawler import crawl_company
from prospect_quality import is_publishable_prospect

_started = False
_lock = threading.Lock()


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=30000")
    return conn


def _columns(conn, table):
    return {str(row[1]) for row in conn.execute(f"pragma table_info({table})")}


def _insert_dynamic(conn, table, values):
    columns = _columns(conn, table)
    payload = {k: v for k, v in values.items() if k in columns}
    if not payload:
        return 0
    names = list(payload)
    cur = conn.execute(
        f"insert into {table}({','.join(names)}) values({','.join('?' for _ in names)})",
        tuple(payload[name] for name in names),
    )
    return int(cur.lastrowid)


def _update_dynamic(conn, table, row_id, values):
    columns = _columns(conn, table)
    payload = {k: v for k, v in values.items() if k in columns and k != "id"}
    if not payload:
        return
    names = list(payload)
    conn.execute(
        f"update {table} set " + ",".join(f"{name}=?" for name in names) + " where id=?",
        tuple(payload[name] for name in names) + (row_id,),
    )


def enrich_batch(conn, *, limit=8):
    """Enrich a bounded batch and return auditable counts."""
    contact_cols = _columns(conn, "contacts")
    if "prospect_id" not in contact_cols:
        return {"examined": 0, "sites_completed": 0, "prospects_updated": 0, "contacts_created": 0, "failed": 0}
    rows = conn.execute(
        """select p.* from prospects p
           where trim(coalesce(p.company,''))<>''
             and not exists (
               select 1 from contacts c where c.prospect_id=p.id
                 and (trim(coalesce(c.phone,''))<>'' or trim(coalesce(c.email,''))<>'')
             )
           order by case when trim(coalesce(p.website,''))<>'' then 0 else 1 end,
                    coalesce(p.score,0) desc,p.id
           limit ?""",
        (max(1, min(int(limit), 25)),),
    ).fetchall()
    counts = {"examined": 0, "sites_completed": 0, "prospects_updated": 0, "contacts_created": 0, "failed": 0}
    for row in rows:
        counts["examined"] += 1
        company = str(row["company"] or "").strip()
        nmls = str(row["nmls"] or "").strip()
        source = str(row["source_name"] or "").strip()
        if not is_publishable_prospect(company, nmls, source):
            continue
        seed = {
            "company": company,
            "nmls": nmls,
            "website": str(row["website"] or "").strip(),
            "city": str(row["city"] or "").strip(),
            "state": str(row["state"] or "").strip().upper(),
            "phone": str(row["phone"] or "").strip(),
            "public_email": str(row["email"] or "").strip(),
        }
        try:
            result = crawl_company(seed, max_pages=3)
        except Exception:
            counts["failed"] += 1
            continue
        if result.get("status") != "Completed" or not result.get("record"):
            counts["failed"] += 1
            continue
        counts["sites_completed"] += 1
        record = dict(result["record"])
        phone = str(record.get("phone") or "").strip()
        email = str(record.get("public_email") or "").strip()
        website = str(record.get("website") or record.get("source_url") or "").strip()
        update = {"updated_at": datetime.now().isoformat(timespec="seconds")}
        if website:
            update["website"] = website
        if phone:
            update["phone"] = phone
        if email:
            update["email"] = email
        if len(update) > 1:
            _update_dynamic(conn, "prospects", int(row["id"]), update)
            counts["prospects_updated"] += 1

        created_for_prospect = 0
        for officer in record.get("officers") or []:
            officer_phone = str(officer.get("phone") or "").strip()
            officer_email = str(officer.get("public_email") or "").strip()
            name = str(officer.get("full_name") or "").strip()
            if not name or (not officer_phone and not officer_email):
                continue
            exists = conn.execute(
                """select 1 from contacts where prospect_id=? and lower(trim(coalesce(name,'')))=lower(trim(?))
                   and (coalesce(phone,'')=? or coalesce(email,'')=?) limit 1""",
                (int(row["id"]), name, officer_phone, officer_email),
            ).fetchone()
            if exists:
                continue
            now = datetime.now().isoformat(timespec="seconds")
            _insert_dynamic(conn, "contacts", {
                "prospect_id": int(row["id"]),
                "name": name,
                "title": str(officer.get("title") or "Mortgage professional"),
                "role": str(officer.get("title") or "Mortgage professional"),
                "phone": officer_phone,
                "email": officer_email,
                "nmls": str(officer.get("nmls_id") or ""),
                "city": str(officer.get("city") or row["city"] or ""),
                "state": str(officer.get("state") or row["state"] or ""),
                "roster_status": "Official company website - verify person/licensing before outreach",
                "source_name": "Official company website via Ember",
                "source_url": str(officer.get("source_url") or website),
                "created_at": now,
                "updated_at": now,
                "is_primary": 1 if created_for_prospect == 0 else 0,
            })
            created_for_prospect += 1
            counts["contacts_created"] += 1

        # If the site exposes a real company channel but no named person, keep a
        # clearly labeled main-office contact so an AE has a usable public route.
        if created_for_prospect == 0 and (phone or email):
            exists = conn.execute(
                """select 1 from contacts where prospect_id=?
                   and (trim(coalesce(phone,''))<>'' or trim(coalesce(email,''))<>'') limit 1""",
                (int(row["id"]),),
            ).fetchone()
            if not exists:
                now = datetime.now().isoformat(timespec="seconds")
                _insert_dynamic(conn, "contacts", {
                    "prospect_id": int(row["id"]),
                    "name": company + " main office",
                    "title": "Company contact",
                    "role": "Company contact",
                    "phone": phone,
                    "email": email,
                    "nmls": nmls,
                    "city": str(row["city"] or ""),
                    "state": str(row["state"] or ""),
                    "roster_status": "Official company website - verify person before outreach",
                    "source_name": "Official company website via Ember",
                    "source_url": website,
                    "created_at": now,
                    "updated_at": now,
                    "is_primary": 1,
                })
                counts["contacts_created"] += 1
        conn.commit()
    return counts


def install_contact_enrichment_worker(app, db_path):
    global _started
    with _lock:
        if _started:
            return app
        _started = True
    interval = max(300, min(int(os.getenv("PROSPECT_CONTACT_ENRICH_SECONDS", "600")), 3600))
    batch = max(1, min(int(os.getenv("PROSPECT_CONTACT_ENRICH_BATCH", "8")), 25))

    def loop():
        time.sleep(20)
        while True:
            try:
                with closing(_connect(db_path)) as conn:
                    counts = enrich_batch(conn, limit=batch)
                app.logger.warning(
                    "CONTACT_ENRICH examined=%s sites_completed=%s prospects_updated=%s contacts_created=%s failed=%s",
                    counts["examined"], counts["sites_completed"], counts["prospects_updated"],
                    counts["contacts_created"], counts["failed"],
                )
            except Exception:
                app.logger.exception("CONTACT_ENRICH worker recovered from error")
            time.sleep(interval)

    threading.Thread(target=loop, name="contact-enrichment", daemon=True).start()
    app.logger.warning("CONTACT_ENRICH scheduled interval=%ss batch=%s official_websites_only", interval, batch)
    return app


__all__ = ["enrich_batch", "install_contact_enrichment_worker"]
