from flask import Flask, request, jsonify, render_template_string, Response, send_file, make_response
import sqlite3, io, csv, os, json, re, uuid, smtplib, ssl, urllib.parse, urllib.request, base64
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path

app = Flask(__name__)
DB = Path(__file__).with_name("brokerbeacon.db")
NOW = lambda: datetime.now().isoformat(timespec="seconds")

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BrokerBeacon AI</title>
<style>
:root{--b:#060916;--p:#10182f;--p2:#0b1226;--l:#ffffff18;--t:#f7f8ff;--m:#9aa5c8;--v:#7c5cff;--c:#23d4fd;--g:#43dfa7;--y:#ffd166;--r:#ff6b8a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 12% 0,#5d3fff55,transparent 28%),radial-gradient(circle at 100% 15%,#23d4fd22,transparent 24%),var(--b);color:var(--t);font:14px Inter,Segoe UI,Arial,sans-serif}.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}aside{padding:24px 16px;border-right:1px solid var(--l);background:#080d1dee;position:sticky;top:0;height:100vh}.brand{font-size:20px;font-weight:850;margin-bottom:8px}.brand span{color:var(--c)}.version{font-size:10px;color:var(--m);margin-bottom:25px}nav button{display:block;width:100%;border:0;background:transparent;color:var(--m);text-align:left;padding:12px;border-radius:10px;margin:5px 0;cursor:pointer}nav button.active,nav button:hover{background:#7c5cff22;color:white}main{padding:28px;min-width:0}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--l);background:#ffffff0b;color:white;padding:10px 13px;border-radius:10px;cursor:pointer;text-decoration:none}.btn:hover{background:#ffffff16}.primary{background:linear-gradient(135deg,var(--v),#5a9cff);border:0}.danger{color:#ff9bb1}.view{display:none}.view.active{display:block}.hero,.panel,.metric{background:#111a34dd;border:1px solid var(--l);border-radius:17px;box-shadow:0 22px 60px #0005;backdrop-filter:blur(10px)}.hero{padding:24px;display:flex;justify-content:space-between;align-items:end;gap:20px}.hero p,.muted{color:var(--m);line-height:1.55}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.metric{padding:18px}.metric span{color:var(--m);font-size:12px}.metric strong{display:block;font-size:30px;margin-top:8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{padding:19px}.filters{display:flex;gap:8px;margin-bottom:12px}input,select,textarea{background:#0c142a;color:white;border:1px solid var(--l);border-radius:9px;padding:10px;outline:0}.filters input{flex:1}table{width:100%;border-collapse:collapse}th,td{padding:13px;border-bottom:1px solid var(--l);text-align:left;vertical-align:middle}th{font-size:10px;color:var(--m);text-transform:uppercase}.pill{background:#23d4fd15;color:#8cecff;padding:5px 8px;border-radius:999px;font-size:10px;white-space:nowrap}.score{color:var(--g);font-weight:800}.board{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.col{min-height:420px;background:#ffffff06;border:1px solid var(--l);border-radius:13px;padding:10px}.card{background:var(--p);border:1px solid var(--l);border-radius:10px;padding:11px;margin:8px 0}.card small{color:var(--m)}label{display:block;color:var(--m);font-size:11px;margin:13px 0 6px}.full{width:100%}textarea{width:100%;min-height:220px;line-height:1.5}.subject{width:100%;margin:10px 0}.int{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.integration{text-align:center}.integration b{font-size:18px}.integration p{color:var(--m);min-height:45px}.activity div{padding:9px 0;border-bottom:1px solid var(--l)}dialog{background:#0d1428;color:white;border:1px solid var(--l);border-radius:15px;width:min(860px,94vw);max-height:90vh;overflow:auto}dialog::backdrop{background:#000b}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.formgrid input,.formgrid select,.formgrid textarea{width:100%}.toast{position:fixed;right:20px;bottom:20px;background:var(--p);padding:12px;border:1px solid var(--l);border-radius:10px;display:none;z-index:99}.priority{display:grid;gap:10px}.priority-card{display:grid;grid-template-columns:64px 1fr auto;gap:14px;align-items:center;padding:13px;border:1px solid var(--l);border-radius:13px;background:#ffffff06}.orb{width:56px;height:56px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--g) calc(var(--s)*1%),#ffffff12 0);font-weight:900}.orb:before{content:"";position:absolute}.reason{color:var(--m);font-size:12px;margin-top:4px}.tag{display:inline-block;padding:4px 7px;border-radius:999px;background:#ffffff0d;color:#c8d0ec;font-size:10px;margin:2px}.scoregrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.scorebox{padding:13px;border:1px solid var(--l);border-radius:12px;background:#ffffff06}.scorebox strong{display:block;font-size:24px;margin-top:5px}.profile-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.tabs{display:flex;gap:6px;margin:14px 0}.tabs button{flex:1}.tabpane{display:none}.tabpane.active{display:block}.memory-item{padding:10px;border-left:3px solid var(--v);background:#ffffff05;margin:8px 0;border-radius:0 10px 10px 0}.smallbtn{padding:7px 9px;font-size:12px}.kicker{font-size:10px;letter-spacing:.12em;color:var(--c);font-weight:800}.nextaction{border-left:4px solid var(--g);padding:12px 14px;background:#43dfa710;border-radius:0 12px 12px 0}.explain li{margin:8px 0;color:#cfd5ed}.empty{padding:30px;text-align:center;color:var(--m)}.bars{display:grid;gap:12px}.barrow{display:grid;grid-template-columns:110px 1fr 42px;gap:10px;align-items:center}.bartrack{height:10px;background:#ffffff0b;border-radius:999px;overflow:hidden}.barfill{height:100%;background:linear-gradient(90deg,var(--v),var(--c));border-radius:999px}.exec{background:linear-gradient(135deg,#171f3e,#0e1733)}.top-account{display:grid;grid-template-columns:54px 1fr 120px 90px;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--l)}.rank{font-size:24px;color:var(--c);font-weight:900}.mini{font-size:11px;color:var(--m)}.state-map{display:grid;grid-template-columns:repeat(5,1fr);grid-template-areas:"mi . va . ." ". tn nc . ." ". . sc . ." ". . ga . .";gap:10px;min-height:300px;align-content:center}.state-tile{aspect-ratio:1.15;border:1px solid var(--l);border-radius:15px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(124,92,255,var(--heat));transition:.2s}.state-tile:hover{transform:translateY(-2px)}.state-tile b{font-size:24px}.state-tile span{color:var(--m);font-size:11px;margin-top:4px}.demo-lock{opacity:.55;cursor:not-allowed!important}.demo-banner{padding:10px 14px;border:1px solid #23d4fd44;background:#23d4fd10;border-radius:12px;margin-bottom:14px;color:#ccefff}.value-story{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.value-story>div{padding:14px;border:1px solid var(--l);border-radius:12px;background:#ffffff06}.value-story b{display:block;margin-bottom:5px}@media(max-width:700px){.state-map{grid-template-columns:repeat(3,1fr);grid-template-areas:"mi va va" "tn nc nc" "ga sc sc"}.value-story{grid-template-columns:1fr}}@media print{aside,.top .actions,nav,.btn{display:none!important}.app{display:block}.view{display:none!important}#boss{display:block!important}main{padding:0;background:white;color:#111}.hero,.panel,.metric{box-shadow:none;background:white;color:#111;border:1px solid #ddd}.muted,.mini{color:#555}.tag,.pill{border:1px solid #bbb;color:#222;background:#f5f5f5}}
.plan-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.action-row{display:grid;grid-template-columns:52px 1fr auto;gap:12px;align-items:center;padding:13px;border-bottom:1px solid var(--l)}.action-row:last-child{border-bottom:0}.activity-chip{display:inline-block;padding:5px 8px;border-radius:999px;background:#43dfa715;color:#91f2cb;font-size:10px}.goalring{width:110px;height:110px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--c) calc(var(--goal)*1%),#ffffff12 0);margin:auto}.goalring>div{width:82px;height:82px;border-radius:50%;background:var(--p2);display:grid;place-items:center;text-align:center;font-weight:900}.timeline{display:grid;gap:10px}.timeline-item{padding:11px 12px;border-left:3px solid var(--c);background:#ffffff05;border-radius:0 10px 10px 0}.callout{padding:14px;border:1px solid #43dfa744;background:#43dfa70d;border-radius:12px}.stale{color:var(--y);font-size:10px}.outcome-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.outcome-grid button{width:100%}@media(max-width:900px){.plan-grid{grid-template-columns:1fr}}@media(max-width:1050px){.board{grid-template-columns:repeat(2,1fr)}.scoregrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:900px){.app{grid-template-columns:1fr}aside{display:none}.metrics,.grid,.int{grid-template-columns:1fr 1fr}}@media(max-width:600px){main{padding:15px}.metrics,.grid,.board,.int,.formgrid,.scoregrid{grid-template-columns:1fr}.top,.hero,.profile-head{align-items:flex-start;flex-direction:column;gap:12px}.filters{flex-direction:column}.priority-card{grid-template-columns:56px 1fr}.priority-card>button{grid-column:1/-1}.actions{width:100%}.actions>*{flex:1;text-align:center}}
.contact-card{display:grid;gap:10px;padding:14px;border:1px solid var(--l);border-radius:13px;background:#ffffff06;margin-bottom:14px}.contact-line{display:flex;justify-content:space-between;gap:12px;align-items:center}.contact-line span{color:var(--m);font-size:11px}.contact-actions{display:flex;gap:7px;flex-wrap:wrap}.contact-cell{min-width:180px}.contact-cell a{display:block;color:#bdefff;text-decoration:none;margin:2px 0}.contact-missing{color:var(--m);font-size:11px}.contact-badge{display:inline-block;padding:4px 7px;border-radius:999px;background:#43dfa715;color:#83f0c4;font-size:10px;margin-top:5px}.contact-list{display:grid;gap:10px}.person-card{border:1px solid var(--l);border-radius:13px;padding:13px;background:#ffffff06}.person-card.primary-contact{border-color:#43dfa766;background:#43dfa70b}.person-top{display:flex;justify-content:space-between;gap:10px}.person-meta{color:var(--m);font-size:11px;margin-top:4px}.contact-tools{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.copybtn{font-size:10px;padding:5px 7px}.contact-form{border-top:1px solid var(--l);margin-top:14px;padding-top:14px}.contact-form .formgrid{grid-template-columns:1fr 1fr}.contact-note{font-size:11px;color:var(--m);margin-top:8px}.decision{color:var(--y);font-size:10px;font-weight:800}.source-link{font-size:10px;color:#8cecff;text-decoration:none}.roster-section{margin-top:15px}.roster-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.roster-title h4{margin:0}.officer-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:9px}.officer-details div{background:#ffffff05;border-radius:8px;padding:7px}.officer-details small{display:block;color:var(--m)}.contact-search{display:flex;gap:8px;margin:10px 0}.candidate-card{border:1px dashed #8cecff66;border-radius:12px;padding:12px;margin-top:9px}.candidate-actions{display:flex;gap:7px;margin-top:8px}.roster-note{padding:10px;border-radius:10px;background:#ffd76d12;color:#ffe6a1;font-size:11px}.wide-form{grid-column:1/-1}@media(max-width:650px){.officer-details{grid-template-columns:1fr}}.copilot-layout{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}.askbox{display:flex;gap:8px}.askbox input{flex:1;font-size:15px}.suggestions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.answer{min-height:180px;white-space:pre-wrap;line-height:1.65}.briefline{padding:11px 0;border-bottom:1px solid var(--l)}.briefline:last-child{border:0}.confidence{font-size:10px;color:var(--m)}@media(max-width:900px){.copilot-layout{grid-template-columns:1fr}}
:root{
  --bg:#f4fbf6;
  --panel:#ffffff;
  --panel-2:#eef9f1;
  --text:#163524;
  --muted:#688174;
  --line:#d8eadf;
  --green:#138a48;
  --green-2:#21a95b;
  --green-3:#e4f7ea;
  --green-dark:#0b6534;
  --shadow:0 12px 34px rgba(17,111,58,.10);
}
*{box-sizing:border-box}
body{
  background:linear-gradient(180deg,#f8fdf9 0%,#eff9f2 100%) !important;
  color:var(--text) !important;
}
aside,.sidebar{
  background:linear-gradient(180deg,#0e7b3f 0%,#0a6333 100%) !important;
  color:#fff !important;
  border-right:none !important;
  box-shadow:8px 0 28px rgba(12,95,48,.12);
}
aside h1,aside h2,aside h3,.sidebar h1,.sidebar h2,.sidebar h3{
  color:#fff !important;
}
aside small,aside .muted,.sidebar small,.sidebar .muted{
  color:#dff5e7 !important;
}
nav button,.nav button,.sidebar button{
  color:#effbf3 !important;
  background:transparent !important;
  border:1px solid transparent !important;
}
nav button:hover,.nav button:hover,.sidebar button:hover,
nav button.active,.nav button.active,.sidebar button.active{
  background:#ffffff1f !important;
  border-color:#ffffff38 !important;
  color:#fff !important;
}
main,.main{
  background:transparent !important;
}
.card,.panel,.modal,.profile-card,.metric,.stat,.contact-card,.copilot-card{
  background:var(--panel) !important;
  color:var(--text) !important;
  border:1px solid var(--line) !important;
  box-shadow:var(--shadow) !important;
}
h1,h2,h3,h4,h5{
  color:var(--green-dark) !important;
}
.kicker,.eyebrow{
  color:var(--green) !important;
  letter-spacing:.08em;
}
.btn,button.btn,.smallbtn{
  background:#fff !important;
  color:var(--green-dark) !important;
  border:1px solid #b8dcc6 !important;
  box-shadow:0 4px 12px rgba(17,111,58,.06);
}
.btn:hover,button.btn:hover,.smallbtn:hover{
  background:var(--green-3) !important;
  border-color:#7cc795 !important;
  transform:translateY(-1px);
}
.btn.primary,.primary,.cta,.savebtn{
  background:linear-gradient(135deg,var(--green-2),var(--green)) !important;
  color:#fff !important;
  border-color:transparent !important;
}
.btn.primary:hover,.primary:hover,.cta:hover,.savebtn:hover{
  background:linear-gradient(135deg,#28b964,#0f7c41) !important;
}
input,select,textarea{
  background:#fff !important;
  color:var(--text) !important;
  border:1px solid #cfe3d6 !important;
}
input:focus,select:focus,textarea:focus{
  outline:none !important;
  border-color:#51b878 !important;
  box-shadow:0 0 0 3px rgba(33,169,91,.12) !important;
}
table{
  background:#fff !important;
  color:var(--text) !important;
  border-radius:14px;
  overflow:hidden;
}
thead th{
  background:#eaf7ee !important;
  color:#0d6b37 !important;
  border-bottom:1px solid #cfe6d7 !important;
}
tbody tr{
  background:#fff !important;
}
tbody tr:nth-child(even){
  background:#fbfefc !important;
}
tbody tr:hover{
  background:#eef9f1 !important;
}
td{
  border-bottom:1px solid #e2eee6 !important;
}
.pill,.tag,.badge,.contact-badge{
  background:#e3f6e9 !important;
  color:#0d6f39 !important;
  border:1px solid #bee3ca !important;
}
.score{
  color:#0f8c48 !important;
}
a{
  color:#0f8645;
}
a:hover{
  color:#086331;
}
.muted,small,.subtle,.contact-missing{
  color:var(--muted) !important;
}
.progress,.progressbar{
  background:#dfeee4 !important;
}
.progress > div,.progressbar > div{
  background:linear-gradient(90deg,#27b963,#0f8d49) !important;
}
hr{
  border-color:var(--line) !important;
}
.modal-backdrop,.overlay{
  background:rgba(9,67,34,.34) !important;
}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:#edf6f0}
::-webkit-scrollbar-thumb{background:#9fcfaf;border-radius:10px}
::-webkit-scrollbar-thumb:hover{background:#76b98c}


.mission-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:14px}.mission-span-2{grid-column:span 2}.brief-card{white-space:pre-line;line-height:1.65;padding:12px;background:var(--green-3);border-radius:12px;margin-bottom:12px}.campaign-layout{display:grid;grid-template-columns:.9fr 1.1fr;gap:14px;margin-top:14px}.campaign-row{padding:14px;border:1px solid var(--line);border-radius:13px;margin:10px 0;background:#fff}.campaign-stats{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:10px}.campaign-stats div{background:var(--panel-2);padding:8px;border-radius:9px;text-align:center}.campaign-stats b{display:block;color:var(--green-dark)}@media(max-width:1000px){.mission-grid{grid-template-columns:1fr 1fr}.mission-span-2{grid-column:span 2}.campaign-layout{grid-template-columns:1fr}}@media(max-width:650px){.mission-grid{grid-template-columns:1fr}.mission-span-2{grid-column:auto}.campaign-stats{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="app"><aside><div class="brand">Broker<span>Beacon</span> AI</div><div class="version">VERSION 6.0 · MISSION CONTROL</div><nav><button class="active" data-v="dashboard">✦ Command Center</button><button data-v="copilot">✦ AI Copilot</button><button data-v="daily">⚡ Daily Plan</button><button data-v="prospects">◉ Prospects</button><button data-v="outreach">✎ Outreach</button><button data-v="campaigns">✉ Campaigns</button><button data-v="pipeline">▦ Pipeline</button><button data-v="followups">✓ Follow-ups</button><button data-v="territory">⌖ Territory</button><button data-v="boss">◆ Executive View</button><button data-v="integrations">⚙ Integrations</button></nav></aside><main><div class="top"><div><small>AI OPERATING SYSTEM FOR WHOLESALE AES</small><h1 id="title">Command Center</h1></div><div class="actions"><button class="btn" id="import">Compliant Import</button><a class="btn" href="/api/export">Export CSV</a><button class="btn primary" id="add">+ Add Prospect</button></div></div>
<section id="dashboard" class="view active"><div class="hero"><div><div class="kicker">AE MISSION CONTROL</div><h2>Good morning, Clay. Here is what deserves attention first.</h2><p>One screen for priority calls, newly discovered accounts, stale relationships, product opportunities, campaign activity, weekly goals, and the AI morning brief.</p></div><button class="btn primary" onclick="show('daily')">Start today’s plan</button></div><div class="metrics"><div class="metric"><span>Priority calls today</span><strong id="mcCalls">0</strong></div><div class="metric"><span>New broker alerts</span><strong id="mcNew">0</strong></div><div class="metric"><span>Relationships at risk</span><strong id="mcRisk">0</strong></div><div class="metric"><span>Meetings this week</span><strong id="mcMeetings">0</strong></div></div><div class="mission-grid"><div class="panel mission-span-2"><div class="profile-head"><div><h3>Today’s priorities</h3><p class="muted">Ranked by opportunity, follow-up urgency, and relationship inactivity.</p></div><button class="btn smallbtn" onclick="show('daily')">Open full plan</button></div><div id="mcPriorities" class="priority"></div></div><div class="panel"><h3>AI morning brief</h3><div id="mcBrief" class="brief-card muted">Loading…</div><button class="btn smallbtn" onclick="missionControl()">Refresh brief</button></div><div class="panel"><h3>New broker alerts</h3><div id="mcAlerts" class="activity"></div></div><div class="panel"><h3>Brokers at risk</h3><div id="mcAtRisk" class="activity"></div></div><div class="panel"><h3>Product opportunities</h3><div id="mcProducts" class="bars"></div></div><div class="panel"><h3>This week’s goals</h3><div id="mcGoals"></div></div><div class="panel"><h3>Campaign performance</h3><div id="mcCampaigns"></div><button class="btn smallbtn" onclick="show('campaigns')">Manage campaigns</button></div></div></section>
<section id="copilot" class="view"><div class="hero"><div><div class="kicker">BROKERBEACON COPILOT</div><h2>Ask your territory a question. Get a ranked, explainable answer.</h2><p>The Copilot uses your BrokerBeacon prospect, pipeline, follow-up, and activity data. It does not invent email opens, licensing events, or production data that are not stored in your database.</p></div><span class="pill">Database-grounded</span></div><div class="copilot-layout" style="margin-top:14px"><div class="panel"><h3>Ask BrokerBeacon</h3><div class="askbox"><input id="copilotQuestion" placeholder="Example: Who should I call first today?"><button class="btn primary" id="askCopilot">Ask</button></div><div class="suggestions"><button class="btn smallbtn copilotPrompt">Who should I call first today?</button><button class="btn smallbtn copilotPrompt">Which Charlotte prospects need attention?</button><button class="btn smallbtn copilotPrompt">Show overdue follow-ups</button><button class="btn smallbtn copilotPrompt">Find high-score government-loan prospects</button></div><div id="copilotAnswer" class="answer muted" style="margin-top:16px">Ask a question to generate a prioritized answer from your current database.</div></div><div class="panel"><h3>Morning briefing</h3><div id="morningBrief"><div class="empty">Loading briefing…</div></div><button class="btn" style="margin-top:12px" onclick="copilotBrief()">Refresh briefing</button></div></div></section><section id="daily" class="view"><div class="hero"><div><div class="kicker">AI-GUIDED WORKDAY</div><h2>Your five best actions, ranked and ready.</h2><p>BrokerBeacon combines opportunity score, pipeline stage, follow-up urgency, and recent activity to create a focused daily call plan.</p></div><button class="btn primary" onclick="dailyPlan()">Refresh plan</button></div><div class="metrics"><div class="metric"><span>Calls logged today</span><strong id="dcalls">0</strong></div><div class="metric"><span>Emails logged today</span><strong id="demails">0</strong></div><div class="metric"><span>Conversations this week</span><strong id="dconvos">0</strong></div><div class="metric"><span>Meetings created this week</span><strong id="dmeetings">0</strong></div></div><div class="plan-grid"><div class="panel"><div class="profile-head"><div><h3>Recommended action queue</h3><p class="muted">Highest-value unfinished actions appear first.</p></div><span class="pill">Top 5</span></div><div id="dailyQueue"></div></div><div><div class="panel"><h3>Daily activity goal</h3><div class="goalring" id="goalring" style="--goal:0"><div><span><strong id="goalPct">0%</strong><br><small class="muted">10 actions</small></span></div></div><div id="goalText" class="muted" style="text-align:center;margin-top:12px"></div></div><div class="panel" style="margin-top:14px"><h3>Recent sales activity</h3><div id="salesTimeline" class="timeline"></div></div></div></div></section><section id="prospects" class="view"><div class="filters"><input id="search" placeholder="Search company, owner, city"><select id="state"><option>All</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select><select id="signal"><option>All</option><option>Newly Licensed</option><option>Team Growth</option><option>VA/FHA Fit</option><option>Imported</option><option>Manual</option><option>Verified Public Record</option><option>Needs Verification</option></select><select id="pstatus"><option>All statuses</option><option>New</option><option>Contacted</option><option>Replied</option><option>Meeting</option><option>Approved</option></select><select id="minscore"><option value="0">Any score</option><option value="70">70+</option><option value="80">80+</option><option value="90">90+</option></select></div><div class="panel" style="overflow:auto"><table><thead><tr><th>Company</th><th>Contact</th><th>Signal</th><th>Location</th><th>Fit</th><th>Score</th><th>Verification</th><th>Status</th><th></th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section id="outreach" class="view"><div class="grid"><div class="panel"><h3>Personalized outreach builder</h3><label>Prospect</label><select id="op" class="full"></select><label>Channel</label><select id="channel" class="full"><option>Email</option><option>LinkedIn</option><option>Phone</option></select><label>Angle</label><select id="angle" class="full"><option>Recommended by intelligence engine</option><option>Congratulations + growth support</option><option>VA/FHA scenario support</option><option>Fast onboarding</option><option>HELOC and niche products</option></select><button class="btn primary full" id="gen" style="margin-top:15px">Generate personalized draft</button></div><div class="panel"><button class="btn primary" id="queue" disabled style="float:right">Approve & queue</button><h3>Review draft</h3><input id="subject" class="subject" placeholder="Subject"><textarea id="body"></textarea></div></div><div class="panel" style="margin-top:14px"><h3>Recent outreach</h3><div id="olist"></div></div></section>
<section id="campaigns" class="view"><div class="hero"><div><div class="kicker">CAMPAIGN AUTOMATION</div><h2>Build approved, compliant email and text sequences.</h2><p>Create targeted campaigns, preview recipients, schedule delivery, enforce throttling and quiet hours, and automatically suppress opt-outs. Live sending activates only when provider credentials are configured.</p></div><span class="pill" id="campaignMode">Approval mode</span></div><div class="campaign-layout"><div class="panel"><h3>Create campaign</h3><label>Campaign name<input id="campName" class="full" placeholder="Example: Carolinas VA Scenario Support"></label><div class="formgrid"><label>Channel<select id="campChannel"><option>Email</option><option>SMS</option></select></label><label>Minimum score<input id="campScore" type="number" min="0" max="100" value="70"></label><label>State<select id="campState"><option value="">All states</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select></label><label>Status<select id="campStatus"><option value="">Any status</option><option>New</option><option>Contacted</option><option>Replied</option><option>Meeting</option></select></label><label>Send date/time<input id="campSchedule" type="datetime-local"></label><label>Daily send limit<input id="campLimit" type="number" min="1" max="500" value="50"></label></div><label>Email subject<input id="campSubject" class="full" placeholder="A quick resource for {{company}}"></label><label>Message body<textarea id="campBody" placeholder="Hi {{first_name}},

I’m Clay with Union Home Mortgage...

Reply STOP to opt out of texts."></textarea></label><p class="contact-note">Available fields: {{first_name}}, {{full_name}}, {{company}}, {{city}}, {{state}}, {{specialties}}. SMS recipients must have recorded consent.</p><div class="contact-tools"><button class="btn" id="previewCampaign">Preview audience</button><button class="btn primary" id="saveCampaign">Save & queue</button></div><div id="campaignPreview" class="roster-note"></div></div><div class="panel"><div class="profile-head"><div><h3>Campaign queue</h3><p class="muted">Paused campaigns never send. Processing can be triggered here or by a scheduled Render cron job.</p></div><button class="btn" id="processCampaigns">Process due queue</button></div><div id="campaignList"></div></div></div></section><section id="pipeline" class="view"><div class="hero"><div><div class="kicker">PIPELINE CONTROL</div><h2>Move prospects from discovery to approved account.</h2><p>Every status change updates the executive view and preserves a consistent sales process.</p></div><span class="pill">5-stage workflow</span></div><div id="board" class="board" style="margin-top:14px"></div></section><section id="followups" class="view"><div class="hero"><div><div class="kicker">FOLLOW-UP CENTER</div><h2>Never lose the next action.</h2><p>Relationship notes with follow-up dates are organized by urgency so the most important conversations stay visible.</p></div><button class="btn primary" onclick="show('prospects')">Open prospects</button></div><div class="metrics"><div class="metric"><span>Overdue</span><strong id="fo">0</strong></div><div class="metric"><span>Due today</span><strong id="ft">0</strong></div><div class="metric"><span>Next 7 days</span><strong id="fw">0</strong></div><div class="metric"><span>Unscheduled notes</span><strong id="fu">0</strong></div></div><div class="panel"><div id="followList"></div></div></section>

<section id="territory" class="view"><div class="hero"><div><div class="kicker">TERRITORY INTELLIGENCE</div><h2>See where broker opportunity is concentrated.</h2><p>Coverage by state and metro helps account executives prioritize travel, identify white space, and balance prospecting effort.</p></div><span class="pill">Public-web prospect coverage</span></div><div class="metrics"><div class="metric"><span>States covered</span><strong id="ts">0</strong></div><div class="metric"><span>Core Carolinas prospects</span><strong id="tc">0</strong></div><div class="metric"><span>Top metro concentration</span><strong id="tm">—</strong></div><div class="metric"><span>High-priority territories</span><strong id="th">0</strong></div></div><div class="grid"><div class="panel"><h3>State coverage map</h3><p class="muted">Tile-map view of the current prospect footprint. Darker fill indicates more discovered companies.</p><div id="stateMap" class="state-map"></div></div><div class="panel"><h3>Metro opportunity</h3><div id="metros" class="bars"></div><h3 style="margin-top:24px">Coverage gaps</h3><div id="gaps" class="activity"></div></div></div></section>
<section id="boss" class="view"><div class="hero exec"><div><div class="kicker">EXECUTIVE DEMO VIEW</div><h2>Broker Development Intelligence</h2><p>A presentation-ready summary of prospecting activity, account quality, product alignment, territory coverage, and pipeline momentum.</p><div class="value-story"><div><b>Find faster</b><span class="muted">Consolidates compliant public-web prospect discovery.</span></div><div><b>Prioritize smarter</b><span class="muted">Scores fit, growth potential, and recommended product angles.</span></div><div><b>Act consistently</b><span class="muted">Turns intelligence into outreach and pipeline action.</span></div></div></div><button class="btn primary" onclick="window.print()">Print / Save PDF</button></div><div class="metrics"><div class="metric"><span>Active prospects</span><strong id="bt">0</strong></div><div class="metric"><span>High priority</span><strong id="bh">0</strong></div><div class="metric"><span>Meetings scheduled</span><strong id="bm">0</strong></div><div class="metric"><span>Weighted opportunity index</span><strong id="bi">0</strong></div></div><div class="grid"><div class="panel"><h3>Pipeline health</h3><div id="bossPipeline" class="bars"></div></div><div class="panel"><h3>Product opportunity mix</h3><div id="bossProducts" class="bars"></div></div></div><div class="panel" style="margin-top:14px"><div class="profile-head"><div><h3>Top strategic accounts</h3><p class="muted">Highest-scoring prospects currently requiring action.</p></div><span class="pill">Union Home Mortgage Demo</span></div><div id="bossTop"></div></div></section>
<section id="integrations" class="view"><div class="int"><div class="panel integration"><b>✉ Gmail</b><p>Future OAuth draft creation and reply tracking.</p><input type="checkbox" data-key="gmail_connected"></div><div class="panel integration"><b>H HubSpot</b><p>Future prospect and lifecycle synchronization.</p><input type="checkbox" data-key="hubspot_connected"></div><div class="panel integration"><b>N Licensing feed</b><p>Future authorized broker-data import adapter.</p><input type="checkbox" data-key="nmls_source_configured"></div></div><div class="panel" style="margin-top:14px;color:var(--m)"><b>Demo safety:</b> connection toggles store flags only. No passwords, tokens, or paid-data credentials are stored. Live research and integrations require approved data sources and credentials.</div></section>
</main></div><input type="file" id="file" accept=".csv" hidden>
<dialog id="dlg"><form id="form"><h3>Add Prospect</h3><div class="formgrid"><label>Company<input name="company" required></label><label>Owner<input name="owner"></label><label>City<input name="city"></label><label>State<input name="state" maxlength="2"></label><label>Signal<select name="signal"><option>Newly Licensed</option><option>Team Growth</option><option>VA/FHA Fit</option><option>Manual</option></select></label><label>Team size<input name="team" type="number"></label><label>Email<input name="email" type="email"></label><label>Phone<input name="phone"></label><label>Website<input name="website"></label><label>NMLS<input name="nmls"></label><label>Specialties<input name="specialties" placeholder="VA, FHA, DPA"></label><label>License type<input name="license_type" placeholder="Mortgage broker / lender-broker"></label><label>Source name<input name="source_name" placeholder="State regulator, company website, authorized vendor"></label><label>Source URL<input name="source_url" type="url"></label><label>Verification status<select name="verification_status"><option>Needs verification</option><option>Verified licensed company</option><option>Verified mortgage broker</option><option>Verified lender/broker combined</option></select></label><label>Verified date<input name="verified_at" type="date"></label><label>Verification notes<input name="verification_notes"></label><label>Hiring?<select name="hiring"><option value="0">No / Unknown</option><option value="1">Yes</option></select></label><label><input name="authorized_use" type="checkbox" value="1" required> I am authorized to store and use this record</label></div><button class="btn primary full" style="margin-top:14px">Save & score</button></form></dialog>
<dialog id="importDlg"><form id="importForm"><div class="profile-head"><div><div class="kicker">COMPLIANT DATA INGESTION</div><h3>Import regulator, CRM, or approved-vendor data</h3></div><button type="button" class="btn" onclick="document.querySelector('#importDlg').close()">Close</button></div><p class="muted">BrokerBeacon detects common column names, previews the file, validates supported states, and deduplicates by NMLS ID or company/location.</p><label>CSV file<input id="importFile" name="file" type="file" accept=".csv,text/csv" required class="full"></label><div class="formgrid"><label>Default source name<input id="defaultSource" placeholder="Example: SC DCA licensee export"></label><label>Default source URL<input id="defaultSourceUrl" type="url" placeholder="Official regulator or approved source"></label><label>Default verification status<select id="defaultVerify"><option>Needs verification</option><option>Verified licensed company</option><option>Verified mortgage broker</option><option>Verified lender/broker combined</option></select></label><label>Default license type<input id="defaultLicense" placeholder="Mortgage broker"></label></div><label style="padding:12px;border:1px solid var(--l);border-radius:10px;background:#ffffff06"><input id="importAuthorized" type="checkbox" required> I confirm this file was obtained lawfully and I am authorized to store and use it for this business purpose.</label><div class="actions" style="margin:14px 0"><button type="button" class="btn" id="previewImport">Preview & validate</button><button type="submit" class="btn primary">Import approved rows</button><a class="btn" href="/api/import/template">Download template</a></div><div id="importPreview" class="panel" style="display:none;max-height:320px;overflow:auto"></div></form></dialog>
<dialog id="profile"><div class="profile-head"><div><div class="kicker">BROKER INTELLIGENCE PROFILE</div><h2 id="pc"></h2><div id="ploc" class="muted"></div></div><button class="btn" onclick="$('#profile').close()">Close</button></div><div id="ptags" style="margin:12px 0"></div>
<div class="contact-card">
  <div class="profile-head"><div><div class="kicker">BUILT-IN CONTACT INFORMATION</div><h3 style="margin:5px 0">Reach this prospect</h3></div><span id="pcontactbadge" class="contact-badge">Contact ready</span></div>
  <div class="contact-line"><span>Primary contact</span><b id="pcontactname">—</b></div>
  <div class="contact-line"><span>Phone</span><b id="pphone">—</b></div>
  <div class="contact-line"><span>Email</span><b id="pemail">—</b></div>
  <div class="contact-actions" id="pcontactactions"></div>
</div>
<div id="scores" class="scoregrid"></div><div class="tabs"><button class="btn primary" data-tab="intel">Intelligence</button><button class="btn" data-tab="contacts">Contacts</button><button class="btn" data-tab="strategy">Sales strategy</button><button class="btn" data-tab="memory">Relationship memory</button></div><div id="intel" class="tabpane active"><div class="grid"><div class="panel"><h3>Copilot pre-call brief</h3><p id="psum" class="muted"></p><h3>Why this score</h3><ul id="preasons" class="explain"></ul><h3>Source & verification</h3><div id="psource" class="muted"></div></div><div class="panel"><h3>Recommended product fit</h3><div id="pproducts"></div><h3>Next best action</h3><div id="pnext" class="nextaction"></div></div></div></div><div id="contacts" class="tabpane"><div class="grid"><div class="panel"><div class="profile-head"><div><h3>Company team directory</h3><p class="muted">Separate sections for decision-makers, individual loan officers, and the company contact desk.</p></div><span id="contactCount" class="pill">0 people</span></div><div class="contact-search"><input id="contactSearch" placeholder="Search officer, NMLS, specialty, language, email, or phone"><button class="btn" id="refreshRoster">Review company website</button></div><div id="rosterStatus" class="roster-note"></div><div id="contactList" class="contact-list"></div><div id="candidatePanel" class="roster-section"></div></div><div class="panel"><h3>Add or update a loan officer</h3><div class="contact-form"><input type="hidden" id="contactId"><div class="formgrid"><label>Name<input id="contactName" placeholder="Loan officer or company contact desk"></label><label>Role<input id="contactRole" placeholder="Loan Officer, Broker/Owner, Branch Manager"></label><label>Email<input id="contactEmail" type="email"></label><label>Phone<input id="contactPhone"></label><label>Mobile<input id="contactMobile"></label><label>NMLS ID<input id="contactNmls"></label><label>Office location<input id="contactOffice"></label><label>Preferred communication<select id="contactPreferred"><option value="">Unknown</option><option>Call</option><option>Email</option><option>Text</option><option>LinkedIn</option></select></label><label class="wide-form">Specialties<input id="contactSpecialties" placeholder="VA, FHA, USDA, Jumbo, Non-QM, HELOC"></label><label class="wide-form">Languages<input id="contactLanguages" placeholder="English, Spanish"></label><label>LinkedIn / public profile<input id="contactLinkedin"></label><label>Source URL<input id="contactSource"></label><label>Last verified<input id="contactVerified" type="date"></label><label>Roster status<select id="contactRoster"><option>Publicly verified</option><option>Needs verification</option><option>Former / inactive</option></select></label></div><label><input id="contactPrimary" type="checkbox"> Primary contact</label><label><input id="contactDecision" type="checkbox"> Decision-maker</label><label><input id="contactSmsConsent" type="checkbox"> Documented consent to receive text messages</label><label>Notes<textarea id="contactNotes" style="min-height:90px"></textarea></label><div class="contact-tools"><button class="btn primary" id="saveContact">Save contact</button><button class="btn" id="clearContact" type="button">Clear</button></div><p class="contact-note">BrokerBeacon stages web discoveries for review. Approve only current public business information from the company’s own website.</p></div></div></div></div><div id="strategy" class="tabpane"><div class="grid"><div class="panel"><h3>Call opener</h3><textarea id="pcall" readonly></textarea></div><div class="panel"><h3>Likely objection & response</h3><p><b id="pobj"></b></p><p id="presp" class="muted"></p><button class="btn primary" id="profileOut">Build outreach</button></div></div></div><div id="memory" class="tabpane"><div class="panel"><h3>Add relationship memory</h3><div class="formgrid"><label>Type<select id="mtype"><option>Call note</option><option>Personal detail</option><option>Product interest</option><option>Follow-up</option></select></label><label>Follow-up date<input id="mdate" type="date"></label></div><textarea id="mnote" placeholder="Example: Interested in HELOCs; prefers text; reconnect after purchase season."></textarea><button class="btn primary" id="msave">Save memory</button><div id="mlist"></div></div></div></dialog><dialog id="actionDlg"><form id="actionForm"><div class="profile-head"><div><div class="kicker">LOG SALES ACTIVITY</div><h3 id="actionCompany">Prospect</h3></div><button type="button" class="btn" onclick="$('#actionDlg').close()">Close</button></div><input type="hidden" id="actionPid"><label>Activity type<select id="actionType" class="full"><option>Call</option><option>Email</option><option>LinkedIn</option><option>Meeting</option><option>Text</option></select></label><label>Outcome<select id="actionOutcome" class="full"><option>No answer</option><option>Left voicemail</option><option>Connected</option><option>Positive response</option><option>Meeting scheduled</option><option>Not interested</option></select></label><label>Notes<textarea id="actionNotes" style="min-height:110px" placeholder="What happened? Capture useful details for the next conversation."></textarea></label><label>Next follow-up<input id="actionFollow" type="date" class="full"></label><button class="btn primary full" type="submit">Save activity</button></form></dialog><div class="toast" id="toast"></div>
<script>
let P=[],draft=null,current=null;const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
async function api(u,o={}){let r=await fetch(u,{headers:{'Content-Type':'application/json',...(o.headers||{})},...o});let d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
function esc(x){return String(x??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function telHref(x){return 'tel:'+String(x||'').replace(/[^0-9+]/g,'')}
function mailHref(x){return 'mailto:'+String(x||'').trim()}
async function copyText(x){try{await navigator.clipboard.writeText(x);msg('Copied')}catch(e){msg('Copy failed')}}
function safeUrl(x){let s=String(x||'').trim();return s&&!/^https?:\/\//i.test(s)?'https://'+s:s}
function contactButtons(p,compact=false){let a=[];if(p.phone)a.push(`<a class="btn smallbtn" href="${telHref(p.phone)}">☎ ${compact?'Call':'Call '+esc(p.phone)}</a>`);if(p.email)a.push(`<a class="btn smallbtn" href="${mailHref(p.email)}">✉ ${compact?'Email':'Email'}</a>`);if(p.website)a.push(`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(safeUrl(p.website))}">↗ Website</a>`);return a.join(' ')}

function msg(x){let t=$('#toast');t.textContent=x;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
function show(v){$$('.view').forEach(x=>x.classList.toggle('active',x.id===v));$$('nav button').forEach(x=>x.classList.toggle('active',x.dataset.v===v));$('#title').textContent=v==='dashboard'?'Command Center':v[0].toUpperCase()+v.slice(1);if(v==='copilot'){copilotBrief()}if(v==='daily')dailyPlan();if(v==='pipeline')pipe();if(v==='followups')followups();if(v==='outreach')outreach();if(v==='campaigns')campaigns();if(v==='territory')territory();if(v==='boss')boss()}
$$('nav button').forEach(b=>b.onclick=()=>show(b.dataset.v));
async function copilotBrief(){let d=await api('/api/copilot/brief');$('#morningBrief').innerHTML=`<div class="briefline"><b>${esc(d.greeting)}</b><div class="muted">${esc(d.summary)}</div></div>`+d.highlights.map(x=>`<div class="briefline"><b>${esc(x.label)}</b><div class="muted">${esc(x.value)}</div></div>`).join('')+`<div class="briefline"><b>Recommended first move</b><div class="nextaction">${esc(d.first_move)}</div></div>`}
async function askCopilot(){let q=$('#copilotQuestion').value.trim();if(!q)return msg('Enter a question');$('#copilotAnswer').innerHTML='<div class="empty">Analyzing your database…</div>';try{let d=await api('/api/copilot/ask',{method:'POST',body:JSON.stringify({question:q})});$('#copilotAnswer').innerHTML=`<b>${esc(d.title)}</b><div class="confidence">${esc(d.scope)}</div><p>${esc(d.answer)}</p>`+(d.results||[]).map((x,i)=>`<div class="priority-card"><div class="orb" style="--s:${x.priority_score||x.score||0}">${x.priority_score||x.score||0}</div><div><b>${i+1}. ${esc(x.company)}</b><div class="reason">${esc(x.reason)}</div><div><span class="tag">${esc(x.city||'')}${x.state?', '+esc(x.state):''}</span><span class="tag">${esc(x.status||'')}</span></div></div><button class="btn smallbtn" onclick="profile(${x.id})">Open</button></div>`).join('');}catch(e){$('#copilotAnswer').textContent=e.message}}
$('#askCopilot').onclick=askCopilot;$('#copilotQuestion').onkeydown=e=>{if(e.key==='Enter')askCopilot()};$$('.copilotPrompt').forEach(b=>b.onclick=()=>{$('#copilotQuestion').value=b.textContent;askCopilot()});

async function load(){let q=new URLSearchParams({search:$('#search').value,state:$('#state').value,signal:$('#signal').value,status:$('#pstatus').value,min_score:$('#minscore').value});P=await api('/api/prospects?'+q);$('#rows').innerHTML=P.map(p=>`<tr><td><b>${esc(p.company)}</b><br><small>${esc(p.owner||'Primary contact not named')}</small></td><td class="contact-cell">${p.phone?`<a href="${telHref(p.phone)}">${esc(p.phone)}</a>`:''}${p.email?`<a href="${mailHref(p.email)}">${esc(p.email)}</a>`:''}${!p.phone&&!p.email?'<span class="contact-missing">Use company website</span>':''}<div>${contactButtons(p,true)}</div></td><td><span class="pill">${esc(p.signal)}</span></td><td>${esc(p.city||'')}, ${esc(p.state||'')}</td><td>${(p.product_fit||'').split(',').slice(0,2).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</td><td class="score">${p.score}</td><td><span class="pill">${esc(p.verification_status||'Needs verification')}</span></td><td>${esc(p.status)}</td><td><button class="btn smallbtn" onclick="profile(${p.id})">Intelligence</button></td></tr>`).join('');$('#op').innerHTML=P.map(p=>`<option value="${p.id}">${esc(p.company)}</option>`).join('')}
async function dash(){let d=await api('/api/dashboard');$('#mt').textContent=d.total;$('#ms').textContent=d.avg;$('#mq').textContent=d.queued;$('#mm').textContent=d.status.Meeting||0;$('#snapshot').innerHTML=['New','Contacted','Replied','Meeting','Approved'].map(x=>`<p>${x}<b style="float:right">${d.status[x]||0}</b></p>`).join('');$('#activity').innerHTML=d.activity.map(a=>`<div><b>${esc(a.action)}</b><br><small>${esc(a.detail||'')} · ${esc(a.created_at.replace('T',' '))}</small></div>`).join('')||'<div class=empty>No activity yet.</div>';$('#priority').innerHTML=d.priorities.map(p=>`<div class="priority-card"><div class="orb" style="--s:${p.score}">${p.score}</div><div><b>${esc(p.company)}</b><div class="reason">${esc(p.next_best_action)}</div><div>${(p.product_fit||'').split(',').slice(0,3).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</div></div><button class="btn smallbtn" onclick="profile(${p.id})">Open</button></div>`).join('')||'<div class=empty>Add or import prospects to begin.</div>'}
function personCard(c){return `<div class="person-card ${c.is_primary?'primary-contact':''}"><div class="person-top"><div><b>${esc(c.name||'Company Contact Desk')}</b>${c.is_decision_maker?' <span class="decision">DECISION-MAKER</span>':''}<div class="person-meta">${esc(c.role||'Contact')} ${c.is_primary?'· Primary':''} ${c.roster_status?`· ${esc(c.roster_status)}`:''}</div></div><div>${document.body.dataset.demo==='1'?'':`<button class="btn copybtn" onclick="editContact(${c.id})">Edit</button>`}</div></div><div class="officer-details">${c.nmls?`<div><small>NMLS</small>${esc(c.nmls)}</div>`:''}${c.office_location?`<div><small>Office</small>${esc(c.office_location)}</div>`:''}${c.specialties?`<div><small>Specialties</small>${esc(c.specialties)}</div>`:''}${c.languages?`<div><small>Languages</small>${esc(c.languages)}</div>`:''}${c.preferred_method?`<div><small>Preferred contact</small>${esc(c.preferred_method)}</div>`:''}${c.verified_at?`<div><small>Verified</small>${esc(c.verified_at)}</div>`:''}</div>${c.phone?`<div><a href="${telHref(c.phone)}">☎ ${esc(c.phone)}</a> <button class="btn copybtn" onclick="copyText('${esc(c.phone).replace(/'/g,"&#39;")}')">Copy</button></div>`:''}${c.mobile?`<div><a href="${telHref(c.mobile)}">📱 ${esc(c.mobile)}</a></div>`:''}${c.email?`<div><a href="${mailHref(c.email)}">✉ ${esc(c.email)}</a> <button class="btn copybtn" onclick="copyText('${esc(c.email).replace(/'/g,"&#39;")}')">Copy</button></div>`:''}<div class="contact-tools">${c.phone||c.mobile?`<a class="btn smallbtn" href="${telHref(c.mobile||c.phone)}">Call</a>`:''}${c.email?`<a class="btn smallbtn" href="${mailHref(c.email)}">Email</a>`:''}${c.linkedin_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(safeUrl(c.linkedin_url))}">Profile</a>`:''}${c.source_url?`<a class="source-link" target="_blank" rel="noopener" href="${esc(safeUrl(c.source_url))}">Verify source</a>`:''}<button class="btn smallbtn" onclick="buildOfficerOutreach(${c.id})">AI outreach</button></div>${c.notes?`<div class="contact-note">${esc(c.notes)}</div>`:''}</div>`}
function renderContacts(items){let q=($('#contactSearch')?.value||'').toLowerCase();let visible=items.filter(c=>!q||[c.name,c.role,c.email,c.phone,c.mobile,c.nmls,c.specialties,c.languages,c.office_location].join(' ').toLowerCase().includes(q));$('#contactCount').textContent=items.length+' person'+(items.length===1?'':'s');let groups=[['Decision-makers',visible.filter(c=>c.is_decision_maker)],['Loan officers',visible.filter(c=>!c.is_decision_maker&&!/desk|office|general/i.test((c.role||'')+' '+(c.name||'')))],['Company contact desk',visible.filter(c=>/desk|office|general/i.test((c.role||'')+' '+(c.name||'')))]];$('#contactList').innerHTML=groups.filter(g=>g[1].length).map(g=>`<section class="roster-section"><div class="roster-title"><h4>${g[0]}</h4><span class="pill">${g[1].length}</span></div>${g[1].map(personCard).join('')}</section>`).join('')||'<div class="empty">No matching contacts entered.</div>';let named=items.filter(c=>c.name&&c.name!=='Company Contact Desk').length;$('#rosterStatus').textContent=named?`${named} named team member${named===1?'':'s'} stored. Public rosters may be incomplete; use Review company website to stage newly published contacts.`:'No named loan officers are stored yet. Review the company website or add verified officers manually.'}
function buildOfficerOutreach(id){let c=(current.contacts||[]).find(x=>x.id===id);if(!c)return;$('#op').value=current.id;$('#ochannel').value=c.email?'Email':'Phone';build();show('outreach');$('#profile').close();msg('Outreach personalized for '+(c.name||'contact'))}
function renderCandidates(items){$('#candidatePanel').innerHTML=items.length?`<div class="roster-title"><h4>Website discoveries awaiting approval</h4><span class="pill">${items.length}</span></div>${items.map(c=>`<div class="candidate-card"><b>${esc(c.name||'Possible contact')}</b><div class="person-meta">${esc(c.role||'Public website discovery')}</div>${c.email?`<div>✉ ${esc(c.email)}</div>`:''}${c.phone?`<div>☎ ${esc(c.phone)}</div>`:''}<a class="source-link" target="_blank" href="${esc(safeUrl(c.source_url))}">Review source</a><div class="candidate-actions"><button class="btn primary smallbtn" onclick="approveCandidate(${c.id})">Approve</button><button class="btn smallbtn" onclick="rejectCandidate(${c.id})">Reject</button></div></div>`).join('')}`:''}
async function approveCandidate(id){await api('/api/contact-candidates/'+id+'/approve',{method:'POST'});await profile(current.id);msg('Contact approved')}
async function rejectCandidate(id){await api('/api/contact-candidates/'+id+'/reject',{method:'POST'});await loadCandidates();msg('Discovery rejected')}
async function loadCandidates(){if(!current)return;let x=await api('/api/prospects/'+current.id+'/contact-candidates');renderCandidates(x)}
function clearContactForm(){['contactId','contactName','contactRole','contactEmail','contactPhone','contactMobile','contactLinkedin','contactSource','contactVerified','contactNotes'].forEach(id=>$('#'+id).value='');$('#contactPrimary').checked=false;$('#contactDecision').checked=false;$('#contactSmsConsent').checked=false}
function editContact(id){let c=(current.contacts||[]).find(x=>x.id===id);if(!c)return;$('#contactId').value=c.id;$('#contactName').value=c.name||'';$('#contactRole').value=c.role||'';$('#contactEmail').value=c.email||'';$('#contactPhone').value=c.phone||'';$('#contactMobile').value=c.mobile||'';$('#contactNmls').value=c.nmls||'';$('#contactOffice').value=c.office_location||'';$('#contactSpecialties').value=c.specialties||'';$('#contactLanguages').value=c.languages||'';$('#contactPreferred').value=c.preferred_method||'';$('#contactRoster').value=c.roster_status||'Publicly verified';$('#contactLinkedin').value=c.linkedin_url||'';$('#contactSource').value=c.source_url||'';$('#contactVerified').value=c.verified_at||'';$('#contactNotes').value=c.notes||'';$('#contactPrimary').checked=!!c.is_primary;$('#contactDecision').checked=!!c.is_decision_maker;$('#contactSmsConsent').checked=!!c.sms_consent;document.querySelector('[data-tab="contacts"]').click()}
async function profile(id){let p=await api('/api/prospects/'+id);current=p;renderContacts(p.contacts||[]);clearContactForm();loadCandidates();$('#pc').textContent=p.company;$('#ploc').textContent=[p.owner,p.city,p.state,p.nmls?'NMLS '+p.nmls:'',p.verification_status,p.verified_at?'Verified '+p.verified_at:''].filter(Boolean).join(' · ');$('#ptags').innerHTML=[p.signal,p.status,p.license_type,p.source_name,p.hiring?'Hiring':''].filter(Boolean).map(x=>`<span class=tag>${esc(x)}</span>`).join('');
$('#pcontactname').textContent=p.owner||'Company contact desk';
$('#pphone').textContent=p.phone||'Not publicly listed';
$('#pemail').textContent=p.email||'Not publicly listed';
$('#pcontactactions').innerHTML=contactButtons(p)||'<span class="contact-missing">Open the source or company website to locate current contact information.</span>';
$('#pcontactbadge').textContent=(p.phone||p.email)?'Direct contact ready':'Website contact available';
$('#scores').innerHTML=[['Opportunity',p.score],['Growth',p.growth_score],['Government fit',p.gov_fit],['HELOC/Jumbo',p.niche_fit]].map(x=>`<div class=scorebox><span class=muted>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');$('#psum').textContent=p.ai_summary;$('#preasons').innerHTML=p.score_reasons.map(x=>`<li>${esc(x)}</li>`).join('');$('#psource').innerHTML=[p.source_name?'<b>Source:</b> '+esc(p.source_name):'',p.source_url?'<a class="btn smallbtn" target="_blank" rel="noopener" href="'+esc(p.source_url)+'">Open source</a>':'',p.nmls?'<a class="btn smallbtn" target="_blank" rel="noopener" href="https://www.nmlsconsumeraccess.org/">Verify in NMLS Consumer Access</a>':'',p.verification_notes?'<div style="margin-top:8px">'+esc(p.verification_notes)+'</div>':''].filter(Boolean).join(' ');$('#pproducts').innerHTML=p.product_fit.split(',').filter(Boolean).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('');$('#pnext').textContent=p.next_best_action;$('#pcall').value=p.call_opener;$('#pobj').textContent=p.likely_objection;$('#presp').textContent=p.objection_response;$('#profileOut').onclick=()=>{show('outreach');$('#op').value=p.id;$('#profile').close()};renderMemory(p.memories);$('#profile').showModal()}
function renderMemory(m){$('#mlist').innerHTML='<h3 style="margin-top:22px">Saved memory</h3>'+((m||[]).map(x=>`<div class=memory-item><b>${esc(x.note_type)}</b><br>${esc(x.note)}<br><small class=muted>${esc(x.created_at.replace('T',' '))}${x.follow_up_date?' · Follow up '+esc(x.follow_up_date):''}</small></div>`).join('')||'<div class=empty>No relationship memory yet.</div>')}
$$('[data-tab]').forEach(b=>b.onclick=()=>{$$('[data-tab]').forEach(x=>x.classList.toggle('primary',x===b));$$('.tabpane').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab))});
$('#msave').onclick=async()=>{if(!$('#mnote').value.trim())return msg('Enter a note');let m=await api('/api/prospects/'+current.id+'/memory',{method:'POST',body:JSON.stringify({note_type:$('#mtype').value,note:$('#mnote').value,follow_up_date:$('#mdate').value})});$('#mnote').value='';$('#mdate').value='';renderMemory(m);msg('Memory saved');dash()}
async function pipe(){P=await api('/api/prospects');let S=['New','Contacted','Replied','Meeting','Approved'];$('#board').innerHTML=S.map(s=>`<div class=col><h3>${s}</h3>${P.filter(p=>p.status===s).map(p=>`<div class=card><b>${esc(p.company)}</b><p><small>${esc(p.owner||'')} · Score ${p.score}</small></p><select class=full ${document.body.dataset.demo==='1'?'disabled title="Read-only demo"':'onchange="status(${p.id},this.value)"'}>${S.map(x=>`<option ${x===p.status?'selected':''}>${x}</option>`).join('')}</select></div>`).join('')}</div>`).join('')}
async function status(id,s){await api('/api/status/'+id,{method:'POST',body:JSON.stringify({status:s})});msg('Pipeline updated');load();dash();pipe()}
$('#gen').onclick=async()=>{let d=await api('/api/generate',{method:'POST',body:JSON.stringify({id:+$('#op').value,channel:$('#channel').value,angle:$('#angle').value})});draft=d.id;$('#subject').value=d.subject;$('#subject').style.display=$('#channel').value==='Email'?'block':'none';$('#body').value=d.body;$('#queue').disabled=false;outreach()}
$('#queue').onclick=async()=>{await api('/api/queue/'+draft,{method:'POST',body:'{}'});msg('Queued');$('#queue').disabled=true;load();dash();outreach()}
async function outreach(){let d=await api('/api/outreach');$('#olist').innerHTML=d.length?d.map(x=>`<p><b>${esc(x.company)}</b> · ${esc(x.channel)} · ${esc(x.status)}</p>`).join(''):'No drafts yet.'}
$('#contactSearch').oninput=()=>current&&renderContacts(current.contacts||[]);$('#refreshRoster').onclick=async()=>{if(!current)return;$('#refreshRoster').disabled=true;$('#refreshRoster').textContent='Checking website…';try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});renderCandidates(r.candidates||[]);msg(r.message)}finally{$('#refreshRoster').disabled=false;$('#refreshRoster').textContent='Review company website'}};$('#clearContact').onclick=clearContactForm;$('#saveContact').onclick=async e=>{e.preventDefault();if(!current)return;let d={id:+($('#contactId').value||0),name:$('#contactName').value,role:$('#contactRole').value,email:$('#contactEmail').value,phone:$('#contactPhone').value,mobile:$('#contactMobile').value,nmls:$('#contactNmls').value,office_location:$('#contactOffice').value,specialties:$('#contactSpecialties').value,languages:$('#contactLanguages').value,preferred_method:$('#contactPreferred').value,roster_status:$('#contactRoster').value,linkedin_url:$('#contactLinkedin').value,source_url:$('#contactSource').value,verified_at:$('#contactVerified').value,notes:$('#contactNotes').value,is_primary:$('#contactPrimary').checked,is_decision_maker:$('#contactDecision').checked,sms_consent:$('#contactSmsConsent').checked};let r=await api('/api/prospects/'+current.id+'/contacts',{method:'POST',body:JSON.stringify(d)});current.contacts=r;renderContacts(r);clearContactForm();msg('Contact saved');load()};
$('#search').oninput=load;$('#state').onchange=load;$('#signal').onchange=load;$('#pstatus').onchange=load;$('#minscore').onchange=load;$('#add').onclick=()=>$('#dlg').showModal();$('#form').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.target));await api('/api/prospects',{method:'POST',body:JSON.stringify(d)});$('#dlg').close();e.target.reset();msg('Prospect added and scored');load();dash()}
$('#import').onclick=()=>$('#importDlg').showModal();
async function previewImport(){let file=$('#importFile').files[0];if(!file){msg('Choose a CSV file first');return}let f=new FormData();f.append('file',file);let r=await fetch('/api/import/preview',{method:'POST',body:f}),d=await r.json();if(!r.ok){msg(d.error||'Preview failed');return}let box=$('#importPreview');box.style.display='block';box.innerHTML='<h4>Preview</h4><p class=muted>'+d.total_rows+' rows · '+d.valid_rows+' valid · '+d.invalid_rows+' need attention</p><p><b>Detected mapping:</b> '+Object.entries(d.mapping).filter(x=>x[1]).map(x=>x[0]+' ← '+x[1]).join(' · ')+'</p><table><thead><tr><th>Row</th><th>Company</th><th>State</th><th>NMLS</th><th>Result</th></tr></thead><tbody>'+d.sample.map(x=>'<tr><td>'+x.row+'</td><td>'+esc(x.company||'')+'</td><td>'+esc(x.state||'')+'</td><td>'+esc(x.nmls||'')+'</td><td>'+(x.errors.length?'<span style="color:var(--r)">'+esc(x.errors.join('; '))+'</span>':'<span style="color:var(--g)">Ready</span>')+'</td></tr>').join('')+'</tbody></table>'}
$('#previewImport').onclick=previewImport;
$('#importForm').onsubmit=async e=>{e.preventDefault();if(!$('#importAuthorized').checked){msg('Authorization confirmation is required');return}let file=$('#importFile').files[0];if(!file){msg('Choose a CSV file first');return}let f=new FormData();f.append('file',file);f.append('authorized_use','yes');f.append('default_source_name',$('#defaultSource').value);f.append('default_source_url',$('#defaultSourceUrl').value);f.append('default_verification_status',$('#defaultVerify').value);f.append('default_license_type',$('#defaultLicense').value);let r=await fetch('/api/import',{method:'POST',body:f}),d=await r.json();if(!r.ok){msg(d.error||'Import failed');return}msg(d.imported+' new · '+d.updated+' updated · '+d.skipped+' skipped');let box=$('#importPreview');box.style.display='block';box.innerHTML='<h4>Import complete</h4><p>'+d.imported+' new prospects, '+d.updated+' updated, '+d.skipped+' skipped.</p>'+(d.report_url?'<a class="btn" href="'+d.report_url+'">Download import report</a>':'');load();dash()};

async function dailyPlan(){let d=await api('/api/daily-plan');$('#dcalls').textContent=d.metrics.calls_today;$('#demails').textContent=d.metrics.emails_today;$('#dconvos').textContent=d.metrics.conversations_week;$('#dmeetings').textContent=d.metrics.meetings_week;$('#goalPct').textContent=d.goal.percent+'%';$('#goalring').style.setProperty('--goal',d.goal.percent);$('#goalText').textContent=d.goal.completed+' of '+d.goal.target+' actions completed today';$('#dailyQueue').innerHTML=d.actions.length?d.actions.map((x,i)=>`<div class="action-row"><div class="rank">#${i+1}</div><div><b>${esc(x.company)}</b> <span class="activity-chip">${esc(x.recommended_channel)}</span><div class="reason">${esc(x.reason)}</div><small class="muted">${esc(x.city||'')}, ${esc(x.state||'')} · Score ${x.score} · ${esc(x.status)}</small>${x.stale_days>=7?`<div class="stale">No logged activity in ${x.stale_days} days</div>`:''}</div><div>${x.phone?`<a class="btn smallbtn" href="${telHref(x.phone)}">Call</a>`:''}${x.email?` <a class="btn smallbtn" href="${mailHref(x.email)}">Email</a>`:''} <button class="btn smallbtn" onclick="openAction(${x.id},'${esc(x.company).replace(/'/g,"&#39;")}','${x.recommended_channel}')">Log action</button> <button class="btn smallbtn" onclick="profile(${x.id})">Open</button></div></div>`).join(''):'<div class=empty>No unfinished actions. Great work.</div>';$('#salesTimeline').innerHTML=d.recent.length?d.recent.map(x=>`<div class="timeline-item"><b>${esc(x.action_type)} · ${esc(x.company)}</b><div>${esc(x.outcome||'')}</div><small class="muted">${esc(x.created_at.replace('T',' '))}</small></div>`).join(''):'<div class=empty>No sales activity logged yet.</div>'}
function openAction(id,company,type='Call'){$('#actionPid').value=id;$('#actionCompany').textContent=company;$('#actionType').value=['Call','Email','LinkedIn','Meeting','Text'].includes(type)?type:'Call';$('#actionDlg').showModal()}
$('#actionForm').onsubmit=async e=>{e.preventDefault();await api('/api/sales-actions',{method:'POST',body:JSON.stringify({prospect_id:+$('#actionPid').value,action_type:$('#actionType').value,outcome:$('#actionOutcome').value,notes:$('#actionNotes').value,follow_up_date:$('#actionFollow').value})});$('#actionDlg').close();e.target.reset();msg('Sales activity logged');dailyPlan();dash();load()}

async function followups(){let d=await api('/api/followups');$('#fo').textContent=d.counts.overdue;$('#ft').textContent=d.counts.today;$('#fw').textContent=d.counts.week;$('#fu').textContent=d.counts.unscheduled;$('#followList').innerHTML=d.items.length?d.items.map(x=>`<div class=priority-card><div class=orb style="--s:${x.score||50}">${x.score||'—'}</div><div><b>${esc(x.company)}</b><div class=reason>${esc(x.note_type)} · ${esc(x.note)}</div><small class=muted>${x.follow_up_date?esc(x.bucket)+' · '+esc(x.follow_up_date):'No date assigned'}</small></div><div><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Open</button> ${document.body.dataset.demo==='1'?'':`<button class="btn smallbtn" onclick="completeFollowup(${x.id})">Complete</button>`}</div></div>`).join(''):'<div class=empty>No follow-ups are currently scheduled.</div>'}async function completeFollowup(id){await api('/api/followups/'+id+'/complete',{method:'POST'});msg('Follow-up completed');followups();dash()}
async function territory(){let d=await api('/api/territory');$('#ts').textContent=d.states.length;$('#tc').textContent=d.carolinas;$('#tm').textContent=d.metros.length?d.metros[0].name:'—';$('#th').textContent=d.high_priority_states;let max=Math.max(1,...d.states.map(x=>x.count));$('#stateMap').innerHTML=d.states.map(x=>`<div class="state-tile" style="grid-area:${x.state.toLowerCase()};--heat:${Math.max(.12,x.count/max*.72)}"><b>${esc(x.state)}</b><strong>${x.count}</strong><span>prospects · avg ${x.avg_score}</span></div>`).join('');let mm=Math.max(1,...d.metros.map(x=>x.count));$('#metros').innerHTML=d.metros.map(x=>`<div class=barrow><span>${esc(x.name)}</span><div class=bartrack><div class=barfill style="width:${x.count/mm*100}%"></div></div><b>${x.count}</b></div>`).join('');$('#gaps').innerHTML=d.gaps.map(x=>`<div><b>${esc(x)}</b><br><small>Recommended next discovery market</small></div>`).join('')}


async function missionControl(){let d=await api('/api/mission-control');$('#mcCalls').textContent=d.metrics.priority_calls;$('#mcNew').textContent=d.metrics.new_alerts;$('#mcRisk').textContent=d.metrics.at_risk;$('#mcMeetings').textContent=d.metrics.meetings_week;$('#mcPriorities').innerHTML=d.priorities.map(p=>`<div class="priority-card"><div class="orb" style="--s:${p.score}">${p.score}</div><div><b>${esc(p.company)}</b><div class="reason">${esc(p.reason)}</div><small class="muted">${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.status)}</small></div><button class="btn smallbtn" onclick="profile(${p.id})">Open</button></div>`).join('')||'<div class="empty">No urgent priorities.</div>';$('#mcBrief').textContent=d.brief;$('#mcAlerts').innerHTML=d.new_alerts.map(x=>`<div><b>${esc(x.company)}</b><br><small>${esc(x.signal||'New prospect')} · Score ${x.score}</small></div>`).join('')||'<div class="empty">No new alerts.</div>';$('#mcAtRisk').innerHTML=d.at_risk.map(x=>`<div><b>${esc(x.company)}</b><br><small>${x.days_inactive} days without activity · <a href="#" onclick="profile(${x.id});return false">Open</a></small></div>`).join('')||'<div class="empty">No relationships at risk.</div>';let mx=Math.max(1,...d.products.map(x=>x.count));$('#mcProducts').innerHTML=d.products.map(x=>`<div class="barrow"><span>${esc(x.name)}</span><div class="bartrack"><div class="barfill" style="width:${x.count/mx*100}%"></div></div><b>${x.count}</b></div>`).join('');$('#mcGoals').innerHTML=`<div class="goalring" style="--goal:${d.goals.percent}"><div><span><strong>${d.goals.percent}%</strong><br><small>${d.goals.completed}/${d.goals.target}</small></span></div></div><p class="muted" style="text-align:center">Weekly selling actions</p>`;$('#mcCampaigns').innerHTML=`<p>Active <b style="float:right">${d.campaigns.active}</b></p><p>Queued <b style="float:right">${d.campaigns.queued}</b></p><p>Sent <b style="float:right">${d.campaigns.sent}</b></p><p>Failed <b style="float:right">${d.campaigns.failed}</b></p>`}
function campaignPayload(){return{name:$('#campName').value,channel:$('#campChannel').value,min_score:+$('#campScore').value,state:$('#campState').value,status_filter:$('#campStatus').value,scheduled_at:$('#campSchedule').value,daily_limit:+$('#campLimit').value,subject:$('#campSubject').value,body:$('#campBody').value}}
async function previewCampaign(){let d=await api('/api/campaigns/preview',{method:'POST',body:JSON.stringify(campaignPayload())});$('#campaignPreview').innerHTML=`<b>${d.eligible} eligible contacts</b> · ${d.suppressed} suppressed or missing consent/contact route.<br>${d.sample.map(x=>esc(x.name)+' — '+esc(x.company)).join('<br>')||'No eligible recipients.'}`}
async function campaigns(){let d=await api('/api/campaigns');$('#campaignMode').textContent=d.live_email||d.live_sms?'Live provider configured':'Approval mode';$('#campaignList').innerHTML=d.items.length?d.items.map(x=>`<div class="campaign-row"><div class="profile-head"><div><b>${esc(x.name)}</b> <span class="pill">${esc(x.channel)}</span><div class="mini">${esc(x.status)} · Scheduled ${esc((x.scheduled_at||'Immediately').replace('T',' '))}</div></div><div><button class="btn smallbtn" onclick="toggleCampaign(${x.id},'${x.status==='Paused'?'Active':'Paused'}')">${x.status==='Paused'?'Resume':'Pause'}</button></div></div><div class="campaign-stats"><div><b>${x.total}</b><small>Total</small></div><div><b>${x.queued}</b><small>Queued</small></div><div><b>${x.sent}</b><small>Sent</small></div><div><b>${x.failed}</b><small>Failed</small></div><div><b>${x.suppressed}</b><small>Suppressed</small></div></div></div>`).join(''):'<div class="empty">No campaigns created yet.</div>'}
async function toggleCampaign(id,status){await api('/api/campaigns/'+id+'/status',{method:'POST',body:JSON.stringify({status})});msg('Campaign updated');campaigns();missionControl()}
$('#previewCampaign').onclick=previewCampaign;$('#saveCampaign').onclick=async()=>{let d=await api('/api/campaigns',{method:'POST',body:JSON.stringify(campaignPayload())});msg(`Campaign queued for ${d.queued} contacts`);campaigns();missionControl()};$('#processCampaigns').onclick=async()=>{let d=await api('/api/campaigns/process',{method:'POST'});msg(`${d.sent} sent · ${d.failed} failed · ${d.skipped} skipped`);campaigns();missionControl()};

async function boss(){let d=await api('/api/executive');$('#bt').textContent=d.total;$('#bh').textContent=d.high_priority;$('#bm').textContent=d.meetings;$('#bi').textContent=d.opportunity_index;let max=Math.max(1,...Object.values(d.pipeline));$('#bossPipeline').innerHTML=Object.entries(d.pipeline).map(([k,v])=>`<div class=barrow><span>${esc(k)}</span><div class=bartrack><div class=barfill style="width:${v/max*100}%"></div></div><b>${v}</b></div>`).join('');$('#bossProducts').innerHTML=Object.entries(d.products).map(([k,v])=>`<div class=barrow><span>${esc(k)}</span><div class=bartrack><div class=barfill style="width:${v}%"></div></div><b>${v}%</b></div>`).join('');$('#bossTop').innerHTML=d.top.map((p,i)=>`<div class=top-account><div class=rank>#${i+1}</div><div><b>${esc(p.company)}</b><div class=mini>${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.next_best_action||'')}</div></div><div>${(p.product_fit||'').split(',').slice(0,2).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</div><div class=score>${p.score}/100</div></div>`).join('')||'<div class=empty>No prospects yet.</div>'}
async function ints(){let d=await api('/api/integrations');$$('[data-key]').forEach(x=>{x.checked=d[x.dataset.key];x.onchange=()=>api('/api/integrations',{method:'POST',body:JSON.stringify({key:x.dataset.key,value:x.checked})})})}
if(document.body.dataset.demo==='1'){
  const banner=document.createElement('div');banner.className='demo-banner';banner.innerHTML='<b>Executive demo mode</b> · Explore every workflow. Data-changing actions are disabled.';document.querySelector('main').insertBefore(banner,document.querySelector('.top').nextSibling);
  const badge=document.createElement('span');badge.className='pill';badge.textContent='FULL-FEATURE READ-ONLY DEMO';document.querySelector('.top small').after(badge);
  document.querySelectorAll('#import,#add,#queue,#gen,#msave,#form button[type="submit"],#importForm button[type="submit"],#actionForm button[type="submit"],#saveContact,[data-key]').forEach(x=>{x.disabled=true;x.classList.add('demo-lock');x.title='Disabled in executive demo mode'});
  document.querySelectorAll('#subject,#body,#mnote,#mdate,#mtype,#actionType,#actionOutcome,#actionNotes,#actionFollow').forEach(x=>{x.disabled=true;x.classList.add('demo-lock')});
  document.querySelectorAll('.actions a').forEach(x=>x.style.display='none');
  show('dashboard');
}
load();dash();outreach();followups();dailyPlan();ints();missionControl();
</script></body></html>'''

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def cols(c, table):
    return {r[1] for r in c.execute(f"pragma table_info({table})")}

def addcol(c, table, definition):
    name = definition.split()[0]
    if name not in cols(c, table):
        c.execute(f"alter table {table} add column {definition}")

def init():
    with db() as c:
        c.executescript("""
        create table if not exists prospects(id integer primary key,company text,owner text,city text,state text,signal text,team int,score int,email text,phone text,status text default 'New',source text,created_at text);
        create table if not exists outreach(id integer primary key,prospect_id int,channel text,subject text,body text,status text,created_at text);
        create table if not exists activity(id integer primary key,action text,detail text,created_at text);
        create table if not exists integrations(key text primary key,value text);
        create table if not exists memories(id integer primary key,prospect_id int,note_type text,note text,follow_up_date text,created_at text);
        create table if not exists sales_actions(id integer primary key,prospect_id int,action_type text,outcome text,notes text,follow_up_date text,created_at text);
        create table if not exists contacts(id integer primary key,prospect_id integer not null,name text,role text,email text,phone text,mobile text,linkedin_url text,source_url text,verified_at text,notes text,is_primary integer default 0,is_decision_maker integer default 0,created_at text,updated_at text);
        create table if not exists contact_candidates(id integer primary key,prospect_id integer not null,name text,role text,email text,phone text,source_url text,raw_context text,status text default 'Pending',created_at text);
        create table if not exists campaigns(id integer primary key,name text,channel text,subject text,body text,min_score integer default 0,state text,status_filter text,scheduled_at text,daily_limit integer default 50,status text default 'Active',created_at text,updated_at text);
        create table if not exists campaign_recipients(id integer primary key,campaign_id integer,prospect_id integer,contact_id integer,destination text,rendered_subject text,rendered_body text,status text default 'Queued',scheduled_at text,sent_at text,error text,provider_id text,created_at text);
        create table if not exists suppressions(id integer primary key,channel text,destination text,reason text,created_at text,unique(channel,destination));

        """)
        for definition in [
            "website text default ''", "nmls text default ''", "specialties text default ''",
            "hiring integer default 0", "growth_score integer default 50", "gov_fit integer default 50",
            "niche_fit integer default 50", "product_fit text default ''", "ai_summary text default ''",
            "score_reasons text default '[]'", "next_best_action text default ''", "call_opener text default ''",
            "likely_objection text default ''", "objection_response text default ''", "updated_at text default ''",
            "source_name text default ''", "source_url text default ''", "verification_status text default 'Needs verification'",
            "verified_at text default ''", "license_type text default ''", "verification_notes text default ''", "authorized_use integer default 0"
        ]:
            addcol(c, "prospects", definition)
        for definition in [
            "nmls text default ''", "specialties text default ''", "languages text default ''",
            "office_location text default ''", "preferred_method text default ''", "birthday text default ''",
            "first_contact_date text default ''", "last_call_at text default ''", "last_email_at text default ''", "sms_consent integer default 0", "email_opt_out integer default 0", "sms_opt_out integer default 0",
            "last_meeting_at text default ''", "roster_status text default 'Publicly verified'", "source_name text default ''"
        ]:
            addcol(c, "contacts", definition)
        # No fictional seed records. Import only data you are authorized to use.
        ids = [r[0] for r in c.execute("select id from prospects")]
    for pid in ids:
        rescore(pid)

def log(action, detail=""):
    with db() as c:
        c.execute("insert into activity(action,detail,created_at) values(?,?,?)", (action, detail, NOW()))

def analyze(p):
    signal = (p.get("signal") or "").lower()
    specs = (p.get("specialties") or "").lower()
    team = int(p.get("team") or 0)
    hiring = bool(int(p.get("hiring") or 0))
    website = bool(p.get("website"))
    reasons = []
    growth = 45
    if "newly" in signal: growth += 25; reasons.append("Recently licensed activity creates a strong window for an early lender relationship.")
    if "growth" in signal: growth += 22; reasons.append("Team-growth activity suggests increasing production capacity and lender demand.")
    if team >= 8: growth += 18; reasons.append(f"A team of approximately {team} can support meaningful account potential.")
    elif team >= 4: growth += 10; reasons.append(f"A team of approximately {team} indicates room for repeat volume.")
    if hiring: growth += 15; reasons.append("Hiring activity is a useful signal of expansion.")
    if website: growth += 5; reasons.append("An active web presence improves outreach confidence and personalization.")
    gov = 42
    if any(x in specs for x in ["va","fha","usda","government"]): gov += 40; reasons.append("Publicly entered specialties align with VA/FHA/USDA scenario support.")
    if "va/fha" in signal: gov += 30; reasons.append("The prospect was specifically flagged for government-loan fit.")
    if (p.get("state") or "") in ["NC","SC"]: gov += 8; reasons.append("The prospect is located in a core Carolinas market for local DPA conversations.")
    niche = 40
    if any(x in specs for x in ["heloc","jumbo","non-qm","bank statement","dscr"]): niche += 42; reasons.append("Entered specialties indicate a strong fit for HELOC or niche-product conversations.")
    if team >= 6: niche += 10
    growth, gov, niche = min(growth,100), min(gov,100), min(niche,100)
    score = round(growth*.42 + gov*.34 + niche*.24)
    if "newly" in signal: score = min(100, score+5)
    products=[]
    if gov >= 65: products += ["VA", "FHA", "USDA", "Local DPA"]
    if niche >= 65: products += ["HELOC", "Jumbo / niche scenarios"]
    products += ["Conventional A-paper", "Lower-FICO government support", "Fast scenario review"]
    products = list(dict.fromkeys(products))
    owner = (p.get("owner") or "the team").split()[0]
    summary = f"{p.get('company')} appears to be a {('growing ' if growth>=70 else '')}independent mortgage prospect in {p.get('city') or 'its local market'}. "
    summary += f"Its strongest current opportunity is {'government and DPA support' if gov>=niche else 'HELOC, jumbo, and niche-product support'}. "
    summary += f"The account is best approached as a helpful secondary lender rather than as a request to replace existing relationships."
    next_action = "Call first and lead with a quick scenario-support introduction." if score >= 85 else "Send a personalized introduction, then follow up by phone within two business days." if score >= 70 else "Add one more research detail before beginning outreach."
    call = f"Hi {owner}, this is Clay with Union Home Mortgage. I was looking at {p.get('company')} and noticed {p.get('signal','recent activity').lower()} in {p.get('city') or 'your market'}. We help independent brokers with {', '.join(products[:3])}, and I wanted to introduce myself as a quick second set of eyes when a scenario gets difficult."
    objection = "We already have enough lenders."
    response = "I completely understand. I am not asking you to replace anyone. I would simply like to earn a place as the lender you call when a current partner cannot make a scenario work or when you need a fast second opinion."
    return dict(score=score,growth_score=growth,gov_fit=gov,niche_fit=niche,product_fit=", ".join(products),ai_summary=summary,score_reasons=json.dumps(reasons[:7]),next_best_action=next_action,call_opener=call,likely_objection=objection,objection_response=response)

def rescore(pid):
    with db() as c:
        row = c.execute("select * from prospects where id=?", (pid,)).fetchone()
        if not row: return
        a = analyze(dict(row))
        c.execute("""update prospects set score=:score,growth_score=:growth_score,gov_fit=:gov_fit,niche_fit=:niche_fit,product_fit=:product_fit,ai_summary=:ai_summary,score_reasons=:score_reasons,next_best_action=:next_best_action,call_opener=:call_opener,likely_objection=:likely_objection,objection_response=:objection_response,updated_at=:updated_at where id=:id""", {**a,"updated_at":NOW(),"id":pid})

init()

@app.get("/")
def home():
    response = make_response(render_template_string(HTML))
    response.delete_cookie("bb_demo")
    return response

@app.get("/demo")
def demo():
    response = make_response(render_template_string(HTML.replace("<body>", "<body data-demo=\"1\">")))
    response.set_cookie("bb_demo", "1", httponly=True, samesite="Lax")
    return response

@app.get("/health")
def health():
    try:
        with db() as c:
            prospect_count = c.execute("select count(*) from prospects").fetchone()[0]
        return jsonify(status="ok", prospects=prospect_count, version="5.3")
    except Exception as exc:
        return jsonify(status="error", detail=str(exc)), 500

def reject_demo_write():
    if request.cookies.get("bb_demo") == "1":
        return jsonify(error="This executive demo is read-only."), 403
    return None


def _days_since(value):
    if not value: return 999
    try: return max(0, (datetime.now() - datetime.fromisoformat(value)).days)
    except Exception: return 999

def _copilot_rank(row, overdue=False):
    d=dict(row); base=int(d.get("score") or 0)
    stage={"New":8,"Contacted":10,"Replied":16,"Meeting":8,"Approved":-20}.get(d.get("status"),0)
    stale=min(18,_days_since(d.get("updated_at"))//3)
    return max(0,min(100,base+stage+stale+(18 if overdue else 0)))

@app.get("/api/copilot/brief")
def copilot_brief():
    today=datetime.now().date().isoformat()
    with db() as c:
        prospects=[dict(x) for x in c.execute("select * from prospects")]
        overdue=c.execute("select count(*) from memories where follow_up_date<>'' and follow_up_date<?",(today,)).fetchone()[0]
        due_today=c.execute("select count(*) from memories where follow_up_date=?",(today,)).fetchone()[0]
        week_actions=c.execute("select count(*) from sales_activity where created_at>=datetime('now','-7 days')").fetchone()[0]
    ranked=sorted(prospects,key=lambda x:_copilot_rank(x),reverse=True)
    first=ranked[0] if ranked else None
    high=sum(1 for x in prospects if int(x.get('score') or 0)>=80)
    first_move=(f"Call {first['company']} first. {first.get('next_best_action') or 'Lead with scenario support.'}" if first else "Import or add prospects to generate a daily recommendation.")
    return jsonify(greeting="Good morning, Clay.",summary=f"BrokerBeacon analyzed {len(prospects)} prospects using only data stored in this application.",highlights=[{"label":"High-priority accounts","value":f"{high} prospects currently score 80 or higher."},{"label":"Follow-up pressure","value":f"{overdue} overdue and {due_today} due today."},{"label":"Recent execution","value":f"{week_actions} sales activities logged in the last seven days."}],first_move=first_move)

@app.post("/api/copilot/ask")
def copilot_ask():
    question=((request.json or {}).get("question") or "").strip()
    if not question:return jsonify(error="Question required"),400
    q=question.lower(); today=datetime.now().date().isoformat()
    with db() as c:
        rows=[dict(x) for x in c.execute("select * from prospects")]
        overdue_ids={x[0] for x in c.execute("select distinct prospect_id from memories where follow_up_date<>'' and follow_up_date<?",(today,))}
    filtered=rows; filters=[]
    state_match=re.search(r"\b(NC|SC|VA|GA|TN|MI)\b",question.upper())
    if state_match:
        st=state_match.group(1);filtered=[x for x in filtered if x.get('state')==st];filters.append(st)
    cities=[x.get('city','') for x in rows if x.get('city')]
    city=next((c for c in sorted(set(cities),key=len,reverse=True) if c.lower() in q),None)
    if city:filtered=[x for x in filtered if (x.get('city') or '').lower()==city.lower()];filters.append(city)
    if any(w in q for w in ['overdue','past due']):filtered=[x for x in filtered if x['id'] in overdue_ids];filters.append('overdue follow-ups')
    if any(w in q for w in ['government','fha','va','usda','dpa']):filtered=[x for x in filtered if int(x.get('gov_fit') or 0)>=60];filters.append('government fit 60+')
    if any(w in q for w in ['heloc','jumbo','niche']):filtered=[x for x in filtered if int(x.get('niche_fit') or 0)>=60];filters.append('niche fit 60+')
    score_match=re.search(r"(?:score|over|above|at least)\s*(\d{2,3})",q)
    threshold=int(score_match.group(1)) if score_match else (80 if any(w in q for w in ['high score','highest','best','priority','first']) else 0)
    if threshold:filtered=[x for x in filtered if int(x.get('score') or 0)>=threshold];filters.append(f'score {threshold}+')
    ranked=sorted(filtered,key=lambda x:_copilot_rank(x,x['id'] in overdue_ids),reverse=True)[:5]
    results=[]
    for x in ranked:
        why=[]
        if x['id'] in overdue_ids:why.append('an overdue follow-up is recorded')
        if int(x.get('score') or 0)>=80:why.append(f"opportunity score is {x.get('score')}")
        if int(x.get('gov_fit') or 0)>=70:why.append('strong government-loan fit')
        if x.get('status') in ('Replied','Meeting'):why.append(f"pipeline stage is {x.get('status')}")
        if not why:why.append(x.get('next_best_action') or 'highest available fit for this request')
        results.append({"id":x['id'],"company":x['company'],"city":x.get('city'),"state":x.get('state'),"status":x.get('status'),"score":x.get('score'),"priority_score":_copilot_rank(x,x['id'] in overdue_ids),"reason":"Recommended because "+", ".join(why)+"."})
    title="Copilot recommendation"
    if not results:answer="No prospects matched those criteria. Try broadening the location, score, or product-fit requirement."
    else:answer=f"I found {len(results)} matching prospect{'s' if len(results)!=1 else ''}. The list is ranked by opportunity score, pipeline stage, staleness, and recorded follow-up urgency."
    return jsonify(title=title,scope="Filters: "+(", ".join(filters) if filters else "none; ranked across the full database"),answer=answer,results=results)

@app.get("/api/prospects")
def prospects():
    q=request.args.get("search","").lower(); st=request.args.get("state","All"); sg=request.args.get("signal","All"); ps=request.args.get("status","All statuses")
    try: min_score=int(request.args.get("min_score",0))
    except ValueError: min_score=0
    with db() as c: rows=c.execute("select * from prospects order by score desc, company").fetchall()
    return jsonify([dict(x) for x in rows if (st=="All" or x["state"]==st) and (sg=="All" or x["signal"]==sg) and (ps=="All statuses" or x["status"]==ps) and int(x["score"] or 0)>=min_score and (not q or q in (x["company"]+" "+(x["owner"]or"")+" "+(x["city"]or"")).lower())])

@app.get("/api/prospects/<int:pid>")
def prospect(pid):
    with db() as c:
        p=c.execute("select * from prospects where id=?",(pid,)).fetchone()
        if not p:return jsonify(error="Prospect not found"),404
        d=dict(p); d["score_reasons"]=json.loads(d.get("score_reasons") or "[]")
        d["memories"]=[dict(x) for x in c.execute("select * from memories where prospect_id=? order by id desc",(pid,))]
        d["contacts"]=[dict(x) for x in c.execute("select * from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,name",(pid,))]
    return jsonify(d)

@app.post("/api/prospects")
def add():
    blocked = reject_demo_write()
    if blocked: return blocked
    d=request.json or {}
    if not d.get("company"): return jsonify(error="Company required"),400
    with db() as c:
        cur=c.execute("""insert into prospects(company,owner,city,state,signal,team,email,phone,status,source,website,nmls,specialties,hiring,source_name,source_url,verification_status,verified_at,license_type,verification_notes,authorized_use,created_at,updated_at) values(?,?,?,?,?,?,?,?, 'New','Manual',?,?,?,?,?,?,?,?,?,?,?,?,?)""",(d["company"],d.get("owner",""),d.get("city",""),d.get("state","").upper(),d.get("signal","Manual"),int(d.get("team")or 0),d.get("email",""),d.get("phone",""),d.get("website",""),d.get("nmls",""),d.get("specialties",""),int(d.get("hiring")or 0),d.get("source_name","Manual entry"),d.get("source_url",""),d.get("verification_status","Needs verification"),d.get("verified_at",""),d.get("license_type",""),d.get("verification_notes",""),int(bool(d.get("authorized_use"))),NOW(),NOW()))
        pid=cur.lastrowid
    rescore(pid); log("Prospect added",d["company"]); return jsonify(ok=True,id=pid)

@app.post("/api/prospects/<int:pid>/contacts")
def save_contact(pid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}
    if not (d.get("name") or d.get("email") or d.get("phone") or d.get("mobile")):
        return jsonify(error="Name or contact method required"),400
    with db() as c:
        if d.get("is_primary"):
            c.execute("update contacts set is_primary=0 where prospect_id=?",(pid,))
        values=(d.get('name','Company Contact Desk'),d.get('role',''),d.get('email',''),d.get('phone',''),d.get('mobile',''),d.get('nmls',''),d.get('specialties',''),d.get('languages',''),d.get('office_location',''),d.get('preferred_method',''),d.get('linkedin_url',''),d.get('source_url',''),d.get('verified_at',''),d.get('roster_status','Publicly verified'),d.get('notes',''),int(bool(d.get('is_primary'))),int(bool(d.get('is_decision_maker'))),int(bool(d.get('sms_consent'))),NOW())
        if int(d.get("id") or 0):
            c.execute("""update contacts set name=?,role=?,email=?,phone=?,mobile=?,nmls=?,specialties=?,languages=?,office_location=?,preferred_method=?,linkedin_url=?,source_url=?,verified_at=?,roster_status=?,notes=?,is_primary=?,is_decision_maker=?,sms_consent=?,updated_at=? where id=? and prospect_id=?""",values+(int(d["id"]),pid))
        else:
            c.execute("""insert into contacts(prospect_id,name,role,email,phone,mobile,nmls,specialties,languages,office_location,preferred_method,linkedin_url,source_url,verified_at,roster_status,notes,is_primary,is_decision_maker,sms_consent,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(pid,)+values[:-1]+(NOW(),NOW()))
        rows=[dict(x) for x in c.execute("select * from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,name",(pid,))]
        primary=next((x for x in rows if x['is_primary']),rows[0] if rows else None)
        if primary:
            c.execute("update prospects set owner=?,email=?,phone=?,updated_at=? where id=?",(primary['name'] if primary['name']!='Company Contact Desk' else '',primary['email'],primary['mobile'] or primary['phone'],NOW(),pid))
    return jsonify(rows)


def _official_pages(base):
    if not base: return []
    u=urllib.parse.urlparse(base if '://' in base else 'https://'+base)
    root=f"{u.scheme or 'https'}://{u.netloc}"
    paths=['','/team','/about','/about-us','/our-team','/loan-officers','/meet-the-team']
    return list(dict.fromkeys([base]+[root+x for x in paths]))[:7]

def _fetch_public_page(url):
    req=urllib.request.Request(url,headers={'User-Agent':'BrokerBeacon/5.1 public-company-roster-review'})
    with urllib.request.urlopen(req,timeout=8) as r:
        ctype=r.headers.get('Content-Type','')
        if 'text/html' not in ctype:return ''
        return r.read(800000).decode('utf-8','ignore')

def _discover_contacts(html,url):
    out=[]; plain=re.sub(r'<[^>]+>',' ',html_lib.unescape(html)); plain=re.sub(r'\s+',' ',plain)
    emails=sorted(set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',plain)))
    phones=sorted(set(re.findall(r'(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}',plain)))
    # JSON-LD Person records are the safest structured source for names.
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S):
        try:
            data=json.loads(html_lib.unescape(block))
            stack=data if isinstance(data,list) else [data]
            while stack:
                x=stack.pop()
                if isinstance(x,list):stack.extend(x);continue
                if not isinstance(x,dict):continue
                if x.get('@type')=='Person' or (isinstance(x.get('@type'),list) and 'Person' in x.get('@type')):
                    name=x.get('name',''); role=x.get('jobTitle','Loan Officer'); email=str(x.get('email','')).replace('mailto:',''); phone=x.get('telephone','')
                    if name:out.append(dict(name=name,role=role,email=email,phone=phone,source_url=url,raw_context='Structured Person record'))
                for v in x.values():
                    if isinstance(v,(dict,list)):stack.append(v)
        except Exception:pass
    # Stage explicit mailto/tel links as company contact discoveries, never guessed people.
    for e in emails[:8]:out.append(dict(name='',role='Public email on company website',email=e,phone='',source_url=url,raw_context='Public email link or page text'))
    for ph in phones[:8]:out.append(dict(name='',role='Public phone on company website',email='',phone=ph,source_url=url,raw_context='Public phone link or page text'))
    dedup=[];seen=set()
    for x in out:
        k=((x.get('name')or'').lower(),(x.get('email')or'').lower(),re.sub(r'\D','',x.get('phone')or''))
        if k in seen or not any(k):continue
        seen.add(k);dedup.append(x)
    return dedup

@app.get('/api/prospects/<int:pid>/contact-candidates')
def contact_candidates(pid):
    with db() as c:rows=[dict(x) for x in c.execute("select * from contact_candidates where prospect_id=? and status='Pending' order by id desc",(pid,))]
    return jsonify(rows)

@app.post('/api/prospects/<int:pid>/refresh-contacts')
def refresh_contacts(pid):
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:p=c.execute('select * from prospects where id=?',(pid,)).fetchone()
    if not p:return jsonify(error='Prospect not found'),404
    pages=_official_pages(p['website'] or p['source_url']); discoveries=[];checked=[]
    host=urllib.parse.urlparse(pages[0]).netloc.lower() if pages else ''
    for url in pages:
        if urllib.parse.urlparse(url).netloc.lower()!=host:continue
        try:
            html=_fetch_public_page(url);checked.append(url)
            discoveries.extend(_discover_contacts(html,url))
        except Exception:continue
    with db() as c:
        existing={(str(x['email']or'').lower(),re.sub(r'\D','',x['phone']or'')) for x in c.execute('select email,phone from contacts where prospect_id=?',(pid,))}
        pending={(str(x['email']or'').lower(),re.sub(r'\D','',x['phone']or'')) for x in c.execute("select email,phone from contact_candidates where prospect_id=? and status='Pending'",(pid,))}
        for x in discoveries:
            k=((x.get('email')or'').lower(),re.sub(r'\D','',x.get('phone')or''))
            if k in existing or k in pending:continue
            c.execute("insert into contact_candidates(prospect_id,name,role,email,phone,source_url,raw_context,status,created_at) values(?,?,?,?,?,?,?,'Pending',?)",(pid,x.get('name',''),x.get('role',''),x.get('email',''),x.get('phone',''),x.get('source_url',''),x.get('raw_context',''),NOW()))
        rows=[dict(x) for x in c.execute("select * from contact_candidates where prospect_id=? and status='Pending' order by id desc",(pid,))]
    return jsonify(message=f"Checked {len(checked)} official company page(s) and staged {len(rows)} unapproved discovery item(s).",candidates=rows)

@app.post('/api/contact-candidates/<int:cid>/approve')
def approve_candidate(cid):
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:
        x=c.execute("select * from contact_candidates where id=? and status='Pending'",(cid,)).fetchone()
        if not x:return jsonify(error='Discovery not found'),404
        c.execute("insert into contacts(prospect_id,name,role,email,phone,mobile,nmls,specialties,languages,office_location,preferred_method,linkedin_url,source_url,verified_at,roster_status,notes,is_primary,is_decision_maker,sms_consent,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(x['prospect_id'],x['name'] or 'Company Contact Desk',x['role'],x['email'],x['phone'],'','','','','','','',x['source_url'],datetime.now().date().isoformat(),'Publicly verified',x['raw_context'],0,0,0,NOW(),NOW()))
        c.execute("update contact_candidates set status='Approved' where id=?",(cid,))
    return jsonify(ok=True)

@app.post('/api/contact-candidates/<int:cid>/reject')
def reject_candidate(cid):
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:c.execute("update contact_candidates set status='Rejected' where id=?",(cid,))
    return jsonify(ok=True)

@app.post("/api/prospects/<int:pid>/memory")
def memory(pid):
    blocked = reject_demo_write()
    if blocked: return blocked
    d=request.json or {}
    if not d.get("note"): return jsonify(error="Note required"),400
    with db() as c:
        c.execute("insert into memories(prospect_id,note_type,note,follow_up_date,created_at) values(?,?,?,?,?)",(pid,d.get("note_type","Call note"),d["note"],d.get("follow_up_date",""),NOW()))
        rows=[dict(x) for x in c.execute("select * from memories where prospect_id=? order by id desc",(pid,))]
        company=c.execute("select company from prospects where id=?",(pid,)).fetchone()
    log("Relationship memory saved",company[0] if company else str(pid)); return jsonify(rows)

@app.post("/api/status/<int:pid>")
def status(pid):
    blocked = reject_demo_write()
    if blocked: return blocked
    s=(request.json or {}).get("status","New")
    with db() as c: c.execute("update prospects set status=?,updated_at=? where id=?",(s,NOW(),pid))
    log("Status updated",f"Prospect {pid}: {s}"); return jsonify(ok=True)

@app.post("/api/generate")
def generate():
    blocked = reject_demo_write()
    if blocked: return blocked
    d=request.json or {}
    with db() as c: p=c.execute("select * from prospects where id=?",(d.get("id"),)).fetchone()
    if not p:return jsonify(error="Prospect not found"),404
    p=dict(p); first=(p.get("owner")or"there").split()[0]; ch=d.get("channel","Email"); angle=d.get("angle","")
    recommended=(p.get("product_fit")or"Conventional, government, DPA, and HELOC support").split(",")[:4]
    hook=", ".join(x.strip() for x in recommended)
    if ch=="Email":
        sub=f"A scenario resource for {p['company']}"
        body=f"""Hi {first},

Congratulations on the momentum at {p['company']}. I noticed {p.get('signal','recent').lower()} activity in {p.get('city') or 'your market'} and wanted to introduce myself.

I work with Union Home Mortgage and support independent brokers with {hook}. Based on your current profile, I thought our ability to help with difficult scenarios and fast second opinions could be particularly useful.

I am not looking to replace any of your existing lender relationships. I would simply like to be a resource when another outlet cannot make a file work.

Would a brief introduction this week be worthwhile?

Best,
Clay"""
    elif ch=="LinkedIn":
        sub=""; body=f"Hi {first} — congratulations on the momentum at {p['company']}. I support independent brokers with {hook}. I’d be glad to be a quick second set of eyes when a scenario gets difficult, without asking you to replace any current lender relationship."
    else:
        sub=""; body=p.get("call_opener") or f"Hi {first}, this is Clay with Union Home Mortgage. I wanted to introduce myself as a scenario resource for {p['company']}."
    with db() as c:
        cur=c.execute("insert into outreach(prospect_id,channel,subject,body,status,created_at) values(?,?,?,?,?,?)",(p["id"],ch,sub,body,"Draft",NOW()))
    log("Outreach generated",p["company"]); return jsonify(id=cur.lastrowid,subject=sub,body=body)

@app.post("/api/queue/<int:i>")
def queue(i):
    blocked = reject_demo_write()
    if blocked: return blocked
    with db() as c:
        r=c.execute("select prospect_id from outreach where id=?",(i,)).fetchone()
        if not r:return jsonify(error="Draft not found"),404
        c.execute("update outreach set status='Queued' where id=?",(i,)); c.execute("update prospects set status='Contacted',updated_at=? where id=?",(NOW(),r["prospect_id"]))
    log("Outreach queued",str(i)); return jsonify(ok=True)

@app.get("/api/outreach")
def out():
    with db() as c: rows=c.execute("select o.*,p.company from outreach o join prospects p on p.id=o.prospect_id order by o.id desc limit 30").fetchall()
    return jsonify([dict(x) for x in rows])

@app.get("/api/dashboard")
def dashboard():
    with db() as c:
        total=c.execute("select count(*) from prospects").fetchone()[0]; avg=c.execute("select round(avg(score),1) from prospects").fetchone()[0]or 0; queued=c.execute("select count(*) from outreach where status='Queued'").fetchone()[0]
        status={r[0]:r[1] for r in c.execute("select status,count(*) from prospects group by status")}; activity=[dict(x) for x in c.execute("select * from activity order by id desc limit 6")]
        priorities=[dict(x) for x in c.execute("select id,company,score,product_fit,next_best_action from prospects where status not in ('Approved') order by score desc limit 5")]
    return jsonify(total=total,avg=avg,queued=queued,status=status,activity=activity,priorities=priorities)


@app.get("/api/daily-plan")
def daily_plan():
    today=datetime.now().date()
    week_start=today.fromordinal(today.toordinal()-today.weekday())
    with db() as c:
        rows=[dict(x) for x in c.execute("""select p.*,max(sa.created_at) last_action from prospects p left join sales_actions sa on sa.prospect_id=p.id where p.status<>'Approved' group by p.id""")]
        recent=[dict(x) for x in c.execute("""select sa.*,p.company from sales_actions sa join prospects p on p.id=sa.prospect_id order by sa.id desc limit 6""")]
        today_actions=[dict(x) for x in c.execute("select * from sales_actions where substr(created_at,1,10)=?",(today.isoformat(),))]
        week_actions=[dict(x) for x in c.execute("select * from sales_actions where substr(created_at,1,10)>=?",(week_start.isoformat(),))]
        due={r['prospect_id']:r['follow_up_date'] for r in c.execute("select prospect_id,min(follow_up_date) follow_up_date from memories where follow_up_date<>'' and note_type not like 'Completed:%' group by prospect_id")}
    stage_weight={'New':0,'Contacted':8,'Replied':15,'Meeting':20}
    actions=[]
    for p in rows:
        last=p.get('last_action') or p.get('updated_at') or p.get('created_at') or ''
        try: stale=max(0,(today-datetime.fromisoformat(last).date()).days)
        except Exception: stale=30
        urgency=0
        due_date=due.get(p['id'])
        overdue_prefix=''
        if due_date:
            try:
                delta=(datetime.fromisoformat(due_date).date()-today).days
                urgency=25 if delta<0 else 18 if delta==0 else 10 if delta<=3 else 0
                if delta<0: overdue_prefix=f"Follow-up is {abs(delta)} day(s) overdue. "
            except Exception: pass
        priority=int(p.get('score') or 0)+stage_weight.get(p.get('status'),0)+min(stale,14)+urgency
        channel='Call' if int(p.get('score') or 0)>=82 or p.get('status') in ('Replied','Meeting') else 'Email' if p.get('email') else 'Call'
        reason=overdue_prefix+(p.get('next_best_action') or 'Make a focused introduction and capture the next step.')
        actions.append({**p,'priority':priority,'stale_days':stale,'recommended_channel':channel,'reason':reason})
    actions.sort(key=lambda x:(-x['priority'],-int(x.get('score') or 0)))
    calls=sum(1 for x in today_actions if x['action_type']=='Call')
    emails=sum(1 for x in today_actions if x['action_type'] in ('Email','LinkedIn','Text'))
    convos=sum(1 for x in week_actions if x['outcome'] in ('Connected','Positive response','Meeting scheduled'))
    meetings=sum(1 for x in week_actions if x['action_type']=='Meeting' or x['outcome']=='Meeting scheduled')
    completed=len(today_actions); target=10
    return jsonify(actions=actions[:5],recent=recent,metrics={'calls_today':calls,'emails_today':emails,'conversations_week':convos,'meetings_week':meetings},goal={'completed':completed,'target':target,'percent':min(100,round(completed/target*100))})

@app.post("/api/sales-actions")
def sales_action():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}
    pid=int(d.get('prospect_id') or 0)
    action_type=(d.get('action_type') or 'Call').strip()
    outcome=(d.get('outcome') or '').strip()
    with db() as c:
        p=c.execute('select company,status from prospects where id=?',(pid,)).fetchone()
        if not p:return jsonify(error='Prospect not found'),404
        c.execute('insert into sales_actions(prospect_id,action_type,outcome,notes,follow_up_date,created_at) values(?,?,?,?,?,?)',(pid,action_type,outcome,d.get('notes','').strip(),d.get('follow_up_date',''),NOW()))
        if outcome in ('Connected','Positive response') and p['status']=='New': c.execute("update prospects set status='Contacted',updated_at=? where id=?",(NOW(),pid))
        if outcome=='Meeting scheduled': c.execute("update prospects set status='Meeting',updated_at=? where id=?",(NOW(),pid))
        if d.get('follow_up_date'):
            c.execute('insert into memories(prospect_id,note_type,note,follow_up_date,created_at) values(?,?,?,?,?)',(pid,'Follow-up',d.get('notes','').strip() or f'{action_type}: {outcome}',d.get('follow_up_date'),NOW()))
    log(f'{action_type} logged',f"{p['company']}: {outcome}")
    return jsonify(ok=True)

@app.get("/api/followups")
def followups_api():
    today=datetime.now().date()
    with db() as c:
        rows=[dict(x) for x in c.execute("""select m.*,p.company,p.score,p.owner,p.city,p.state from memories m join prospects p on p.id=m.prospect_id where m.note_type not like 'Completed:%' order by case when m.follow_up_date='' then 1 else 0 end,m.follow_up_date,m.id desc""")]
    counts={"overdue":0,"today":0,"week":0,"unscheduled":0}
    for x in rows:
        raw=(x.get("follow_up_date") or "").strip()
        if not raw:
            x["bucket"]="Unscheduled"; counts["unscheduled"]+=1; continue
        try:
            due=datetime.fromisoformat(raw).date()
            delta=(due-today).days
            if delta<0: x["bucket"]="Overdue"; counts["overdue"]+=1
            elif delta==0: x["bucket"]="Due today"; counts["today"]+=1
            elif delta<=7: x["bucket"]="Next 7 days"; counts["week"]+=1
            else: x["bucket"]="Upcoming"
        except ValueError:
            x["bucket"]="Date needs review"
    order={"Overdue":0,"Due today":1,"Next 7 days":2,"Upcoming":3,"Date needs review":4,"Unscheduled":5}
    rows.sort(key=lambda x:(order.get(x["bucket"],9),x.get("follow_up_date") or "9999"))
    return jsonify(items=rows,counts=counts)

@app.post("/api/followups/<int:memory_id>/complete")
def complete_followup(memory_id):
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:
        row=c.execute("select m.note_type,p.company from memories m join prospects p on p.id=m.prospect_id where m.id=?",(memory_id,)).fetchone()
        if not row:return jsonify(error="Follow-up not found"),404
        note_type=row["note_type"]
        if not note_type.startswith("Completed:"):
            c.execute("update memories set note_type=?,follow_up_date='' where id=?",("Completed: "+note_type,memory_id))
    log("Follow-up completed",row["company"]); return jsonify(ok=True)

@app.get("/api/territory")
def territory_data():
    with db() as c:
        states=[dict(x) for x in c.execute("select state,count(*) count,round(avg(score),1) avg_score from prospects group by state order by count desc")]
        metros=[dict(x) for x in c.execute("select city||', '||state name,count(*) count,round(avg(score),1) avg_score from prospects where city<>'' group by city,state order by count desc,avg_score desc limit 8")]
        carolinas=c.execute("select count(*) from prospects where state in ('NC','SC')").fetchone()[0]
        high_states=c.execute("select count(*) from (select state from prospects group by state having avg(score)>=75)").fetchone()[0]
    covered={x['state'] for x in states}
    preferred=['Raleigh, NC','Wilmington, NC','Greenville, SC','Columbia, SC','Richmond, VA','Nashville, TN','Atlanta, GA']
    existing={x['name'] for x in metros}
    gaps=[x for x in preferred if x not in existing][:4]
    return jsonify(states=states,metros=metros,carolinas=carolinas,high_priority_states=high_states,gaps=gaps)

@app.get("/api/executive")
def executive():
    with db() as c:
        total=c.execute("select count(*) from prospects").fetchone()[0]
        high=c.execute("select count(*) from prospects where score>=80").fetchone()[0]
        meetings=c.execute("select count(*) from prospects where status='Meeting'").fetchone()[0]
        avg=c.execute("select round(avg(score),1) from prospects").fetchone()[0] or 0
        pipeline={r[0]:r[1] for r in c.execute("select status,count(*) from prospects group by status")}
        gov=c.execute("select round(avg(gov_fit)) from prospects").fetchone()[0] or 0
        niche=c.execute("select round(avg(niche_fit)) from prospects").fetchone()[0] or 0
        growth=c.execute("select round(avg(growth_score)) from prospects").fetchone()[0] or 0
        top=[dict(x) for x in c.execute("select id,company,city,state,score,product_fit,next_best_action from prospects order by score desc limit 7")]
    readiness=round(sum(pipeline.get(k,0)*w for k,w in {'New':10,'Contacted':30,'Replied':55,'Meeting':80,'Approved':100}.items())/max(total,1),1)
    return jsonify(total=total,high_priority=high,meetings=meetings,opportunity_index=avg,conversion_readiness=readiness,pipeline={k:pipeline.get(k,0) for k in ['New','Contacted','Replied','Meeting','Approved']},products={'Government / DPA':gov,'HELOC / Jumbo':niche,'Growth potential':growth},top=top)

FIELD_ALIASES = {
    "company": ["company","company name","legal name","business name","licensee","licensee name","entity name","organization"],
    "owner": ["owner","broker owner","contact","contact name","qualifying individual","responsible individual"],
    "city": ["city","business city","mailing city","location city"],
    "state": ["state","business state","mailing state","location state","jurisdiction"],
    "nmls": ["nmls","nmls id","nmls#","company nmls","nmls number","license number","license no"],
    "email": ["email","email address","business email","contact email"],
    "phone": ["phone","telephone","business phone","contact phone","phone number"],
    "website": ["website","web site","url","company website"],
    "license_type": ["license type","license category","credential type","type"],
    "verification_status": ["verification status","verified status"],
    "verified_at": ["verified date","verification date","last verified","verified at"],
    "source_name": ["source","source name","data source"],
    "source_url": ["source url","source link","regulator url"],
    "specialties": ["specialties","products","loan products","focus"],
    "signal": ["signal","lead signal","prospect signal"],
    "team": ["team","team size","loan officers","lo count"],
    "hiring": ["hiring","is hiring","recruiting"],
    "status": ["status","pipeline status"],
    "verification_notes": ["verification notes","notes","license notes"]
}
SUPPORTED_STATES={"NC","SC","VA","GA","TN","MI"}

def clean_header(v):
    return re.sub(r"[^a-z0-9]+"," ",(v or "").strip().lower()).strip()

def detect_mapping(headers):
    normalized={clean_header(h):h for h in headers}
    mapping={}
    for field, aliases in FIELD_ALIASES.items():
        mapping[field]=next((normalized[a] for a in aliases if a in normalized),"")
    return mapping

def csv_rows(file_storage):
    raw=file_storage.read()
    try: text=raw.decode("utf-8-sig")
    except UnicodeDecodeError: text=raw.decode("cp1252")
    sample=text[:4096]
    try: dialect=csv.Sniffer().sniff(sample,delimiters=",;\t|")
    except csv.Error: dialect=csv.excel
    reader=csv.DictReader(io.StringIO(text),dialect=dialect)
    if not reader.fieldnames: raise ValueError("The CSV does not contain a header row.")
    return list(reader), detect_mapping(reader.fieldnames)

def val(row,mapping,field,default=""):
    h=mapping.get(field)
    return (row.get(h,default) if h else default) or default

def truthy(v): return str(v).strip().lower() in {"1","true","yes","y","active"}

def validate_row(row,mapping,index):
    company=str(val(row,mapping,"company")).strip()
    state=str(val(row,mapping,"state")).strip().upper()
    errors=[]
    if not company: errors.append("Missing company")
    if not state: errors.append("Missing state")
    elif state not in SUPPORTED_STATES: errors.append("Unsupported state")
    return {"row":index,"company":company,"state":state,"nmls":str(val(row,mapping,"nmls")).strip(),"errors":errors}

@app.post("/api/import/preview")
def import_preview():
    if "file" not in request.files:return jsonify(error="CSV file required"),400
    try: rows,mapping=csv_rows(request.files["file"])
    except Exception as e:return jsonify(error=str(e)),400
    checked=[validate_row(r,mapping,i+2) for i,r in enumerate(rows)]
    return jsonify(total_rows=len(rows),valid_rows=sum(not x["errors"] for x in checked),invalid_rows=sum(bool(x["errors"]) for x in checked),mapping=mapping,sample=checked[:25])

@app.post("/api/import")
def imp():
    blocked = reject_demo_write()
    if blocked: return blocked
    if "file" not in request.files:return jsonify(error="CSV file required"),400
    if not truthy(request.form.get("authorized_use")):return jsonify(error="Authorization confirmation is required"),400
    file=request.files["file"]
    try: rows,mapping=csv_rows(file)
    except Exception as e:return jsonify(error=str(e)),400
    batch_id=uuid.uuid4().hex[:12]; imported=updated=skipped=0; ids=[]; report=[]
    defaults={
      "source_name":request.form.get("default_source_name","").strip(),
      "source_url":request.form.get("default_source_url","").strip(),
      "verification_status":request.form.get("default_verification_status","Needs verification").strip(),
      "license_type":request.form.get("default_license_type","").strip()
    }
    with db() as c:
        for idx,r in enumerate(rows,start=2):
            check=validate_row(r,mapping,idx)
            if check["errors"]:
                skipped+=1; report.append({**check,"action":"skipped"}); continue
            company=check["company"]; state=check["state"]; nmls=check["nmls"]; city=str(val(r,mapping,"city")).strip()
            existing=None
            if nmls: existing=c.execute("select id from prospects where nmls=?",(nmls,)).fetchone()
            if not existing: existing=c.execute("select id from prospects where lower(company)=lower(?) and lower(city)=lower(?) and state=?",(company,city,state)).fetchone()
            def intval(field):
                try:return int(float(str(val(r,mapping,field,"0")).replace(",","")))
                except:return 0
            values={
              "company":company,"owner":str(val(r,mapping,"owner")).strip(),"city":city,"state":state,
              "signal":str(val(r,mapping,"signal","Imported")).strip() or "Imported","team":intval("team"),
              "email":str(val(r,mapping,"email")).strip(),"phone":str(val(r,mapping,"phone")).strip(),
              "status":str(val(r,mapping,"status","New")).strip() or "New","source":"Compliant CSV Import",
              "website":str(val(r,mapping,"website")).strip(),"nmls":nmls,"specialties":str(val(r,mapping,"specialties")).strip(),
              "hiring":1 if truthy(val(r,mapping,"hiring")) else 0,
              "source_name":str(val(r,mapping,"source_name",defaults["source_name"])).strip() or defaults["source_name"],
              "source_url":str(val(r,mapping,"source_url",defaults["source_url"])).strip() or defaults["source_url"],
              "verification_status":str(val(r,mapping,"verification_status",defaults["verification_status"])).strip() or defaults["verification_status"],
              "verified_at":str(val(r,mapping,"verified_at")).strip(),
              "license_type":str(val(r,mapping,"license_type",defaults["license_type"])).strip() or defaults["license_type"],
              "verification_notes":str(val(r,mapping,"verification_notes")).strip(),"authorized_use":1,"updated_at":NOW()
            }
            if existing:
                values["id"]=existing[0]
                c.execute("""update prospects set company=:company,owner=:owner,city=:city,state=:state,signal=:signal,team=:team,email=:email,phone=:phone,status=:status,source=:source,website=:website,nmls=:nmls,specialties=:specialties,hiring=:hiring,source_name=:source_name,source_url=:source_url,verification_status=:verification_status,verified_at=:verified_at,license_type=:license_type,verification_notes=:verification_notes,authorized_use=:authorized_use,updated_at=:updated_at where id=:id""",values)
                pid=existing[0]; updated+=1; action="updated"
            else:
                values["created_at"]=NOW()
                cur=c.execute("""insert into prospects(company,owner,city,state,signal,team,email,phone,status,source,website,nmls,specialties,hiring,source_name,source_url,verification_status,verified_at,license_type,verification_notes,authorized_use,created_at,updated_at) values(:company,:owner,:city,:state,:signal,:team,:email,:phone,:status,:source,:website,:nmls,:specialties,:hiring,:source_name,:source_url,:verification_status,:verified_at,:license_type,:verification_notes,:authorized_use,:created_at,:updated_at)""",values)
                pid=cur.lastrowid; imported+=1; action="imported"
            ids.append(pid); report.append({**check,"action":action})
        c.execute("insert into import_batches(id,filename,source_name,source_url,total_rows,imported,updated,skipped,report_json,created_at) values(?,?,?,?,?,?,?,?,?,?)",(batch_id,file.filename or "import.csv",defaults["source_name"],defaults["source_url"],len(rows),imported,updated,skipped,json.dumps(report),NOW()))
    for pid in set(ids):rescore(pid)
    log("Compliant CSV imported",f"{imported} new, {updated} updated, {skipped} skipped")
    return jsonify(imported=imported,updated=updated,skipped=skipped,batch_id=batch_id,report_url=f"/api/import/report/{batch_id}")

@app.get("/api/import/report/<batch_id>")
def import_report(batch_id):
    with db() as c:r=c.execute("select * from import_batches where id=?",(batch_id,)).fetchone()
    if not r:return jsonify(error="Import report not found"),404
    report=json.loads(r["report_json"] or "[]"); o=io.StringIO(); w=csv.DictWriter(o,fieldnames=["row","company","state","nmls","action","errors"]); w.writeheader()
    for x in report:w.writerow({**x,"errors":"; ".join(x.get("errors",[]))})
    return Response(o.getvalue(),mimetype="text/csv",headers={"Content-Disposition":f"attachment; filename=brokerbeacon_import_report_{batch_id}.csv"})

@app.get("/api/import/template")
def import_template():
    headers=["company","owner","city","state","nmls","email","phone","website","license_type","verification_status","verified_at","source_name","source_url","specialties","signal","team","hiring","status","verification_notes"]
    o=io.StringIO(); w=csv.writer(o); w.writerow(headers); w.writerow(["Example Mortgage LLC","","Charlotte","NC","123456","","","https://example.com","Mortgage broker","Needs verification","","Authorized source name","https://official-source.example","VA, FHA","Imported","0","no","New",""])
    return Response(o.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=brokerbeacon_compliant_import_template.csv"})

@app.get("/api/export")
def exp():
    with db() as c: rows=c.execute("select company,owner,city,state,signal,team,score,growth_score,gov_fit,niche_fit,product_fit,email,phone,website,nmls,specialties,hiring,status,source,source_name,source_url,verification_status,verified_at,license_type,verification_notes,authorized_use from prospects order by score desc").fetchall()
    o=io.StringIO(); w=csv.writer(o); w.writerow(rows[0].keys() if rows else []); w.writerows([tuple(x) for x in rows]); return Response(o.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=brokerbeacon_intelligence_export.csv"})


def _render_tokens(template, contact, prospect):
    values={
        'first_name':(contact.get('name') or '').split(' ')[0], 'full_name':contact.get('name') or '',
        'company':prospect.get('company') or '', 'city':prospect.get('city') or '', 'state':prospect.get('state') or '',
        'specialties':contact.get('specialties') or prospect.get('specialties') or ''}
    out=template or ''
    for k,v in values.items(): out=out.replace('{{'+k+'}}',str(v))
    return out

def _campaign_audience(d):
    channel=(d.get('channel') or 'Email').upper(); params=[int(d.get('min_score') or 0)]; where=['p.score>=?']
    if d.get('state'): where.append('p.state=?'); params.append(d['state'])
    if d.get('status_filter'): where.append('p.status=?'); params.append(d['status_filter'])
    dest="c.email" if channel=='EMAIL' else "coalesce(nullif(c.mobile,''),c.phone)"
    consent="coalesce(c.email_opt_out,0)=0" if channel=='EMAIL' else "coalesce(c.sms_consent,0)=1 and coalesce(c.sms_opt_out,0)=0"
    sql=f"""select c.*,p.company,p.city,p.state,p.score,p.status as prospect_status,p.specialties as prospect_specialties,{dest} destination from contacts c join prospects p on p.id=c.prospect_id where {' and '.join(where)} and trim(coalesce({dest},''))<>'' and {consent} and not exists(select 1 from suppressions s where s.channel=? and lower(s.destination)=lower({dest})) order by p.score desc,c.is_primary desc,c.id"""
    params.append(channel)
    with db() as c: eligible=[dict(x) for x in c.execute(sql,params)]
    with db() as c:
        total=c.execute(f"select count(*) from contacts c join prospects p on p.id=c.prospect_id where {' and '.join(where)}",params[:-1]).fetchone()[0]
    return eligible,max(0,total-len(eligible))

@app.get('/api/mission-control')
def mission_control():
    today=datetime.now().date(); week_start=today-timedelta(days=today.weekday()); now=NOW()
    with db() as c:
        prospects=[dict(x) for x in c.execute("select * from prospects order by score desc")]
        last={r['prospect_id']:r['last_at'] for r in c.execute("select prospect_id,max(created_at) last_at from sales_actions group by prospect_id")}
        meetings=c.execute("select count(*) from sales_actions where (action_type='Meeting' or outcome='Meeting scheduled') and date(created_at)>=?",(week_start.isoformat(),)).fetchone()[0]
        actions_week=c.execute("select count(*) from sales_actions where date(created_at)>=?",(week_start.isoformat(),)).fetchone()[0]
        camps={r['status']:r['n'] for r in c.execute("select status,count(*) n from campaign_recipients group by status")}
        active=c.execute("select count(*) from campaigns where status='Active'").fetchone()[0]
    ranked=[]; at_risk=[]
    for p in prospects:
        days=999
        if last.get(p['id']):
            try: days=(datetime.now()-datetime.fromisoformat(last[p['id']])).days
            except: pass
        if p['status'] in ('Contacted','Replied','Meeting') and days>=30: at_risk.append({**p,'days_inactive':days})
        urgency=min(days,20) if days!=999 else 20
        ranked.append({**p,'priority':p['score']+urgency,'reason':p.get('next_best_action') or 'Make the next relationship-building touch.'})
    ranked.sort(key=lambda x:-x['priority']); at_risk.sort(key=lambda x:-x['days_inactive'])
    alerts=[p for p in prospects if 'new' in (p.get('signal') or '').lower() or (p.get('created_at') or '')[:10]>=(today-timedelta(days=14)).isoformat()][:6]
    products=[]
    for name,terms in [('VA / FHA',['VA','FHA']),('DPA',['DPA']),('HELOC',['HELOC']),('Jumbo / niche',['Jumbo','niche']),('Low-FICO',['Lower-FICO'])]:
        products.append({'name':name,'count':sum(1 for p in prospects if any(t.lower() in (p.get('product_fit') or '').lower() for t in terms))})
    brief=f"Start with {ranked[0]['company'] if ranked else 'your top account'} and complete the five ranked actions before broad prospecting. {len(alerts)} new-account alerts and {len(at_risk)} relationships need attention. The strongest current product lane is {max(products,key=lambda x:x['count'])['name'] if products else 'scenario support'}."
    return jsonify(metrics={'priority_calls':min(5,len(ranked)),'new_alerts':len(alerts),'at_risk':len(at_risk),'meetings_week':meetings},priorities=ranked[:5],new_alerts=alerts,at_risk=at_risk[:6],products=products,goals={'completed':actions_week,'target':50,'percent':min(100,round(actions_week/50*100))},campaigns={'active':active,'queued':camps.get('Queued',0),'sent':camps.get('Sent',0),'failed':camps.get('Failed',0)},brief=brief)

@app.post('/api/campaigns/preview')
def campaign_preview():
    eligible,suppressed=_campaign_audience(request.json or {})
    return jsonify(eligible=len(eligible),suppressed=suppressed,sample=[{'name':x['name'],'company':x['company'],'destination':x['destination']} for x in eligible[:8]])

@app.get('/api/campaigns')
def campaign_list():
    with db() as c:
        rows=[dict(x) for x in c.execute("select * from campaigns order by id desc")]
        for x in rows:
            stats={r['status']:r['n'] for r in c.execute("select status,count(*) n from campaign_recipients where campaign_id=? group by status",(x['id'],))}
            x.update(total=sum(stats.values()),queued=stats.get('Queued',0),sent=stats.get('Sent',0),failed=stats.get('Failed',0),suppressed=stats.get('Suppressed',0))
    return jsonify(items=rows,live_email=bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_USERNAME')),live_sms=bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN') and os.getenv('TWILIO_FROM_NUMBER')))

@app.post('/api/campaigns')
def campaign_create():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}; channel=(d.get('channel') or 'Email').title()
    if channel not in ('Email','Sms'): channel='Email'
    if not d.get('name') or not d.get('body'): return jsonify(error='Campaign name and message body are required'),400
    if channel=='Email' and not d.get('subject'): return jsonify(error='Email campaigns require a subject'),400
    eligible,suppressed=_campaign_audience({**d,'channel':channel})
    scheduled=(d.get('scheduled_at') or NOW()).replace('Z','')
    with db() as c:
        cur=c.execute("insert into campaigns(name,channel,subject,body,min_score,state,status_filter,scheduled_at,daily_limit,status,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,'Active',?,?)",(d['name'],channel,d.get('subject',''),d['body'],int(d.get('min_score') or 0),d.get('state',''),d.get('status_filter',''),scheduled,int(d.get('daily_limit') or 50),NOW(),NOW()))
        cid=cur.lastrowid
        for x in eligible:
            contact=dict(x); prospect={'company':x['company'],'city':x['city'],'state':x['state'],'specialties':x['prospect_specialties']}
            c.execute("insert into campaign_recipients(campaign_id,prospect_id,contact_id,destination,rendered_subject,rendered_body,status,scheduled_at,created_at) values(?,?,?,?,?,?,'Queued',?,?)",(cid,x['prospect_id'],x['id'],x['destination'],_render_tokens(d.get('subject',''),contact,prospect),_render_tokens(d['body'],contact,prospect),scheduled,NOW()))
    log('Campaign created',f"{d['name']}: {len(eligible)} queued")
    return jsonify(ok=True,id=cid,queued=len(eligible),suppressed=suppressed)

@app.post('/api/campaigns/<int:cid>/status')
def campaign_status(cid):
    blocked=reject_demo_write()
    if blocked:return blocked
    status=(request.json or {}).get('status','Paused')
    if status not in ('Active','Paused','Completed'): return jsonify(error='Invalid campaign status'),400
    with db() as c:c.execute('update campaigns set status=?,updated_at=? where id=?',(status,NOW(),cid))
    return jsonify(ok=True)

def _send_email(to,subject,body):
    host=os.getenv('SMTP_HOST'); user=os.getenv('SMTP_USERNAME'); password=os.getenv('SMTP_PASSWORD'); sender=os.getenv('SMTP_FROM_EMAIL') or user
    if not all([host,user,password,sender]): return False,'SMTP credentials not configured',''
    port=int(os.getenv('SMTP_PORT','587')); msg=f"From: {sender}\r\nTo: {to}\r\nSubject: {subject}\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}"
    try:
        with smtplib.SMTP(host,port,timeout=20) as server:
            server.starttls(context=ssl.create_default_context());server.login(user,password);server.sendmail(sender,[to],msg.encode('utf-8'))
        return True,'','smtp'
    except Exception as e:return False,str(e)[:300],''

def _send_sms(to,body):
    sid=os.getenv('TWILIO_ACCOUNT_SID'); token=os.getenv('TWILIO_AUTH_TOKEN'); sender=os.getenv('TWILIO_FROM_NUMBER')
    if not all([sid,token,sender]): return False,'SMS provider credentials not configured',''
    url=f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'; data=urllib.parse.urlencode({'To':to,'From':sender,'Body':body}).encode(); req=urllib.request.Request(url,data=data); req.add_header('Authorization','Basic '+base64.b64encode(f'{sid}:{token}'.encode()).decode())
    try:
        with urllib.request.urlopen(req,timeout=20) as r: result=json.loads(r.read().decode())
        return True,'',result.get('sid','')
    except Exception as e:return False,str(e)[:300],''

@app.post('/api/campaigns/process')
def campaign_process():
    blocked=reject_demo_write()
    if blocked:return blocked
    now=datetime.now(); quiet_start=int(os.getenv('SMS_QUIET_START','20')); quiet_end=int(os.getenv('SMS_QUIET_END','9'))
    with db() as c:
        rows=[dict(x) for x in c.execute("select r.*,c.channel,c.daily_limit from campaign_recipients r join campaigns c on c.id=r.campaign_id where r.status='Queued' and c.status='Active' and (r.scheduled_at='' or r.scheduled_at<=?) order by r.id limit 100",(NOW(),))]
    sent=failed=skipped=0; per_campaign={}
    for r in rows:
        per_campaign[r['campaign_id']]=per_campaign.get(r['campaign_id'],0)+1
        if per_campaign[r['campaign_id']]>int(r['daily_limit'] or 50): skipped+=1;continue
        if r['channel']=='Sms' and (now.hour>=quiet_start or now.hour<quiet_end): skipped+=1;continue
        ok,err,pid=_send_email(r['destination'],r['rendered_subject'],r['rendered_body']) if r['channel']=='Email' else _send_sms(r['destination'],r['rendered_body'])
        with db() as c:
            c.execute("update campaign_recipients set status=?,sent_at=?,error=?,provider_id=? where id=?",('Sent' if ok else 'Failed',NOW() if ok else '',err,pid,r['id']))
        sent+=1 if ok else 0;failed+=0 if ok else 1
    return jsonify(sent=sent,failed=failed,skipped=skipped)

@app.post('/api/suppressions')
def add_suppression():
    d=request.json or {}; channel=(d.get('channel') or '').upper(); destination=(d.get('destination') or '').strip()
    if channel not in ('EMAIL','SMS') or not destination:return jsonify(error='Channel and destination required'),400
    with db() as c:c.execute("insert or ignore into suppressions(channel,destination,reason,created_at) values(?,?,?,?)",(channel,destination,d.get('reason','Opt-out'),NOW()))
    return jsonify(ok=True)

@app.get("/api/integrations")
def gi():
    with db() as c:d={r[0]:r[1] for r in c.execute("select key,value from integrations")}
    return jsonify({k:d.get(k)=="true" for k in ["gmail_connected","hubspot_connected","nmls_source_configured"]})

@app.post("/api/integrations")
def si():
    blocked = reject_demo_write()
    if blocked: return blocked
    d=request.json or {}
    with db() as c:c.execute("insert or replace into integrations(key,value) values(?,?)",(d.get("key"),str(bool(d.get("value"))).lower()))
    return jsonify(ok=True)

if __name__=="__main__":
    init()
    app.run(host=os.getenv("HOST","127.0.0.1"), port=int(os.getenv("PORT","5000")), debug=False)
