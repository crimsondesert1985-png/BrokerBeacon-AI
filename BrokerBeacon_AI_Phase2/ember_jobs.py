"""Durable SQLite job queue and activity stream for Ember workers."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Mapping

TERMINAL_STATUSES = {"Completed", "Failed", "Cancelled"}
ACTIVE_STATUSES = {"Queued", "Running"}
ALL_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists crawl_jobs(
            id integer primary key,
            job_type text not null,
            state text not null default '',
            company_id integer,
            payload_json text not null default '{}',
            priority integer not null default 100,
            status text not null default 'Queued',
            attempts integer not null default 0,
            max_attempts integer not null default 3,
            available_at text not null,
            claimed_by text not null default '',
            claimed_at text not null default '',
            lock_expires_at text not null default '',
            completed_at text not null default '',
            last_error text not null default '',
            created_at text not null,
            updated_at text not null
        );
        create index if not exists idx_crawl_jobs_claim
            on crawl_jobs(status, available_at, priority, id);
        create index if not exists idx_crawl_jobs_lock
            on crawl_jobs(status, lock_expires_at);

        create table if not exists worker_status(
            worker_key text primary key,
            status text not null,
            current_job_id integer,
            last_heartbeat_at text not null,
            jobs_completed_today integer not null default 0,
            last_error text not null default '',
            started_at text not null,
            updated_at text not null
        );

        create table if not exists activity_events(
            id integer primary key,
            event_type text not null,
            worker_key text not null default '',
            job_id integer,
            company_id integer,
            contact_id integer,
            state text not null default '',
            message text not null,
            detail_json text not null default '{}',
            created_at text not null
        );
        create index if not exists idx_activity_events_created
            on activity_events(id desc);
        """
    )
    conn.commit()


def emit_event(
    conn: sqlite3.Connection,
    event_type: str,
    message: str,
    *,
    worker_key: str = "",
    job_id: int | None = None,
    company_id: int | None = None,
    contact_id: int | None = None,
    state: str = "",
    detail: Mapping[str, Any] | None = None,
) -> int:
    event_id = int(
        conn.execute(
            """insert into activity_events(
                event_type,worker_key,job_id,company_id,contact_id,state,message,detail_json,created_at
            ) values(?,?,?,?,?,?,?,?,?)""",
            (
                event_type,
                worker_key,
                job_id,
                company_id,
                contact_id,
                state,
                message,
                json.dumps(dict(detail or {}), default=str),
                now_iso(),
            ),
        ).lastrowid
    )
    conn.commit()
    return event_id


def enqueue(
    conn: sqlite3.Connection,
    job_type: str,
    *,
    state: str = "",
    company_id: int | None = None,
    payload: Mapping[str, Any] | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    available_at: str | None = None,
) -> int:
    initialize(conn)
    stamp = now_iso()
    job_id = int(
        conn.execute(
            """insert into crawl_jobs(
                job_type,state,company_id,payload_json,priority,status,attempts,max_attempts,
                available_at,created_at,updated_at
            ) values(?,?,?,?,?,'Queued',0,?,?,?,?)""",
            (
                job_type,
                state.upper()[:2],
                company_id,
                json.dumps(dict(payload or {}), default=str),
                int(priority),
                max(1, int(max_attempts)),
                available_at or stamp,
                stamp,
                stamp,
            ),
        ).lastrowid
    )
    emit_event(
        conn,
        "JobQueued",
        f"Queued {job_type} job #{job_id}",
        job_id=job_id,
        company_id=company_id,
        state=state.upper()[:2],
    )
    return job_id


def recover_stale_locks(conn: sqlite3.Connection) -> int:
    initialize(conn)
    stamp = now_iso()
    rows = conn.execute(
        """select id,job_type,state,company_id,attempts,max_attempts
           from crawl_jobs
           where status='Running' and lock_expires_at<>'' and lock_expires_at<=?""",
        (stamp,),
    ).fetchall()
    recovered = 0
    for row in rows:
        next_status = "Queued" if int(row["attempts"]) < int(row["max_attempts"]) else "Failed"
        conn.execute(
            """update crawl_jobs set status=?,claimed_by='',claimed_at='',lock_expires_at='',
               last_error='Worker lock expired',available_at=?,updated_at=? where id=? and status='Running'""",
            (next_status, stamp, stamp, row["id"]),
        )
        emit_event(
            conn,
            "JobRecovered" if next_status == "Queued" else "JobFailed",
            f"Recovered stale {row['job_type']} job #{row['id']}" if next_status == "Queued" else f"Job #{row['id']} exhausted retries after stale lock",
            job_id=row["id"],
            company_id=row["company_id"],
            state=row["state"],
        )
        recovered += 1
    conn.commit()
    return recovered


