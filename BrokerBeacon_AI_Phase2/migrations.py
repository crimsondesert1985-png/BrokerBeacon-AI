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
"""),
(3, "voice_agent", """
create table if not exists voice_calls(id integer primary key,prospect_id integer not null,contact_id integer not null,twilio_sid text default '',status text not null default 'Queued',answered_by text default '',transcript text default '',disposition text default '',appointment_id integer,created_at text not null,updated_at text not null);
create table if not exists appointments(id integer primary key,prospect_id integer not null,contact_id integer not null,start_at text not null,status text not null default 'Scheduled',source text not null default 'AI Voice Agent',notes text default '',created_at text not null);
create index if not exists idx_voice_calls_contact on voice_calls(contact_id);
create index if not exists idx_voice_calls_created on voice_calls(created_at);
create index if not exists idx_appointments_start on appointments(start_at);
"""),
(4, "drip_campaign_automation", """
create table if not exists automation_runs(id integer primary key,run_type text not null,started_at text not null,finished_at text not null,sent integer default 0,failed integer default 0,skipped integer default 0,suppressed integer default 0,detail text default '');
create index if not exists idx_automation_runs_started on automation_runs(started_at);
"""),
(5, "production_intelligence", """
create table if not exists production_imports(id integer primary key,source_name text not null,source_type text not null default 'CSV',data_as_of text default '',file_name text default '',rows_imported integer default 0,created_at text not null);
create table if not exists production_records(id integer primary key,import_id integer not null,prospect_id integer,company text not null,company_nmls text default '',lo_name text default '',lo_nmls text default '',period_month text not null,loan_type text not null default 'Other',purpose text not null default 'Other',units integer not null default 0,volume real not null default 0,source_name text not null,data_as_of text default '',created_at text not null);
create index if not exists idx_prod_company on production_records(company);
create index if not exists idx_prod_period on production_records(period_month);
create index if not exists idx_prod_lo on production_records(lo_name);
create index if not exists idx_prod_type on production_records(loan_type);
"""),
(6, "broker_dna", """
create table if not exists broker_dna(
    prospect_id integer primary key,
    dna_score integer not null default 0,
    tier text not null default 'D',
    relationship_health integer not null default 0,
    opportunity_strength integer not null default 0,
    engagement_score integer not null default 0,
    product_fit_score integer not null default 0,
    next_best_action text not null default '',
    reasons_json text not null default '[]',
    calculated_at text not null,
    updated_at text not null,
    foreign key(prospect_id) references prospects(id) on delete cascade
);
create index if not exists idx_broker_dna_score on broker_dna(dna_score desc);
create index if not exists idx_broker_dna_tier on broker_dna(tier);
create index if not exists idx_broker_dna_relationship on broker_dna(relationship_health desc);
"""),
(7, "call_outcome_loop", """
alter table sales_actions add column objections text default '';
alter table sales_actions add column next_step text default '';
alter table sales_actions add column source_view text default '';
create index if not exists idx_sales_actions_prospect_created on sales_actions(prospect_id,created_at desc);
create index if not exists idx_sales_actions_follow_up on sales_actions(follow_up_date);
"""),
(8, "intelligent_follow_up", """
alter table outreach add column source_action_id integer default 0;
alter table outreach add column recommended_send_at text default '';
alter table outreach add column rationale text default '';
create index if not exists idx_outreach_source_action on outreach(source_action_id);
"""),
(9, "outreach_execution_center", """
alter table outreach add column destination text default '';
alter table outreach add column scheduled_at text default '';
alter table outreach add column approved_at text default '';
alter table outreach add column sent_at text default '';
alter table outreach add column error text default '';
alter table outreach add column delivery_method text default '';
alter table outreach add column updated_at text default '';
create table if not exists outreach_events(
    id integer primary key,
    outreach_id integer not null,
    event_type text not null,
    detail text default '',
    created_at text not null
);
create index if not exists idx_outreach_status_schedule on outreach(status,scheduled_at);
create index if not exists idx_outreach_events_outreach on outreach_events(outreach_id,id);
""")
]

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
    # Compatibility columns for existing databases. SQLite lacks ADD COLUMN IF NOT EXISTS,
    # so inspect the schema first.
    contact_cols={r[1] for r in conn.execute('pragma table_info(contacts)')}
    if 'voice_consent' not in contact_cols:
        conn.execute('alter table contacts add column voice_consent integer default 0')
    if 'voice_opt_out' not in contact_cols:
        conn.execute('alter table contacts add column voice_opt_out integer default 0')

    recipient_cols={r[1] for r in conn.execute('pragma table_info(campaign_recipients)')}
    if 'attempts' not in recipient_cols:
        conn.execute('alter table campaign_recipients add column attempts integer default 0')
    if 'last_attempt_at' not in recipient_cols:
        conn.execute("alter table campaign_recipients add column last_attempt_at text default ''")
