"""Small, idempotent SQLite migration runner for BrokerBeacon."""
from datetime import datetime

MIGRATIONS = [
(1, "sprint2_intelligence", """
create table if not exists schema_migrations(version integer primary key,name text not null,applied_at text not null);
create table if not exists scoring_settings(key text primary key,label text not null,weight integer not null,description text not null,updated_at text not null);
create table if not exists product_catalog(id integer primary key,name text unique not null,category text not null,keywords text not null,talking_point text not null,is_active integer default 1,created_at text not null,updated_at text not null);
create table if not exists opportunity_snapshots(id integer primary key,prospect_id integer not null,score integer not null,tier text not null,confidence integer not null,reasons_json text not null,next_action text not null,product_matches_json text not null,created_at text not null);
"""),
(2, "sprint3_revenue_intelligence", """
create table if not exists revenue_settings(key text primary key,label text not null,value real not null,description text not null,updated_at text not null);
create table if not exists revenue_events(id integer primary key,prospect_id integer not null,event_type text not null,amount real default 0,loan_count integer default 1,notes text default '',event_at text not null,attributed_campaign_id integer,attribution_method text default '',created_at text not null);
create index if not exists idx_revenue_events_prospect on revenue_events(prospect_id);
create index if not exists idx_revenue_events_campaign on revenue_events(attributed_campaign_id);
create index if not exists idx_revenue_events_date on revenue_events(event_at);
""")]

DEFAULT_WEIGHTS = [
('base_verified','Verified data',8,'Rewards records with a verified status.'),
('recently_licensed','Recently licensed',18,'Rewards newly licensed or new-account signals.'),
('team_size','Loan officer roster',14,'Rewards firms with multiple public contacts or a larger team.'),
('government_fit','Government lending fit',14,'Rewards FHA, VA, USDA, DPA, and first-time-buyer alignment.'),
('niche_fit','HELOC / jumbo / niche fit',10,'Rewards product-fit signals outside standard agency lending.'),
('engagement','Engagement',16,'Rewards replies, meetings, campaign engagement, and active relationship stages.'),
('staleness','Reactivation urgency',12,'Rewards accounts that have gone long enough without a touch.'),
('followup_due','Follow-up urgency',8,'Rewards overdue or currently due follow-ups.')]


DEFAULT_REVENUE_SETTINGS = [
('average_loan_amount','Average loan amount',325000,'Used only for clearly labeled projected volume.'),
('revenue_bps','Estimated revenue basis points',35,'Used to estimate revenue from funded or projected volume.'),
('meeting_to_application_rate','Meeting-to-application assumption',0.35,'Projection assumption expressed as a decimal.'),
('application_to_funding_rate','Application-to-funding assumption',0.55,'Projection assumption expressed as a decimal.')]

DEFAULT_PRODUCTS = [
('Conventional','Agency','conventional,a-paper,agency','Lead with competitive conventional pricing and fast scenario support.'),
('FHA / Low-FICO Government','Government','fha,low fico,lower-fico,government','Offer a responsible second look on difficult FHA and lower-credit government files.'),
('VA','Government','va,veteran,military','Lead with VA scenario expertise and responsive eligibility reviews.'),
('USDA','Government','usda,rural','Offer rural-housing eligibility and structuring support.'),
('Down Payment Assistance','Government','dpa,down payment,first-time,first time','Connect first-time-buyer activity to applicable local assistance options.'),
('HELOC','Equity','heloc,equity,second lien','Position HELOCs for equity access without replacing a favorable first mortgage.'),
('Jumbo','Specialty','jumbo,high balance,luxury','Offer structure and pricing comparisons for higher-balance borrowers.'),
('Renovation','Specialty','renovation,rehab,fixer','Offer purchase-plus-improvement financing guidance where program rules fit.')]

def run_migrations(conn):
    conn.execute('create table if not exists schema_migrations(version integer primary key,name text not null,applied_at text not null)')
    applied={r[0] for r in conn.execute('select version from schema_migrations')}
    now=datetime.now().isoformat(timespec='seconds')
    for version,name,sql in MIGRATIONS:
        if version not in applied:
            conn.executescript(sql)
            conn.execute('insert into schema_migrations(version,name,applied_at) values(?,?,?)',(version,name,now))
    for key,label,weight,description in DEFAULT_WEIGHTS:
        conn.execute('insert or ignore into scoring_settings(key,label,weight,description,updated_at) values(?,?,?,?,?)',(key,label,weight,description,now))
    for key,label,value,description in DEFAULT_REVENUE_SETTINGS:
        conn.execute('insert or ignore into revenue_settings(key,label,value,description,updated_at) values(?,?,?,?,?)',(key,label,value,description,now))
    for name,category,keywords,talking_point in DEFAULT_PRODUCTS:
        conn.execute('insert or ignore into product_catalog(name,category,keywords,talking_point,is_active,created_at,updated_at) values(?,?,?,?,1,?,?)',(name,category,keywords,talking_point,now,now))
