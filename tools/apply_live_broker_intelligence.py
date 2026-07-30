from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "BrokerBeacon_AI_Phase2" / "app.py"
MIGRATIONS = ROOT / "BrokerBeacon_AI_Phase2" / "migrations.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Missing patch anchor: {label}")
    return text.replace(old, new, 1)


migration_text = MIGRATIONS.read_text(encoding="utf-8")
if '(7, "broker_dna_history"' not in migration_text:
    migration_anchor = '''""")
]

DEFAULT_WEIGHTS'''
    migration_replacement = '''"""),
(7, "broker_dna_history", """
create table if not exists broker_dna_snapshots(
    id integer primary key,
    prospect_id integer not null,
    dna_score integer not null,
    tier text not null,
    relationship_health integer not null,
    opportunity_strength integer not null,
    engagement_score integer not null,
    product_fit_score integer not null,
    captured_at text not null,
    foreign key(prospect_id) references prospects(id) on delete cascade
);
create index if not exists idx_broker_dna_snapshots_prospect on broker_dna_snapshots(prospect_id, captured_at desc);
create index if not exists idx_broker_dna_snapshots_date on broker_dna_snapshots(captured_at desc);
""")
]

DEFAULT_WEIGHTS'''
    migration_text = replace_once(migration_text, migration_anchor, migration_replacement, "migration 7")
    MIGRATIONS.write_text(migration_text, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
app = app.replace('BUILD_VERSION = "12.0"', 'BUILD_VERSION = "12.1"', 1)
app = app.replace('BUILD_NAME = "BROKER DNA"', 'BUILD_NAME = "LIVE BROKER INTELLIGENCE"', 1)
app = app.replace('VERSION 12.0 · BROKER DNA', 'VERSION 12.1 · LIVE BROKER INTELLIGENCE', 1)

css_anchor = '''@media(max-width:520px){.dna-components{grid-template-columns:1fr}}
</style>'''
css_replacement = '''@media(max-width:520px){.dna-components{grid-template-columns:1fr}}
.dna-trend{display:inline-flex;align-items:center;gap:4px;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}.dna-trend-up{background:#e5f6eb;color:#17653a}.dna-trend-down{background:#fdecef;color:#a51e33}.dna-trend-flat{background:#eef2f7;color:#60708a}.dark-mode .dna-trend-up{background:#123b2a;color:#8ce7b2}.dark-mode .dna-trend-down{background:#481c28;color:#ffadbd}.dark-mode .dna-trend-flat{background:#25344a;color:#b8c7db}
</style>'''
app = replace_once(app, css_anchor, css_replacement, "trend CSS")

api_anchor = '''        results = [calculate_broker_dna(c, row) for row in rows]
    results.sort(key=lambda x: (-x['dna_score'], x['company'].lower()))'''
api_replacement = '''        results = [calculate_broker_dna(c, row) for row in rows]
        for result in results:
            pid = result['prospect_id']
            latest = c.execute("select * from broker_dna_snapshots where prospect_id=? order by captured_at desc,id desc limit 1", (pid,)).fetchone()
            changed = (not latest or int(latest['dna_score']) != int(result['dna_score']) or int(latest['relationship_health']) != int(result['relationship_health']) or int(latest['engagement_score']) != int(result['engagement_score']) or int(latest['product_fit_score']) != int(result['product_fit_score']))
            if changed:
                c.execute("insert into broker_dna_snapshots(prospect_id,dna_score,tier,relationship_health,opportunity_strength,engagement_score,product_fit_score,captured_at) values(?,?,?,?,?,?,?,?)", (pid,result['dna_score'],result['tier'],result['relationship_health'],result['opportunity_strength'],result['engagement_score'],result['product_fit_score'],NOW()))
            history = c.execute("select dna_score,captured_at from broker_dna_snapshots where prospect_id=? order by captured_at desc,id desc limit 2", (pid,)).fetchall()
            delta = int(history[0]['dna_score']) - int(history[1]['dna_score']) if len(history) > 1 else 0
            result['trend_delta'] = delta
            result['trend_direction'] = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
            result['previous_score'] = int(history[1]['dna_score']) if len(history) > 1 else None
    results.sort(key=lambda x: (-x['dna_score'], x['company'].lower()))'''
app = replace_once(app, api_anchor, api_replacement, "DNA trend calculation")

summary_anchor = '''        'average_score': round(sum(x['dna_score'] for x in results) / len(results)) if results else 0,
    }'''
summary_replacement = '''        'average_score': round(sum(x['dna_score'] for x in results) / len(results)) if results else 0,
        'trending_up': sum(1 for x in results if x.get('trend_direction') == 'up'),
        'trending_down': sum(1 for x in results if x.get('trend_direction') == 'down'),
    }'''
app = replace_once(app, summary_anchor, summary_replacement, "trend summary")

history_anchor = '''@app.get("/api/broker-dna/<int:pid>")
def broker_dna_detail_api(pid):'''
history_replacement = '''@app.get("/api/broker-dna/<int:pid>/history")
def broker_dna_history_api(pid):
    try:
        days = max(1, min(365, int(request.args.get('days', 90))))
    except (TypeError, ValueError):
        days = 90
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec='seconds')
    with db() as c:
        prospect = c.execute("select id,company from prospects where id=?", (pid,)).fetchone()
        if not prospect:
            return jsonify(error="Prospect not found"), 404
        rows = [dict(x) for x in c.execute("select dna_score,tier,relationship_health,opportunity_strength,engagement_score,product_fit_score,captured_at from broker_dna_snapshots where prospect_id=? and captured_at>=? order by captured_at,id", (pid, cutoff)).fetchall()]
    return jsonify(prospect_id=pid, company=prospect['company'], days=days, history=rows)

@app.get("/api/broker-dna/<int:pid>")
def broker_dna_detail_api(pid):'''
app = replace_once(app, history_anchor, history_replacement, "DNA history endpoint")

card_anchor = '''<span class="dna-tier dna-tier-${String(x.tier).toLowerCase()}">Tier ${esc(x.tier)}</span><span class="pill">'''
card_replacement = '''<span class="dna-tier dna-tier-${String(x.tier).toLowerCase()}">Tier ${esc(x.tier)}</span><span class="dna-trend dna-trend-${x.trend_direction||'flat'}">${x.trend_direction==='up'?'▲':x.trend_direction==='down'?'▼':'—'} ${x.trend_delta?Math.abs(x.trend_delta)+' pts':'Stable'}</span><span class="pill">'''
app = replace_once(app, card_anchor, card_replacement, "trend badge")

method_anchor = '''<p>${esc(m.note||'')}</p>`;renderBrokerDna();'''
method_replacement = '''<p>${esc(m.note||'')}</p><p><b>Live movement:</b> ${s.trending_up||0} improving · ${s.trending_down||0} declining. Scores refresh whenever this workspace is opened and every five minutes while active.</p>`;renderBrokerDna();'''
app = replace_once(app, method_anchor, method_replacement, "trend methodology")

auto_anchor = '''load();dash();outreach();followups();dailyPlan();ints();missionControl();'''
auto_replacement = '''setInterval(()=>{if($('#brokerdna')?.classList.contains('active'))brokerDna()},300000);
load();dash();outreach();followups();dailyPlan();ints();missionControl();'''
app = replace_once(app, auto_anchor, auto_replacement, "automatic DNA refresh")

APP.write_text(app, encoding="utf-8")
py_compile.compile(str(APP), doraise=True)
py_compile.compile(str(MIGRATIONS), doraise=True)
print("Live Broker Intelligence applied and Python syntax validated.")
