"""Durable Ember state cursors, company crawl history, and activity events."""
from __future__ import annotations
import sqlite3
from datetime import datetime
NOW=lambda:datetime.now().isoformat(timespec="seconds")
SCHEMA="""
create table if not exists ember_state_cursors(state text primary key,last_index_id integer not null default 0,companies_processed integer not null default 0,contacts_found integer not null default 0,last_run_at text default '',updated_at text not null);
create table if not exists ember_activity(id integer primary key,event_type text not null,state text default '',company_name text default '',contact_id integer,title text not null,detail text default '',severity text not null default 'info',created_at text not null);
create index if not exists idx_ember_activity_created on ember_activity(id desc);
create table if not exists ember_company_history(id integer primary key,state text not null,company_name text not null,source_url text not null,source_domain text default '',index_id integer default 0,status text not null default 'Queued',contacts_found integer not null default 0,pages_fetched integer not null default 0,last_error text default '',first_seen_at text not null,last_crawled_at text default '',next_crawl_at text default '',unique(state,source_url));
create index if not exists idx_ember_company_state_status on ember_company_history(state,status,id desc);
"""
def initialize(conn:sqlite3.Connection)->None:
 conn.executescript(SCHEMA);conn.commit()
def record(conn:sqlite3.Connection,event_type:str,title:str,state:str='',company_name:str='',contact_id:int|None=None,detail:str='',severity:str='info')->int:
 initialize(conn);cur=conn.execute("insert into ember_activity(event_type,state,company_name,contact_id,title,detail,severity,created_at) values(?,?,?,?,?,?,?,?)",(event_type,state,company_name,contact_id,title[:240],detail[:2000],severity,NOW()));conn.commit();return int(cur.lastrowid)