def claim_next(
    conn: sqlite3.Connection,
    worker_key: str,
    *,
    lease_seconds: int = 900,
) -> dict[str, Any] | None:
    initialize(conn)
    recover_stale_locks(conn)
    stamp = now_iso()
    lock_expires = (datetime.now() + timedelta(seconds=max(60, lease_seconds))).isoformat(timespec="seconds")
    conn.execute("begin immediate")
    row = conn.execute(
        """select * from crawl_jobs
           where status='Queued' and available_at<=? and attempts<max_attempts
           order by priority asc,id asc limit 1""",
        (stamp,),
    ).fetchone()
    if not row:
        conn.commit()
        return None
    updated = conn.execute(
        """update crawl_jobs set status='Running',attempts=attempts+1,claimed_by=?,claimed_at=?,
           lock_expires_at=?,updated_at=? where id=? and status='Queued'""",
        (worker_key, stamp, lock_expires, stamp, row["id"]),
    ).rowcount
    conn.commit()
    if updated != 1:
        return None
    claimed = conn.execute("select * from crawl_jobs where id=?", (row["id"],)).fetchone()
    emit_event(
        conn,
        "JobClaimed",
        f"{worker_key} claimed {claimed['job_type']} job #{claimed['id']}",
        worker_key=worker_key,
        job_id=claimed["id"],
        company_id=claimed["company_id"],
        state=claimed["state"],
    )
    result = dict(claimed)
    result["payload"] = json.loads(result.pop("payload_json") or "{}")
    return result


def complete(conn: sqlite3.Connection, job_id: int, worker_key: str, detail: Mapping[str, Any] | None = None) -> bool:
    initialize(conn)
    stamp = now_iso()
    row = conn.execute("select * from crawl_jobs where id=?", (job_id,)).fetchone()
    if not row:
        return False
    updated = conn.execute(
        """update crawl_jobs set status='Completed',completed_at=?,lock_expires_at='',updated_at=?,last_error=''
           where id=? and status='Running' and claimed_by=?""",
        (stamp, stamp, job_id, worker_key),
    ).rowcount
    if updated:
        emit_event(
            conn,
            "JobCompleted",
            f"Completed {row['job_type']} job #{job_id}",
            worker_key=worker_key,
            job_id=job_id,
            company_id=row["company_id"],
            state=row["state"],
            detail=detail,
        )
    conn.commit()
    return bool(updated)


def fail(conn: sqlite3.Connection, job_id: int, worker_key: str, error: str, *, retry_delay_seconds: int = 60) -> str:
    initialize(conn)
    row = conn.execute("select * from crawl_jobs where id=?", (job_id,)).fetchone()
    if not row:
        return "Missing"
    retry = int(row["attempts"]) < int(row["max_attempts"])
    status = "Queued" if retry else "Failed"
    available_at = (datetime.now() + timedelta(seconds=max(1, retry_delay_seconds))).isoformat(timespec="seconds")
    stamp = now_iso()
    conn.execute(
        """update crawl_jobs set status=?,available_at=?,claimed_by='',claimed_at='',lock_expires_at='',
           last_error=?,updated_at=? where id=? and claimed_by=?""",
        (status, available_at, str(error)[:2000], stamp, job_id, worker_key),
    )
    emit_event(
        conn,
        "JobRetried" if retry else "JobFailed",
        f"Retrying {row['job_type']} job #{job_id}" if retry else f"Failed {row['job_type']} job #{job_id}",
        worker_key=worker_key,
        job_id=job_id,
        company_id=row["company_id"],
        state=row["state"],
        detail={"error": str(error)[:500], "attempts": row["attempts"]},
    )
    conn.commit()
    return status


def heartbeat(
    conn: sqlite3.Connection,
    worker_key: str,
    *,
    status: str,
    current_job_id: int | None = None,
    jobs_completed_today: int = 0,
    last_error: str = "",
) -> None:
    initialize(conn)
    stamp = now_iso()
    conn.execute(
        """insert into worker_status(
            worker_key,status,current_job_id,last_heartbeat_at,jobs_completed_today,last_error,started_at,updated_at
        ) values(?,?,?,?,?,?,?,?)
        on conflict(worker_key) do update set
            status=excluded.status,current_job_id=excluded.current_job_id,
            last_heartbeat_at=excluded.last_heartbeat_at,
            jobs_completed_today=excluded.jobs_completed_today,
            last_error=excluded.last_error,updated_at=excluded.updated_at""",
        (worker_key, status, current_job_id, stamp, jobs_completed_today, last_error[:2000], stamp, stamp),
    )
    conn.commit()
