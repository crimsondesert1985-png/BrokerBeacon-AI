Warning: truncated output (original token count: 151102)
Total output lines: 4990

# BrokerBeacon AI
# Copyright © 2026 Clay Carr. All rights reserved.
# BrokerBeacon AI™ is a trademark of Clay Carr.
from flask import Flask, request, jsonify, render_template_string, Response, send_file, make_response, redirect, g, has_request_context
import sqlite3, io, csv, os, json, re, uuid, smtplib, ssl, urllib.parse, urllib.request, base64, html, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from migrations import run_migrations
from intelligence import intelligence_dashboard, save_snapshots
from revenue_intelligence import executive_dashboard, log_revenue_event
from voice_agent import configured as voice_configured, create_twilio_call, human_greeting, voicemail, twiml, say, appointment_slots, ai_reply
from guideline_index import seed_index, index_fha_pdf, search as search_guideline_index, stats as guideline_index_stats
from saas import install_saas
from tenant_storage import ensure_workspace_database
from data_durability import create_backup, prepare_database, storage_status, verify_latest_backup
from security_monitoring import emit_security_alert
from postgres_migration import migration_status, rehearsal_status

app = Flask(__name__)
BUILD_VERSION = "26.0"
BUILD_NAME = "POSTGRESQL CUTOVER REHEARSAL"
DB = prepare_database(Path(__file__).with_name("brokerbeacon.db"))
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

.template-grid{display:grid;grid-template-columns:320px 1fr;gap:14px;margin-top:14px}.template-list{max-height:720px;overflow:auto}.template-item{padding:12px;border:1px solid var(--line);border-radius:12px;margin:8px 0;background:#fff;cursor:pointer}.template-item:hover,.template-item.active{border-color:var(--green);background:var(--green-3)}.template-item b{display:block;color:var(--green-dark)}.sequence-step{display:grid;grid-template-columns:64px 110px 1fr auto;gap:10px;align-items:center;padding:11px;border:1px solid var(--line);border-radius:12px;margin:8px 0;background:#fff}.sequence-step .day{font-weight:900;color:var(--green)}.tone-row{display:flex;gap:7px;flex-wrap:wrap}.tone-row button.active{background:var(--green)!important;color:#fff!important}.analytics-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.analytics-grid>div{padding:11px;border-radius:11px;background:var(--panel-2);text-align:center}.analytics-grid b{display:block;font-size:20px;color:var(--green-dark)}.library-tabs{display:flex;gap:6px;margin-bottom:10px}.library-tabs button.active{background:var(--green)!important;color:#fff!important}.step-editor{padding:12px;background:var(--panel-2);border-radius:12px;margin-top:10px}@media(max-width:900px){.template-grid{grid-template-columns:1fr}.sequence-step{grid-template-columns:55px 90px 1fr}.sequence-step button{grid-column:1/-1}.analytics-grid{grid-template-columns:repeat(3,1fr)}}

/* v8.3 professional navy + red command-center theme */
:root{--bg:#f3f6fb;--panel:#fff;--panel-2:#edf2f9;--text:#17233a;--muted:#66758f;--line:#d8e0ec;--green:#174ea6;--green-2:#2868cf;--green-3:#e8f0fe;--green-dark:#123b7a;--navy:#0d2347;--navy-2:#153866;--red:#c6283d;--red-soft:#fdecef;--shadow:0 12px 32px rgba(13,35,71,.09)}
body{background:linear-gradient(180deg,#f8fafd 0%,#eef3f9 100%)!important;color:var(--text)!important}
aside,.sidebar{background:linear-gradient(180deg,var(--navy) 0%,#091a36 100%)!important;box-shadow:8px 0 30px rgba(4,18,40,.16)}
.brand span{color:#6fb2ff!important}.version{color:#a9bdd9!important}
nav button.active,nav button:hover{background:linear-gradient(90deg,#ffffff1e,#c6283d22)!important;border-left:3px solid #ef4055!important}
h1,h2,h3,h4,h5{color:var(--navy)!important}.kicker,.eyebrow{color:var(--red)!important}.btn,button.btn,.smallbtn{color:var(--navy)!important;border-color:#bfd0e7!important}.btn:hover,.smallbtn:hover{background:#edf3fb!important;border-color:#8eaed4!important}.btn.primary,.primary,.cta,.savebtn,.btn.accent{background:linear-gradient(135deg,#1d5fbf,#123f83)!important;color:#fff!important}.btn.start-day{background:linear-gradient(135deg,#d43149,#a9182e)!important;color:#fff!important;border:0!important;padding:15px 22px!important;font-size:15px;font-weight:800;box-shadow:0 12px 24px rgba(198,40,61,.22)!important}.btn.start-day span{margin-right:7px}.pill,.tag,.badge,.contact-badge{background:#e9f1fc!important;color:#174b91!important;border-color:#bfd3ee!important}.score{color:#174ea6!important}a{color:#175eb8}.progress>div,.progressbar>div,.barfill{background:linear-gradient(90deg,#1b5db8,#d43149)!important}.goalring{background:conic-gradient(#d43149 calc(var(--goal)*1%),#e4eaf2 0)!important}.goalring>div{background:#fff!important}.orb{background:conic-gradient(#1d5fbf calc(var(--s)*1%),#e4eaf2 0)!important;color:var(--navy)}
.command-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:28px 30px;border-radius:18px;background:linear-gradient(120deg,#0d2347 0%,#173b6b 68%,#8f1c30 140%);box-shadow:0 18px 40px rgba(13,35,71,.18);color:#fff}.command-hero h2{color:#fff!important;font-size:28px;margin:8px 0}.command-hero p{color:#d6e2f2;max-width:780px;margin:0;line-height:1.6}.command-hero .kicker{color:#ff8a9a!important}.command-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.command-kpi{background:#fff;border:1px solid var(--line);border-top:4px solid #174ea6;border-radius:14px;padding:17px;box-shadow:var(--shadow)}.command-kpi:nth-child(1),.command-kpi:nth-child(4){border-top-color:var(--red)}.command-kpi span,.command-kpi small{display:block;color:var(--muted)}.command-kpi strong{display:block;font-size:28px;color:var(--navy);margin:7px 0}.morning-panel{border-top:4px solid #174ea6!important}.ash-panel{border-top:4px solid var(--red)!important}.brief-card{background:linear-gradient(135deg,#edf3fc,#fff)!important;border-left:4px solid #174ea6;padding:16px!important;color:#31415d!important}.brief-facts{display:flex;gap:10px;flex-wrap:wrap}.brief-facts span{background:#f3f6fa;border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--muted)}.brief-facts b{color:var(--navy)}.recommendations{display:grid;gap:10px}.recommendation{display:grid;grid-template-columns:30px 1fr;gap:10px;align-items:start;padding:11px;background:#f7f9fc;border:1px solid var(--line);border-radius:11px}.recommendation>span{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:var(--red);color:#fff;font-weight:800}.recommendation small{display:block;margin-top:4px}.priority-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.priority-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.health{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800}.health.healthy{background:#e4f5eb;color:#16723b}.health.cooling{background:#fff3dc;color:#8b5b00}.health.at-risk{background:var(--red-soft);color:#a51e33}.health-grid{display:grid;gap:10px}.health-row{display:flex;justify-content:space-between;align-items:center;padding:11px;border-bottom:1px solid var(--line)}.pro-priority{background:#fff!important}.panel,.metric,.card{border-radius:14px!important}.mission-grid{grid-template-columns:repeat(3,1fr)}
@media(max-width:1050px){.command-kpis{grid-template-columns:repeat(2,1fr)}.command-hero{align-items:flex-start;flex-direction:column}.priority-actions{grid-column:1/-1;justify-content:flex-start}}
@media(max-width:650px){.command-kpis{grid-template-columns:1fr}.command-hero{padding:22px}.command-hero h2{font-size:23px}}

/* v8.4 executive polish */
:root{
  --focus:0 0 0 3px rgba(29,95,191,.18);
  --card-shadow:0 10px 28px rgba(13,35,71,.08);
  --card-shadow-hover:0 16px 36px rgba(13,35,71,.13);
}
html{scroll-behavior:smooth}
body{font-family:Inter,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif!important;letter-spacing:-.005em}
.app{grid-template-columns:252px minmax(0,1fr)!important}
aside{padding:22px 14px!important;overflow-y:auto;z-index:20}
.brand{font-size:21px!important;letter-spacing:-.03em;padding:0 10px}.version{padding:0 10px 13px;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:14px!important;line-height:1.4}
nav button{position:relative;padding:11px 12px!important;margin:3px 0!important;border-radius:9px!important;font-weight:600;letter-spacing:.005em;transition:background .18s ease,color .18s ease,transform .18s ease!important}
nav button:hover{transform:translateX(2px)}
nav button.active:after{content:"";position:absolute;right:10px;top:50%;width:6px;height:6px;border-radius:50%;background:#ff7185;transform:translateY(-50%);box-shadow:0 0 0 4px rgba(255,113,133,.13)}
main{padding:26px clamp(18px,3vw,38px) 42px!important;max-width:1680px;width:100%;margin:0 auto}
.top{position:sticky;top:0;z-index:12;margin:-26px calc(clamp(18px,3vw,38px)*-1) 22px;padding:20px clamp(18px,3vw,38px) 14px;background:rgba(246,249,253,.91);backdrop-filter:blur(14px);border-bottom:1px solid rgba(216,224,236,.8)}
.top small{font-size:10px;letter-spacing:.13em;font-weight:800;color:#66758f}.top h1{margin:4px 0 0;font-size:27px;letter-spacing:-.035em}
.actions{align-items:center}.today-chip{display:inline-flex;align-items:center;min-height:38px;padding:0 11px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--muted);font-size:11px;font-weight:700;white-space:nowrap}
.btn,button.btn,.smallbtn{min-height:38px;font-weight:700;letter-spacing:.005em;box-shadow:0 1px 2px rgba(13,35,71,.03);transition:transform .16s ease,box-shadow .16s ease,background .16s ease,border-color .16s ease!important}
.btn:hover,.smallbtn:hover{transform:translateY(-1px);box-shadow:0 5px 14px rgba(13,35,71,.10)}
.btn:active,.smallbtn:active{transform:translateY(0)}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:none!important;box-shadow:var(--focus)!important;border-color:#5c8ed2!important}
.panel,.metric,.card,.command-kpi{box-shadow:var(--card-shadow)!important;border-color:#dbe3ef!important;transition:box-shadow .2s ease,border-color .2s ease,transform .2s ease}
.panel:hover,.command-kpi:hover{box-shadow:var(--card-shadow-hover)!important;border-color:#c7d5e8!important}
.panel{padding:20px!important}.panel h3{margin-top:0;letter-spacing:-.02em}.command-hero{position:relative;overflow:hidden;border:1px solid rgba(255,255,255,.09)}
.command-hero:after{content:"";position:absolute;width:260px;height:260px;border-radius:50%;right:-75px;top:-120px;background:radial-gradient(circle,rgba(255,255,255,.16),transparent 68%);pointer-events:none}
.command-copy{position:relative;z-index:1}.start-day{position:relative;z-index:1;white-space:nowrap}
.command-kpi{position:relative;overflow:hidden}.command-kpi:after{content:"";position:absolute;right:-22px;bottom:-30px;width:90px;height:90px;border-radius:50%;background:rgba(23,78,166,.045)}.command-kpi:nth-child(1):after,.command-kpi:nth-child(4):after{background:rgba(198,40,61,.055)}
.command-kpi strong{font-variant-numeric:tabular-nums;letter-spacing:-.04em}
table{font-variant-numeric:tabular-nums}thead th{position:sticky;top:0;background:var(--panel);z-index:2}tbody tr{transition:background .15s ease}tbody tr:hover{background:#f6f9fd}
input,select,textarea{background:#fff!important;color:var(--text)!important;border-color:#ccd7e6!important;transition:border-color .15s ease,box-shadow .15s ease}
textarea{resize:vertical}.toast{background:#0d2347!important;color:#fff!important;border:0!important;box-shadow:0 16px 40px rgba(5,18,40,.25)!important;padding:13px 16px!important}
dialog{background:#f8fafc!important;color:var(--text)!important;border-color:#ccd8e8!important;box-shadow:0 28px 90px rgba(5,18,40,.28)!important}
.empty{border:1px dashed #cbd7e7;border-radius:12px;background:#f8fafc;margin:8px 0}
.priority-card{transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}.priority-card:hover{transform:translateY(-1px);box-shadow:0 9px 22px rgba(13,35,71,.09);border-color:#bdcde2}
.health{letter-spacing:.02em}.kicker{letter-spacing:.14em!important}
.theme-toggle{min-width:86px}
.coach-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:25px 27px;margin-bottom:16px;border-radius:16px;background:linear-gradient(135deg,#0d2347 0%,#174ea6 72%,#1d60bd 100%);color:#fff;box-shadow:0 16px 38px rgba(13,35,71,.18)}
.coach-hero h2{color:#fff;margin:5px 0 7px;font-size:25px;letter-spacing:-.035em}.coach-hero p{margin:0;max-width:820px;color:#dce9fb;line-height:1.55}.coach-hero .kicker{color:#9fc5ff}.coach-hero .btn{background:#fff!important;color:#174ea6!important;border-color:#fff!important;white-space:nowrap}
.coach-kpis{margin-bottom:16px}.coach-queue{display:grid;gap:13px}.coach-card{border:1px solid #d8e2ef;border-radius:14px;background:#fff;padding:18px;box-shadow:0 5px 16px rgba(13,35,71,.05)}.coach-card:hover{border-color:#b8cbe4;box-shadow:0 10px 25px rgba(13,35,71,.09)}
.coach-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:13px}.coach-company{font-size:18px;font-weight:800;letter-spacing:-.025em}.coach-meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:6px}.coach-score{min-width:92px;text-align:center;border:1px solid #c8d8ed;background:#f4f8fd;border-radius:12px;padding:9px}.coach-score strong{display:block;font-size:23px;color:#174ea6}.coach-score small{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#66758f;font-weight:800}
.coach-grid{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:11px}.coach-block{border:1px solid #e0e7f0;background:#f8fafc;border-radius:11px;padding:12px}.coach-block b{display:block;margin-bottom:5px;color:#0d2347;font-size:11px;text-transform:uppercase;letter-spacing:.07em}.coach-block p{margin:0;line-height:1.48;font-size:13px}.coach-opening{grid-column:1/-1;border-left:4px solid #174ea6;background:#f4f8fd}.coach-reasons{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.coach-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding-top:13px;border-top:1px solid #e4eaf2}.coach-action-label{display:inline-flex;align-items:center;border-radius:999px;padding:5px 9px;background:#fff1f3;color:#a51f36;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}.coach-health-healthy{background:#e8f7ef;color:#17643a}.coach-health-cooling{background:#fff7df;color:#835b00}.coach-health-at-risk{background:#fff0f2;color:#a51f36}
body.dark-mode .coach-card,body.dark-mode .coach-block,body.dark-mode .coach-score{background:#101d34!important;border-color:#2b405f!important}body.dark-mode .coach-block{background:#14223a!important}body.dark-mode .coach-opening{background:#162b4b!important}body.dark-mode .coach-block b,body.dark-mode .coach-company{color:#edf4ff!important}body.dark-mode .coach-score strong{color:#78adf4!important}body.dark-mode .coach-actions{border-color:#2b405f!important}
@media(max-width:1050px){.coach-grid{grid-template-columns:1fr 1fr}.coach-opening{grid-column:1/-1}}@media(max-width:700px){.coach-hero,.coach-card-head{align-items:stretch;flex-direction:column}.coach-grid{grid-template-columns:1fr}.coach-opening{grid-column:auto}.coach-score{text-align:left;display:flex;align-items:center;gap:8px}.coach-score strong{display:inline}}
body.dark-mode{--bg:#081226;--panel:#101d34;--panel-2:#16253f;--text:#edf4ff;--muted:#9fb0c8;--line:#263957;--green-3:#172b49;--navy:#eaf2ff;--navy-2:#bcd2ef;--red-soft:#3a1822;--shadow:0 12px 32px rgba(0,0,0,.24);background:linear-gradient(180deg,#071124 0%,#0c1830 100%)!important;color:var(--text)!important}
body.dark-mode .top{background:rgba(8,18,38,.9);border-color:#263957}body.dark-mode .today-chip,body.dark-mode .panel,body.dark-mode .metric,body.dark-mode .card,body.dark-mode .command-kpi,body.dark-mode .campaign-row,body.dark-mode .template-item,body.dark-mode .sequence-step{background:#101d34!important;border-color:#263957!important}
body.dark-mode h1,body.dark-mode h2,body.dark-mode h3,body.dark-mode h4,body.dark-mode h5,body.dark-mode .command-kpi strong,body.dark-mode .btn,body.dark-mode button.btn,body.dark-mode .smallbtn{color:#edf4ff!important}
body.dark-mode .btn,body.dark-mode button.btn,body.dark-mode .smallbtn{background:#15243d!important;border-color:#314868!important}body.dark-mode .btn:hover,body.dark-mode .smallbtn:hover{background:#1d3152!important}
body.dark-mode .btn.primary,body.dark-mode .primary,body.dark-mode .btn.accent{background:linear-gradient(135deg,#347fe0,#194d97)!important;color:#fff!important}body.dark-mode .btn.start-day{background:linear-gradient(135deg,#e34760,#a91d34)!important}
body.dark-mode input,body.dark-mode select,body.dark-mode textarea{background:#0c182c!important;color:#edf4ff!important;border-color:#314868!important}body.dark-mode tbody tr:hover{background:#15243d}body.dark-mode thead th{background:#101d34}body.dark-mode .brief-card,body.dark-mode .recommendation,body.dark-mode .empty{background:#15243d!important;color:#dce8f8!important;border-color:#2c4262!important}body.dark-mode .brief-facts span{background:#14223a;border-color:#2b405f;color:#aebed4}body.dark-mode .goalring>div{background:#101d34!important}body.dark-mode dialog{background:#0d192d!important;color:#edf4ff!important;border-color:#314868!important}body.dark-mode .toast{background:#eaf2ff!important;color:#0d2347!important}
@media(max-width:900px){.top{position:static;margin:-26px calc(clamp(18px,3vw,38px)*-1) 22px}.today-chip{display:none}}
@media(max-width:600px){.top{padding-top:16px}.theme-toggle{min-width:auto}.command-hero{border-radius:15px}.command-kpi strong{font-size:25px}}

/* v8.10 Ash Underwriter local index */
.guide-index-status{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.guide-index-status .guide-chip{background:#e7f7ed;color:#0a6333}.guide-result mark{background:#fff0a6;color:#2b341f;padding:0 2px;border-radius:3px}.guide-result .indexed-meta{font-size:10px;color:var(--muted);margin-top:8px}.compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:12px 0}.compare-card{border:1px solid var(--line);border-radius:12px;padding:12px;background:#fff}.compare-card h4{margin:0 0 6px}.source-confidence{font-size:10px;font-weight:800;color:#138a48;text-transform:uppercase;letter-spacing:.08em}
/* v8.8 loan guidelines library */
.guide-hero{display:flex;justify-content:space-between;gap:22px;align-items:flex-end;padding:26px 28px;border-radius:18px;background:linear-gradient(120deg,#0d2347,#173b6b 72%,#8f1c30 145%);color:#fff;box-shadow:0 18px 40px rgba(13,35,71,.18)}
.guide-hero h2{color:#fff!important;margin:7px 0}.guide-hero p{color:#d9e5f4;max-width:850px;line-height:1.6;margin:0}.guide-hero .kicker{color:#ff9eaa!important}
.guide-toolbar{display:grid;grid-template-columns:1fr auto;gap:10px;margin:14px 0}.guide-toolbar input{width:100%}.guide-tabs{display:flex;gap:7px;flex-wrap:wrap}.guide-tabs button.active{background:linear-gradient(135deg,#1d5fbf,#123f83)!important;color:#fff!important}
.guide-program{display:none}.guide-program.active{display:block}.guide-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.guide-card{background:#fff;border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:var(--shadow)}.guide-card h3{margin:0 0 10px}.guide-card ul{padding-left:19px;margin:0}.guide-card li{margin:8px 0;line-height:1.5;color:var(--text)}
.guide-program-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}.guide-program-head h2{margin:0 0 5px}.guide-chip{display:inline-block;padding:5px 9px;border-radius:999px;background:#e8f0fe;color:#174b91;border:1px solid #bfd3ee;font-size:11px;font-weight:750}.source-links{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.source-links a{display:inline-flex;align-items:center;gap:5px;padding:8px 10px;border:1px solid #bfd0e7;border-radius:9px;background:#f7f9fc;text-decoration:none;font-size:12px;font-weight:700}.guide-alert{padding:13px 15px;border-left:4px solid var(--red);background:var(--red-soft);border-radius:0 11px 11px 0;line-height:1.5}.guide-note{padding:13px 15px;border-left:4px solid #1d5fbf;background:#eaf2fd;border-radius:0 11px 11px 0;line-height:1.5}.guide-search-hidden{display:none!important}
.guide-live-search{margin-top:14px}.guide-query-row{display:grid;grid-template-columns:180px 1fr auto;gap:9px;margin-top:14px}.guide-query-row input,.guide-query-row select{width:100%}.guide-example-row{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.guide-results{display:grid;gap:11px;margin-top:12px}.guide-result{border:1px solid #d7e1ee;border-radius:13px;padding:15px;background:#fff}.guide-result-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.guide-result h4{margin:0 0 5px;font-size:16px}.guide-result .source-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:#174b91}.guide-result .excerpt{line-height:1.55;margin:10px 0;color:var(--text)}.guide-result .result-url{font-size:11px;color:var(--muted);word-break:break-all}.guide-loading{padding:18px;border:1px dashed #b9c9de;border-radius:12px;background:#f7f9fc}.guide-empty{padding:20px;border:1px dashed #c3d0df;border-radius:12px;text-align:center;background:#f8fafc}.guide-warning{padding:10px 12px;border-left:4px solid #d59b16;background:#fff8e3;border-radius:0 9px 9px 0;margin-top:9px}.dark-mode .guide-result,.dark-mode .guide-loading,.dark-mode .guide-empty{background:#101d34!important;border-color:#2b405f!important}.dark-mode .guide-warning{background:#332a12!important}
@media(max-width:900px){.guide-grid{grid-template-columns:1fr}.guide-query-row{grid-template-columns:1fr}.guide-hero{align-items:flex-start;flex-direction:column}}

/* v9.0 Ash Underwriter answer-first workspace */
.underwriter-shell{display:grid;gap:14px}.underwriter-modebar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}.underwriter-modes{display:flex;gap:7px}.underwriter-modes button.active{background:#123f83!important;color:#fff!important;border-color:#123f83!important}.underwriter-answer{display:none;border:1px solid #bfd2eb;border-radius:16px;background:linear-gradient(135deg,#f8fbff,#eef5ff);padding:18px 20px;margin-top:13px}.underwriter-answer.visible{display:block}.plain-answer-box{margin-top:12px;padding:16px 18px;border:1px solid #a9c8ec;border-radius:14px;background:#fff}.plain-answer-label{font-size:10px;font-weight:900;letter-spacing:.09em;text-transform:uppercase;color:#174b91}.plain-answer-verdict{font-size:28px;line-height:1.18;font-weight:950;color:#0d2347;margin:7px 0 9px}.plain-answer-body{font-size:16px;line-height:1.62;color:#263d5a;margin:0;max-width:980px}.plain-answer-basis{margin-top:12px;font-size:12px;color:#62748d}.answer-detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-top:13px}.answer-detail{background:#f7faff;border:1px solid #d5e2f1;border-radius:12px;padding:12px 14px}.answer-detail h4{margin:0 0 7px;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:#174b91}.answer-detail ul{margin:0;padding-left:18px}.answer-detail li{font-size:13px;line-height:1.48;margin:4px 0;color:#314762}.answer-citations{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.answer-source-pill{display:inline-flex;align-items:center;border-radius:999px;padding:6px 9px;background:#e8f0fe;border:1px solid #bfd3ee;color:#174b91;font-size:11px;font-weight:850}.answer-status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.06em}.answer-status.yes{background:#e8f7ed;color:#166534;border:1px solid #b9e3c6}.answer-status.no{background:#fff0f0;color:#9f1d2d;border:1px solid #f0c1c7}.answer-status.conditional{background:#fff7df;color:#895d00;border:1px solid #ead49a}.answer-status.unclear{background:#eef2f7;color:#516176;border:1px solid #d4dde8}.answer-confidence{display:inline-flex;margin-left:7px;padding:3px 7px;border-radius:999px;background:#eef4fb;border:1px solid #cbd9e9;color:#526782;font-size:9px;font-weight:850;text-transform:uppercase}.dark-mode .plain-answer-box{background:#101d34!important;border-color:#365374!important}.dark-mode .plain-answer-verdict,.dark-mode .plain-answer-body{color:#edf4ff!important}.dark-mode .plain-answer-basis{color:#aebfd5!important}.dark-mode .answer-detail{background:#13213a!important;border-color:#365374!important}.dark-mode .answer-detail li{color:#c6d4e7!important}.answer-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.answer-badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 9px;background:#dcecff;color:#174b91;font-size:10px;font-weight:850;letter-spacing:.07em;text-transform:uppercase}.answer-title{font-size:21px;line-height:1.2;margin:8px 0 6px;color:#0d2347}.answer-summary{font-size:14px;line-height:1.62;margin:0;color:#273b58}.answer-caveat{margin-top:10px;padding:10px 12px;border-left:4px solid #d59b16;background:#fff8e3;border-radius:0 9px 9px 0;font-size:12px;line-height:1.45}.answer-findings{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:9px;margin-top:13px}.finding-card{border:1px solid #d9e4f1;border-radius:12px;background:#fff;padding:12px}.finding-card b{display:block;margin-bottom:5px}.finding-card p{margin:0;font-size:12px;line-height:1.48;color:#4c607d}.scenario-issues{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.scenario-issue{display:inline-flex;border-radius:999px;background:#fff;border:1px solid #c8d9ed;padding:5px 9px;font-size:11px;font-weight:750;color:#174b91}.guide-section-heading{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:16px 0 8px}.guide-section-heading h3{margin:0}.guide-program-group{border:1px solid #d9e3ef;border-radius:16px;background:#fff;overflow:hidden;margin-top:11px}.guide-program-group-head{display:flex;justify-content:space-between;align-items:center;padding:12px 15px;background:#f4f8fd;border-bottom:1px solid #d9e3ef}.guide-program-group-head h4{margin:0;font-size:14px}.guide-program-count{font-size:10px;font-weight:800;color:#66758f;text-transform:uppercase;letter-spacing:.07em}.guide-result-clean{padding:15px;border-bottom:1px solid #e6edf5}.guide-result-clean:last-child{border-bottom:0}.clean-result-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.clean-result-title{font-size:16px;font-weight:850;color:#0d2347;margin:2px 0 5px}.citation-line{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.citation-pill{display:inline-flex;border-radius:999px;background:#e8f0fe;color:#174b91;border:1px solid #bfd3ee;padding:4px 8px;font-size:10px;font-weight:800}.match-pill{display:inline-flex;border-radius:999px;background:#eef8f2;color:#17643a;border:1px solid #c9e8d5;padding:4px 8px;font-size:10px;font-weight:750}.clean-excerpt{font-size:13px;line-height:1.58;color:#344964;margin:10px 0 0}.clean-excerpt em{font-style:normal;background:#fff0a6;border-radius:3px;padding:0 2px}.result-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.guide-disclosure{margin-top:10px}.guide-disclosure summary{cursor:pointer;font-size:11px;font-weight:800;color:#174b91}.guide-disclosure div{margin-top:7px;font-size:11px;color:#66758f;word-break:break-word}.guide-empty-state{text-align:center;padding:28px 18px;border:1px dashed #c3d0df;border-radius:14px;background:#f8fafc}.dark-mode .underwriter-answer,.dark-mode .finding-card,.dark-mode .guide-program-group,.dark-mode .guide-result-clean{background:#101d34!important;border-color:#2b405f!important}.dark-mode .guide-program-group-head{background:#14223a!important;border-color:#2b405f!important}.dark-mode .answer-title,.dark-mode .clean-result-title{color:#edf4ff!important}.dark-mode .answer-summary,.dark-mode .clean-excerpt,.dark-mode .finding-card p{color:#b8c8dd!important}.dark-mode .answer-caveat{background:#332a12!important}.dark-mode .guide-empty-state{background:#101d34!important;border-color:#2b405f!important}
.answer-short-label{font-size:11px;font-weight:950;letter-spacing:.08em;text-transform:uppercase;color:#174b91;margin-bottom:5px}.answer-broker-script{margin-top:13px;padding:14px 16px;border-radius:12px;background:#f0f7ff;border:1px solid #c7dcf4}.answer-broker-script h4{margin:0 0 7px;font-size:12px;color:#174b91;text-transform:uppercase;letter-spacing:.06em}.answer-broker-script p{margin:0;font-size:14px;line-height:1.55;color:#263d5a}.followup-block{margin-top:13px;padding-top:12px;border-top:1px solid #d5e2f1}.followup-block h4{margin:0 0 8px;font-size:12px;color:#0d2347}.followup-options{display:flex;gap:7px;flex-wrap:wrap}.followup-option{border:1px solid #9ebee3;background:#fff;color:#174b91;border-radius:999px;padding:7px 11px;font-weight:800;font-size:11px;cursor:pointer}.followup-option:hover{background:#e8f1fc}.answer-grid-label{margin-top:14px;font-size:10px;font-weight:950;letter-spacing:.08em;text-transform:uppercase;color:#b4233b}.dark-mode .answer-broker-script{background:#13243f!important;border-color:#365374!important}.dark-mode .answer-broker-script p,.dark-mode .followup-block h4{color:#dce8f7!important}.dark-mode .followup-option{background:#101d34!important;color:#bcd8ff!important;border-color:#365374!important}

@media(max-width:720px){.answer-head,.clean-result-head,.guide-section-heading{flex-direction:column;align-items:stretch}.guide-query-row{grid-template-columns:1fr}.underwriter-modes{width:100%}.underwriter-modes .btn{flex:1}}

.executive-summary{margin-top:12px;padding:14px 16px;border-radius:12px;background:linear-gradient(135deg,#eef8ff,#f7fbff);border:1px solid #c7dff5}.executive-summary h4,.confidence-reasons h4,.related-topics h4,.scenario-form h4{margin:0 0 7px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#174b91}.executive-summary p{margin:0;font-size:15px;line-height:1.55;color:#193452;font-weight:650}.confidence-reasons{margin-top:12px;padding:12px 14px;border-radius:12px;background:#f8fbff;border:1px solid #d5e2f1}.confidence-reasons ul{margin:0;padding-left:18px}.confidence-reasons li{font-size:12px;line-height:1.45;margin:4px 0}.related-topics{margin-top:13px;padding-top:12px;border-top:1px solid #d5e2f1}.related-topic-row{display:flex;gap:7px;flex-wrap:wrap}.scenario-form{display:none;margin-top:12px;padding:14px;border:1px solid #cbdcf0;border-radius:14px;background:#f8fbff}.scenario-form.visible{display:block}.scenario-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:9px}.scenario-grid label{font-size:10px;font-weight:800;color:#526782;text-transform:uppercase;letter-spacing:.05em}.scenario-grid input,.scenario-grid select{width:100%;margin-top:5px}.scenario-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}.dark-mode .executive-summary,.dark-mode .confidence-reasons,.dark-mode .scenario-form{background:#13243f!important;border-color:#365374!important}.dark-mode .executive-summary p{color:#e2edfb!important}

/* v11.0 Executive UX Refresh */
:root{--ux-blue:#174ea6;--ux-blue2:#0d2347;--ux-red:#c6283d;--ux-soft:#f4f8fd;--ux-line:#d7e2f0;--ux-shadow:0 12px 30px rgba(13,35,71,.08)}
.view{animation:uxFade .22s ease}.view>.hero,.view>.coach-hero,.view>.guide-hero,.ux-page-hero{margin-bottom:16px}
@keyframes uxFade{from{opacity:.55;transform:translateY(4px)}to{opacity:1;transform:none}}
.ux-page-hero{position:relative;overflow:hidden;display:flex;justify-content:space-between;align-items:flex-end;gap:22px;padding:24px 26px;border-radius:18px;background:linear-gradient(125deg,#0d2347,#17467d 72%,#5c2748 140%);color:#fff;box-shadow:0 18px 40px rgba(13,35,71,.16)}
.ux-page-hero:after{content:"";position:absolute;width:280px;height:280px;border-radius:50%;right:-80px;top:-150px;background:radial-gradient(circle,rgba(255,255,255,.18),transparent 68%)}
.ux-page-hero>*{position:relative;z-index:1}.ux-page-hero h2{color:#fff!important;margin:5px 0 7px;font-size:25px;letter-spacing:-.035em}.ux-page-hero p{margin:0;max-width:850px;color:#dce9f7;line-height:1.55}.ux-page-hero .kicker{color:#ff9eaa!important}.ux-page-badge{display:inline-flex;padding:7px 10px;border:1px solid rgba(255,255,255,.28);border-radius:999px;background:rgba(255,255,255,.1);font-size:10px;font-weight:800;letter-spacing:.06em;white-space:nowrap}
.ux-insight{display:grid;grid-template-columns:minmax(0,1.45fr) repeat(3,minmax(160px,.55fr));gap:10px;margin:0 0 16px}.ux-insight-main,.ux-insight-cell{border:1px solid var(--ux-line);border-radius:14px;background:#fff;box-shadow:var(--ux-shadow);padding:15px 17px}.ux-insight-main{border-left:4px solid var(--ux-blue)}.ux-insight-label{font-size:9px;text-transform:uppercase;letter-spacing:.12em;font-weight:850;color:var(--ux-red);margin-bottom:5px}.ux-insight-main strong{display:block;font-size:17px;color:#0d2347;margin-bottom:4px}.ux-insight-main p,.ux-insight-cell p{margin:0;color:#60708a;line-height:1.45}.ux-insight-cell b{display:block;color:#0d2347;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px}.ux-insight-cell span{font-size:13px;color:#42536d}
.view>.panel,.view>.grid>.panel,.view>.campaign-layout>.panel,.view>.template-grid>.panel{border-radius:15px!important}.view>.panel>h3,.view .panel>.profile-head h3{font-size:17px;color:#0d2347}.metrics{gap:11px!important}.metric{position:relative;overflow:hidden;background:linear-gradient(180deg,#fff,#f9fbfe)!important}.metric:after{content:"";position:absolute;right:-26px;bottom:-34px;width:90px;height:90px;border-radius:50%;background:rgba(23,78,166,.055)}.metric span{font-weight:700;text-transform:uppercase;letter-spacing:.055em;font-size:9px!important}.metric strong{color:#0d2347!important}
.filters{padding:13px;border:1px solid var(--ux-line);border-radius:14px;background:#fff;box-shadow:var(--ux-shadow)}
.view table{background:#fff;border-radius:12px;overflow:hidden}.view thead th{color:#53647e}.view tbody td{color:#223553}
.panel-section-label{font-size:9px;text-transform:uppercase;letter-spacing:.12em;font-weight:850;color:var(--ux-red);margin-bottom:4px}
body.dark-mode .ux-page-hero{background:linear-gradient(125deg,#0a1d3b,#173d6b 72%,#4a203a 140%)}body.dark-mode .ux-insight-main,body.dark-mode .ux-insight-cell,body.dark-mode .filters,body.dark-mode .metric{background:#101d34!important;border-color:#2b405f!important}body.dark-mode .ux-insight-main strong,body.dark-mode .ux-insight-cell b,body.dark-mode .metric strong,body.dark-mode .view>.panel>h3,body.dark-mode .view .panel>.profile-head h3{color:#edf4ff!important}body.dark-mode .ux-insight-main p,body.dark-mode .ux-insight-cell p,body.dark-mode .ux-insight-cell span{color:#aebed4!important}
@media(max-width:1100px){.ux-insight{grid-template-columns:1fr 1fr}.ux-insight-main{grid-column:1/-1}}@media(max-width:700px){.ux-page-hero{align-items:flex-start;flex-direction:column}.ux-insight{grid-template-columns:1fr}.ux-insight-main{grid-column:auto}}


/* Sprint 20 · Navigation Architecture */
.app>aside{overflow-y:auto;scrollbar-width:thin;scrollbar-color:#ffffff38 transparent}
.workflow-nav{display:grid;gap:7px;padding-bottom:22px}
.nav-group{border:1px solid transparent;border-radius:12px;transition:.18s ease}
.nav-group.active-group{background:#ffffff08;border-color:#ffffff12}
.nav-group-toggle{display:flex!important;align-items:center;justify-content:space-between;width:100%;margin:0!important;padding:8px 10px!important;border:0!important;background:transparent!important;color:#a9bdd9!important;font-size:9px!important;font-weight:900!important;letter-spacing:.12em;text-transform:uppercase}
.nav-group-toggle:hover{background:#ffffff0b!important;border-left:0!important}
.nav-group-toggle .nav-chevron{font-size:12px;transition:transform .18s ease}
.nav-group.collapsed .nav-chevron{transform:rotate(-90deg)}
.nav-group-items{display:grid;grid-template-rows:1fr;opacity:1;transition:grid-template-rows .2s ease,opacity .18s ease}
.nav-group-items-inner{min-height:0;overflow:hidden;padding:0 4px 4px}
.nav-group.collapsed .nav-group-items{grid-template-rows:0fr;opacity:.35}
.nav-group .nav-group-items button{padding:9px 10px!important;margin:2px 0!important;font-size:12px}
.nav-group.active-group>.nav-group-toggle{color:#fff!important}
.nav-flow{display:flex;align-items:center;gap:7px}
.nav-flow-step{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#ffffff12;color:#d8e7fb;font-size:9px;letter-spacing:0}
body.dark-mode .nav-group.active-group{background:#ffffff0a;border-color:#ffffff16}
@media(max-width:900px){.workflow-nav{padding-bottom:0}}

/* v11.1 Global Ash Workplace */
.ash-global-trigger{background:linear-gradient(135deg,#d43149,#a9182e)!important;color:#fff!important;border:0!important;font-weight:850!important;box-shadow:0 8px 20px rgba(198,40,61,.2)!important}
.ash-global-trigger:hover{transform:translateY(-1px);box-shadow:0 12px 26px rgba(198,40,61,.26)!important}
.ash-drawer-backdrop{position:fixed;inset:0;background:rgba(5,17,38,.36);backdrop-filter:blur(2px);z-index:210;opacity:0;pointer-events:none;transition:.22s ease}
.ash-drawer-backdrop.open{opacity:1;pointer-events:auto}
.ash-drawer{position:fixed;top:0;right:0;width:min(470px,100vw);height:100vh;background:#f7faff;border-left:1px solid #cbd8e8;box-shadow:-24px 0 60px rgba(7,27,57,.22);z-index:220;transform:translateX(105%);transition:transform .24s ease;display:flex;flex-direction:column;color:#17233a}
.ash-drawer.open{transform:translateX(0)}
.ash-drawer-head{padding:19px 20px;background:linear-gradient(125deg,#0d2347,#18457d 70%,#7c2138);color:#fff;display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.ash-drawer-head h2{color:#fff!important;margin:3px 0 4px;font-size:22px}.ash-drawer-head p{margin:0;color:#dbe8f7;font-size:12px}.ash-close{background:#ffffff16!important;color:#fff!important;border-color:#ffffff38!important;padding:8px 10px!important}
.ash-context{margin:12px 16px 0;padding:11px 13px;background:#eaf2fc;border:1px solid #cbdcf1;border-radius:12px;display:flex;justify-content:space-between;gap:10px;align-items:center}.ash-context b{display:block;color:#123b70}.ash-context small{color:#60728e}.ash-context-badge{background:#fff;border:1px solid #bdd2ec;border-radius:999px;padding:5px 8px;font-size:10px;font-weight:800;color:#17539b;white-space:nowrap}
.ash-chat{flex:1;overflow:auto;padding:15px 16px 22px;display:flex;flex-direction:column;gap:12px}.ash-msg{max-width:94%;border-radius:14px;padding:12px 14px;line-height:1.5;box-shadow:0 5px 16px rgba(13,35,71,.06)}.ash-msg.user{align-self:flex-end;background:#174ea6;color:#fff;border-bottom-right-radius:4px}.ash-msg.assistant{align-self:flex-start;background:#fff;border:1px solid #d7e1ee;border-bottom-left-radius:4px}.ash-msg.assistant strong{color:#0d2347}.ash-msg .ash-eyebrow{font-size:9px;letter-spacing:.11em;text-transform:uppercase;font-weight:900;color:#c6283d;margin-bottom:5px}.ash-msg.user .ash-eyebrow{color:#dce9ff}.ash-msg ul{margin:8px 0 0;padding-left:18px}.ash-msg li{margin:5px 0}.ash-msg .muted{font-size:11px;margin-top:8px}
.ash-results{display:grid;gap:7px;margin-top:10px}.ash-result{border:1px solid #d7e2ef;background:#f8fbff;border-radius:10px;padding:9px}.ash-result-top{display:flex;justify-content:space-between;gap:8px}.ash-result b{font-size:12px}.ash-result small{display:block;color:#697991;margin-top:3px}.ash-result button{margin-top:7px}
.ash-suggestions{display:flex;gap:7px;flex-wrap:wrap;margin:0 16px 10px}.ash-suggestion{border:1px solid #bfd1e7;background:#fff;color:#174b91;padding:7px 9px;border-radius:999px;font-size:11px;font-weight:700;cursor:pointer}.ash-suggestion:hover{background:#edf4fd}
.ash-compose{padding:12px 16px 16px;border-top:1px solid #d9e3ef;background:#fff}.ash-compose-row{display:grid;grid-template-columns:1fr auto;gap:8px}.ash-compose textarea{min-height:54px;max-height:130px;resize:vertical;background:#f7faff!important;color:#17233a!important;border-color:#c9d7e8!important}.ash-compose button{align-self:end;height:44px}.ash-footnote{font-size:10px;color:#78879d;margin-top:7px}
body.dark-mode .ash-drawer{background:#0c1830;color:#edf4ff;border-color:#263957}.dark-mode .ash-context{background:#152743;border-color:#2b4567}.dark-mode .ash-context b{color:#edf4ff}.dark-mode .ash-context small{color:#9fb0c8}.dark-mode .ash-context-badge{background:#102039;color:#bcd7fa;border-color:#345476}.dark-mode .ash-msg.assistant{background:#11213a;border-color:#294360}.dark-mode .ash-msg.assistant strong{color:#f2f7ff}.dark-mode .ash-result{background:#152743;border-color:#2d486a}.dark-mode .ash-compose{background:#0e1b32;border-color:#263957}.dark-mode .ash-compose textarea{background:#13233d!important;color:#edf4ff!important;border-color:#304b6d!important}.dark-mode .ash-suggestion{background:#142642;border-color:#345375;color:#c9ddfa}
@media(max-width:700px){.ash-global-trigger{padding:9px 10px!important}.ash-drawer{width:100vw}.ash-drawer-head{padding-top:16px}}

/* v11.2 Production Intelligence */
.production-toolbar{display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:center;margin:14px 0}.production-toolbar input,.production-toolbar select{width:100%}.production-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.production-kpi{padding:18px;border:1px solid #d5dfec;border-radius:14px;background:#fff}.production-kpi span{display:block;color:#718097;font-size:11px}.production-kpi strong{display:block;color:#102a51;font-size:26px;margin:7px 0 3px}.production-kpi small{color:#8793a6}.production-layout{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.production-company{border:1px solid #d7e2ef;border-radius:14px;padding:14px;background:#fff;margin-bottom:10px;cursor:pointer}.production-company:hover{border-color:#86aee0;box-shadow:0 8px 22px rgba(20,58,105,.08)}.production-company-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.production-company h4{margin:0;color:#102a51}.production-company .prod-meta{color:#74839a;font-size:11px;margin-top:4px}.production-company .prod-volume{font-size:18px;font-weight:900;color:#154f9d;white-space:nowrap}.mix-row{display:grid;grid-template-columns:100px 1fr 90px;gap:10px;align-items:center;margin:8px 0}.mix-track{height:9px;border-radius:999px;background:#edf2f8;overflow:hidden}.mix-fill{height:100%;background:linear-gradient(90deg,#174ea6,#35a0d8)}.lo-table td,.lo-table th{padding:10px}.source-badge{display:inline-flex;padding:4px 7px;border-radius:999px;background:#edf5ff;color:#18539b;font-size:9px;font-weight:800}.freshness-note{padding:10px 12px;border-left:3px solid #e0a800;background:#fff8dc;color:#5e4a11;border-radius:0 10px 10px 0;font-size:11px}.production-empty{padding:32px;text-align:center;border:1px dashed #c6d3e3;border-radius:14px;color:#718097}.production-import{display:flex;gap:8px;align-items:center}.production-import input{max-width:280px}.prod-ash{padding:14px;border:1px solid #cbdcf0;background:#f4f8fd;border-radius:13px}.prod-ash h4{margin:0 0 7px;color:#102a51}.prod-chart{display:grid;gap:8px}.prod-month{display:grid;grid-template-columns:70px 1fr 90px;gap:9px;align-items:center;font-size:11px}.prod-month-bar{height:10px;background:#edf2f8;border-radius:999px;overflow:hidden}.prod-month-fill{height:100%;background:linear-gradient(90deg,#c6283d,#174ea6)}
body.dark-mode .production-kpi,body.dark-mode .production-company{background:#101d34;border-color:#2b405f}body.dark-mode .production-kpi strong,body.dark-mode .production-company h4{color:#edf4ff}body.dark-mode .prod-ash{background:#142642;border-color:#304e71}body.dark-mode .prod-ash h4{color:#edf4ff}body.dark-mode .mix-track,body.dark-mode .prod-month-bar{background:#263750}
@media(max-width:1000px){.production-layout{grid-template-columns:1fr}.production-kpis{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.production-toolbar{grid-template-columns:1fr}.production-kpis{grid-template-columns:1fr}.production-import{align-items:stretch;flex-direction:column}.production-import input{max-width:none}}

.marketing-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:14px;margin-top:14px}.marketing-card{border:1px solid var(--line);border-radius:15px;padding:16px;background:var(--panel)}.marketing-preview{white-space:pre-wrap;min-height:190px;background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:14px;line-height:1.55}.approval-row,.trigger-row,.asset-row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}.approval-row:last-child,.trigger-row:last-child,.asset-row:last-child{border-bottom:0}.marketing-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:#f0b429;margin-right:6px}.status-dot.approved{background:#1f9d68}.status-dot.rejected{background:#d64545}@media(max-width:900px){.marketing-grid{grid-template-columns:1fr}}

/* v12.0 Broker DNA */
.dna-toolbar{display:flex;gap:9px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:14px 0}.dna-toolbar select{min-width:170px}.dna-roster{display:grid;gap:11px}.dna-card{display:grid;grid-template-columns:74px minmax(0,1fr) auto;gap:16px;align-items:center;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 5px 16px rgba(13,35,71,.05)}.dna-card:hover{border-color:#a9bfdb;box-shadow:0 10px 25px rgba(13,35,71,.09)}.dna-orb{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#174ea6 calc(var(--dna)*1%),#e5ebf3 0);position:relative}.dna-orb:after{content:"";position:absolute;inset:8px;border-radius:50%;background:#fff}.dna-orb strong{position:relative;z-index:1;color:#0d2347;font-size:20px}.dna-main h4{margin:0 0 5px;color:#0d2347}.dna-meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}.dna-components{display:grid;grid-template-columns:repeat(4,minmax(110px,1fr));gap:7px}.dna-component{padding:8px 9px;border-radius:9px;background:#f4f7fb;border:1px solid #e0e7f0}.dna-component small{display:block;color:#6b7b92;font-size:9px;text-transform:uppercase;letter-spacing:.05em}.dna-component b{display:block;color:#173c70;margin-top:3px}.dna-next{margin-top:9px;color:#3c4f6b;font-size:12px;line-height:1.45}.dna-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.dna-tier{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}.dna-tier-a{background:#e5f6eb;color:#17653a}.dna-tier-b{background:#e8f0fe;color:#174b91}.dna-tier-c{background:#fff5da;color:#865d00}.dna-tier-d{background:#fdecef;color:#a51e33}.dna-method{font-size:12px;line-height:1.55;color:#60708a}.dna-method b{color:#0d2347}.dark-mode .dna-card,.dark-mode .dna-orb:after{background:#101d34!important;border-color:#2b405f!important}.dark-mode .dna-main h4,.dark-mode .dna-orb strong,.dark-mode .dna-component b,.dark-mode .dna-method b{color:#edf4ff!important}.dark-mode .dna-component{background:#14223a;border-color:#2b405f}.dark-mode .dna-next,.dark-mode .dna-method{color:#aebed4}.dark-mode .dna-orb{background:conic-gradient(#4d91ea calc(var(--dna)*1%),#263750 0)}@media(max-width:850px){.dna-card{grid-template-columns:64px 1fr}.dna-actions{grid-column:1/-1;justify-content:flex-start}.dna-components{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.dna-components{grid-template-columns:1fr}}

/* v12.2 Ash Mission Control */
.mission-value{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;background:#e8f0fe;color:#174b91;font-size:10px;font-weight:900;margin-left:6px}.dark-mode .mission-value{background:#17345f;color:#d9e8ff}.mission-impact{margin-top:5px;color:#50637f;font-size:11px}.dark-mode .mission-impact{color:#aebed4}

/* v12.3 Opportunity Engine */
.oe-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin:15px 0}.oe-filters{display:flex;gap:8px;flex-wrap:wrap}.oe-filters select{min-width:145px}.oe-list{display:grid;gap:12px}.oe-card{display:grid;grid-template-columns:76px minmax(0,1fr) auto;gap:15px;align-items:center;border:1px solid var(--line);border-radius:15px;background:#fff;padding:16px;box-shadow:0 5px 17px rgba(13,35,71,.05)}.oe-card:hover{border-color:#9db7d6;box-shadow:0 11px 27px rgba(13,35,71,.09)}.oe-score{width:65px;height:65px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#174ea6 calc(var(--oe)*1%),#e5ebf3 0);position:relative}.oe-score:after{content:"";position:absolute;inset:8px;border-radius:50%;background:#fff}.oe-score strong{position:relative;z-index:1;color:#0d2347;font-size:20px}.oe-title{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.oe-title h4{margin:0;color:#0d2347}.oe-tier{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}.oe-hot{background:#fdecef;color:#a51e33}.oe-warm{background:#fff3d2;color:#7c5700}.oe-watch{background:#e8f0fe;color:#174b91}.oe-research{background:#edf1f5;color:#526176}.oe-money{display:inline-flex;padding:5px 8px;border-radius:999px;background:#e5f6eb;color:#17653a;font-size:10px;font-weight:900}.oe-confidence{font-size:10px;color:#60708a}.oe-components{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:7px;margin:9px 0}.oe-component{padding:8px;border-radius:9px;background:#f4f7fb;border:1px solid #e0e7f0}.oe-component small{display:block;color:#6b7b92;font-size:9px;text-transform:uppercase}.oe-component b{display:block;color:#173c70;margin-top:3px}.oe-explain{font-size:11px;color:#50637f;line-height:1.5}.oe-next{margin-top:7px;padding:9px 11px;border-left:3px solid #174ea6;background:#f2f7fe;border-radius:0 9px 9px 0;color:#304966;font-size:12px}.oe-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.dark-mode .oe-card,.dark-mode .oe-score:after{background:#101d34!important;border-color:#2b405f!important}.dark-mode .oe-title h4,.dark-mode .oe-score strong,.dark-mode .oe-component b{color:#edf4ff!important}.dark-mode .oe-component{background:#14223a;border-color:#2b405f}.dark-mode .oe-explain,.dark-mode .oe-confidence{color:#aebed4}.dark-mode .oe-next{background:#162946;color:#c3d3e7}.dark-mode .oe-score{background:conic-gradient(#4d91ea calc(var(--oe)*1%),#263750 0)}@media(max-width:900px){.oe-card{grid-template-columns:65px 1fr}.oe-actions{grid-column:1/-1;justify-content:flex-start}.oe-components{grid-template-columns:repeat(3,1fr)}}@media(max-width:580px){.oe-components{grid-template-columns:repeat(2,1fr)}.oe-filters{width:100%}.oe-filters select{flex:1;min-width:120px}}

/* Sprint 22 · Scout Web Discovery */
.scout-discovery{margin-bottom:14px;padding:0!important;overflow:hidden}.scout-head{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:17px 19px;background:linear-gradient(125deg,#0d2347,#164b82 74%,#1a6c75);color:#fff}.scout-head h3{color:#fff!important;margin:4px 0}.scout-head p{margin:0;color:#dce9f7}.scout-head .kicker{color:#8be7f2!important}.scout-controls{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.scout-controls select,.scout-controls input{min-width:145px;background:#fff!important}.scout-body{padding:15px 18px}.scout-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.scout-metric{padding:11px;border:1px solid #dce5f0;border-radius:11px;background:#f8fbff}.scout-metric small{display:block;color:#718097;font-size:9px;text-transform:uppercase;font-weight:850}.scout-metric b{display:block;color:#0d2347;font-size:20px;margin-top:4px}.scout-candidates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.scout-candidate{border:1px solid #d8e3ef;border-radius:13px;padding:13px;background:#fff}.scout-candidate-top{display:flex;justify-content:space-between;gap:10px}.scout-candidate h4{margin:0 0 4px;color:#0d2347}.scout-fields{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}.scout-fields input{width:100%;padding:8px;font-size:11px}.scout-evidence{margin-top:8px;padding:9px;border-left:3px solid #174ea6;background:#f3f7fc;border-radius:0 9px 9px 0;font-size:11px;line-height:1.4;color:#52647c}.scout-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.scout-sources{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px}.scout-source{font-size:10px;padding:5px 8px;border:1px solid #cbd9ea;border-radius:999px;background:#f7faff;color:#174b91;text-decoration:none}.scout-safety{font-size:11px;color:#65758c;margin-top:10px}.dark-mode .scout-head{background:linear-gradient(125deg,#081a36,#163b68 74%,#164b52)}.dark-mode .scout-metric,.dark-mode .scout-candidate{background:#101d34!important;border-color:#2b405f!important}.dark-mode .scout-metric b,.dark-mode .scout-candidate h4{color:#edf4ff}.dark-mode .scout-evidence{background:#14243e;color:#b8c9df}.dark-mode .scout-source{background:#142642;color:#c9ddfa;border-color:#345375}@media(max-width:900px){.scout-candidates{grid-template-columns:1fr}.scout-metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.scout-head{align-items:flex-start;flex-direction:column}.scout-controls{width:100%}.scout-controls>*{flex:1}.scout-fields{grid-template-columns:1fr}}
/* Sprint 23 · Scout Autopilot */
.autopilot-shell{margin:14px 18px 0;border:1px solid #cfdced;border-radius:15px;background:linear-gradient(135deg,#f8fbff,#f2f0ff);overflow:hidden}.autopilot-top{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 15px;border-bottom:1px solid #dce5f0}.autopilot-title{display:flex;align-items:center;gap:10px}.autopilot-orb{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;color:#fff;background:linear-gradient(135deg,#2563eb,#7657ff);box-shadow:0 8px 18px rgba(37,99,235,.22)}.autopilot-title h4{margin:0}.autopilot-title small{display:block;margin-top:3px}.autopilot-switch{display:flex;align-items:center;gap:8px;font-weight:800;color:#344865}.autopilot-body{padding:14px 15px}.autopilot-grid{display:grid;grid-template-columns:1.3fr repeat(4,minmax(100px,.55fr));gap:8px;align-items:end}.autopilot-states{min-height:72px;max-height:120px;overflow:auto;display:flex;gap:5px;flex-wrap:wrap;padding:8px;border:1px solid #ccd9ea;border-radius:10px;background:#fff}.autopilot-state{display:inline-flex;gap:4px;align-items:center;padding:4px 7px;border:1px solid #d5e0ed;border-radius:999px;font-size:10px}.autopilot-state input{min-height:0}.autopilot-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}.autopilot-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:11px}.autopilot-stat{padding:9px;border:1px solid #dce5f0;border-radius:10px;background:#fff}.autopilot-stat small{display:block;font-size:8px;text-transform:uppercase;color:#75849a;font-weight:900}.autopilot-stat b{display:block;margin-top:4px;color:#102a51}.research-queue{margin-top:13px}.research-card{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:11px;align-items:center;padding:11px;border:1px solid #dce5f0;border-radius:12px;background:#fff;margin-top:7px}.research-score{width:45px;height:45px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#e8f0ff,#efeaff);color:#174ea6;font-weight:950}.research-flags{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}.research-flag{padding:3px 6px;border-radius:999px;background:#fff3db;color:#7e5b13;font-size:9px}.coverage-strip{display:flex;gap:6px;overflow:auto;padding-bottom:4px;margin-top:10px}.coverage-state{min-width:92px;padding:8px;border-radius:9px;background:#edf4fc;border:1px solid #d5e1ef;font-size:9px}.coverage-state b{display:block;color:#173c70;margin-bottom:3px}.dark-mode .autopilot-shell{background:linear-gradient(135deg,#0e2039,#1a1d3e);border-color:#2c4260}.dark-mode .autopilot-top{border-color:#2c4260}.dark-mode .autopilot-states,.dark-mode .autopilot-stat,.dark-mode .research-card{background:#10233e;border-color:#2d4462}.dark-mode .autopilot-title h4,.dark-mode .autopilot-stat b{color:#edf4ff!important}.dark-mode .coverage-state{background:#142946;border-color:#304966}.dark-mode .coverage-state b{color:#d8e7fb}@media(max-width:1050px){.autopilot-grid{grid-template-columns:1fr 1fr 1fr}.autopilot-grid>div:first-child{grid-column:1/-1}}@media(max-width:700px){.autopilot-shell{margin:12px 10px 0}.autopilot-top{align-items:flex-start;flex-direction:column}.autopilot-grid,.autopilot-summary{grid-template-columns:1fr 1fr}.research-card{grid-template-columns:45px 1fr}.research-card>button{grid-column:1/-1}}
.control-tower{margin:14px 18px 0;padding:16px;border:1px solid #cbd9ec;border-radius:16px;background:radial-gradient(circle at 85% 0,#d8e7ff 0,transparent 34%),linear-gradient(145deg,#071a37,#102f5d);color:#f8fbff;box-shadow:0 18px 36px rgba(12,41,82,.2)}.tower-head{display:flex;justify-content:space-between;gap:16px;align-items:center}.tower-head h3{margin:3px 0;color:#fff}.tower-head p{margin:0;color:#b9c9df}.tower-controls{display:flex;gap:7px;align-items:end;flex-wrap:wrap}.tower-controls label{color:#c9d6e8;margin:0}.tower-controls select,.tower-controls input{background:#ffffff12;color:#fff;border-color:#ffffff2e}.tower-controls option{color:#102a51}.tower-stop{border-color:#ff7185!important;color:#ffb5c0!important}.tower-stop.active{background:#e33e58!important;color:#fff!important}.agent-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}.control-tower .agent-card{padding:11px;border:1px solid #ffffff1f;border-radius:12px;background:#ffffff0c}.control-tower .agent-card b{color:#fff}.control-tower .agent-card-top{display:flex;justify-content:space-between;gap:8px}.control-tower .agent-card small{color:#aebfd7}.agent-status{font-size:9px;padding:4px 7px;border-radius:999px;background:#4de0aa20;color:#78f0c4}.agent-status.working{background:#60a5fa25;color:#a8ccff}.tower-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-top:10px}.tower-metric{padding:9px;border:1px solid #ffffff19;border-radius:10px;background:#050f2240}.tower-metric small{display:block;color:#a9bad1;font-size:8px;text-transform:uppercase}.tower-metric b{display:block;margin-top:4px;font-size:17px;color:#fff}.tower-lower{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.tower-box{padding:11px;border:1px solid #ffffff19;border-radius:11px;background:#07172d90}.tower-box h4{margin:0 0 7px;color:#fff}.tower-run{display:grid;grid-template-columns:88px 1fr auto;gap:8px;padding:7px 0;border-bottom:1px solid #ffffff14;font-size:10px}.tower-run:last-child{border:0}.tower-run .warn{color:#ffcc75}.tower-empty{padding:12px;color:#aebfd7;text-align:center}.dark-mode .control-tower{border-color:#2f4c73}@media(max-width:1050px){.agent-grid{grid-template-columns:1fr 1fr}.tower-metrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.control-tower{margin:12px 10px}.tower-head{align-items:flex-start;flex-direction:column}.agent-grid,.tower-lower{grid-template-columns:1fr}.tower-metrics{grid-template-columns:1fr 1fr}}
.national-index{margin:14px 18px 0;border:1px solid #cddbea;border-radius:16px;background:#fff;overflow:hidden}.index-head{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:16px 17px;background:linear-gradient(125deg,#091c39,#174e82 72%,#0f7777);color:#fff}.index-head h3{margin:3px 0;color:#fff}.index-head p{margin:0;color:#d8e7f5}.index-mode{padding:7px 10px;border:1px solid #7be0d355;border-radius:999px;background:#3ae1c218;color:#a9fff1;font-size:10px;font-weight:850}.index-body{padding:14px 16px}.index-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:7px}.index-metric{padding:10px;border:1px solid #dce6f1;border-radius:11px;background:#f7faff}.index-metric small{display:block;color:#75859a;font-size:8px;text-transform:uppercase}.index-metric b{display:block;margin-top:4px;color:#102e57;font-size:18px}.index-tools{display:grid;grid-template-columns:1fr 170px 190px auto;gap:7px;margin:11px 0}.index-list{display:grid;gap:7px}.index-record{display:grid;grid-template-columns:minmax(190px,1.2fr) minmax(150px,.8fr) 110px 95px auto;gap:10px;align-items:center;padding:11px;border:1px solid #dde7f1;border-radius:11px;background:#fff}.index-record h4{margin:0;color:#102e57}.index-record small{color:#728299}.index-evidence{font-size:10px;color:#586b84}.index-source-count{color:#137f64;font-size:10px;font-weight:800}.index-warn{color:#9b6711}.dark-mode .national-index,.dark-mode .index-record{background:#0f1f37;border-color:#2d4562}.dark-mode .index-body{background:#0c1a2e}.dark-mode .index-metric{background:#122642;border-color:#2d4562}.dark-mode .index-metric b,.dark-mode .index-record h4{color:#edf5ff}@media(max-width:1050px){.index-metrics{grid-template-columns:repeat(3,1fr)}.index-record{grid-template-columns:1fr 1fr 90px}.index-record>*:last-child{grid-column:1/-1}}@media(max-width:700px){.national-index{margin:12px 10px}.index-head{align-items:flex-start;flex-direction:column}.index-metrics{grid-template-columns:1fr 1fr}.index-tools,.index-record{grid-template-columns:1fr}}
.population-engine{margin-top:12px;padding:12px;border:1px solid #ffffff20;border-radius:12px;background:#07172d90}.population-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.population-head h4{margin:2px 0;color:#fff}.population-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:9px}.population-stat{padding:8px;border:1px solid #ffffff18;border-radius:9px;background:#ffffff09}.population-stat small{display:block;color:#a9bad1;font-size:8px;text-transform:uppercase}.population-stat b{display:block;color:#fff;margin-top:3px}.population-queue{display:flex;gap:6px;overflow:auto;margin-top:9px;padding-bottom:3px}.population-item{min-width:145px;padding:8px;border:1px solid #ffffff18;border-radius:9px;background:#ffffff08;font-size:10px}.population-item b{display:flex;justify-content:space-between;color:#fff}.population-item small{display:block;color:#b9c9df;margin-top:4px}.population-item .priority{color:#8be7f2}.population-note{margin-top:8px;color:#b9c9df;font-size:10px}@media(max-width:700px){.population-head{align-items:flex-start;flex-direction:column}.population-summary{grid-template-columns:1fr 1fr}}

/* Sprint 21 · Ash Agent Command Center */
.agent-center{margin:14px 0;padding:0!important;overflow:hidden}.agent-center-head{display:flex;justify-content:space-between;gap:18px;align-items:center;padding:18px 20px;background:linear-gradient(125deg,#0d2347,#17467d 72%,#5c2748 140%);color:#fff}.agent-center-head h3{margin:4px 0;color:#fff!important}.agent-center-head p{margin:0;color:#dce9f7}.agent-center-head .kicker{color:#ff9eaa!important}.agent-center-body{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(300px,.8fr);gap:14px;padding:16px}.agent-roster{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.agent-card{border:1px solid #d9e4f1;border-radius:12px;background:#f8fbff;padding:11px}.agent-card-top{display:flex;align-items:center;gap:7px}.agent-avatar{width:27px;height:27px;border-radius:9px;display:grid;place-items:center;background:#e8f0fe;color:#174b91;font-weight:950}.agent-card b{display:block;color:#0d2347;font-size:11px}.agent-card small{display:block;margin-top:6px;line-height:1.35}.agent-run-status{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:13px 0 8px}.agent-step{display:grid;grid-template-columns:35px minmax(0,1fr) auto;gap:9px;a…111102 tokens truncated…t=len(prospects),drafts_created=drafts,followups_created=followups)

@app.get('/api/voice-agent')
def voice_agent_dashboard():
    with db() as c:
        cols={r[1] for r in c.execute('pragma table_info(contacts)')}
        if 'voice_consent' not in cols: c.execute('alter table contacts add column voice_consent integer default 0')
        if 'voice_opt_out' not in cols: c.execute('alter table contacts add column voice_opt_out integer default 0')
        contacts=[dict(x) for x in c.execute("select c.id,c.prospect_id,c.name,coalesce(c.mobile,c.phone,p.phone) phone,coalesce(c.voice_consent,0) voice_consent,coalesce(c.voice_opt_out,0) voice_opt_out,p.company from contacts c join prospects p on p.id=c.prospect_id where coalesce(c.mobile,c.phone,p.phone,'')<>'' and coalesce(c.voice_opt_out,0)=0 order by p.score desc,c.is_primary desc limit 40")]
        calls=[dict(x) for x in c.execute("select v.*,p.company,c.name from voice_calls v join prospects p on p.id=v.prospect_id join contacts c on c.id=v.contact_id order by v.id desc limit 20")]
        appointments=[dict(x) for x in c.execute("select a.*,p.company,c.name from appointments a join prospects p on p.id=a.prospect_id join contacts c on c.id=a.contact_id where a.status='Scheduled' order by a.start_at limit 12")]
    return jsonify(connected=voice_configured(),female_voice=os.getenv('TWILIO_VOICE','Polly.Joanna'),contacts=contacts,calls=calls,appointments=appointments)

@app.post('/api/voice-agent/consent')
def voice_agent_consent():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.get_json(silent=True) or {}; cid=int(d.get('contact_id') or 0); value=1 if d.get('consent') else 0
    with db() as c:
        cols={r[1] for r in c.execute('pragma table_info(contacts)')}
        if 'voice_consent' not in cols:c.execute('alter table contacts add column voice_consent integer default 0')
        if 'voice_opt_out' not in cols:c.execute('alter table contacts add column voice_opt_out integer default 0')
        c.execute('update contacts set voice_consent=?,voice_opt_out=case when ?=1 then 0 else voice_opt_out end,updated_at=? where id=?',(value,value,NOW(),cid))
    return jsonify(ok=True)

@app.post('/api/voice-agent/call')
def voice_agent_call():
    blocked=reject_demo_write()
    if blocked:return blocked
    if not voice_configured():return jsonify(error='Twilio is not configured. Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER in Render.'),400
    d=request.get_json(silent=True) or {}; cid=int(d.get('contact_id') or 0)
    with db() as c:
        row=c.execute("select c.*,p.company from contacts c join prospects p on p.id=c.prospect_id where c.id=?",(cid,)).fetchone()
        if not row:return jsonify(error='Contact not found'),404
        x=dict(row); phone=x.get('mobile') or x.get('phone')
        if not phone:return jsonify(error='Contact has no phone number'),400
        if not x.get('voice_consent') or x.get('voice_opt_out'):return jsonify(error='Explicit voice consent is required and the contact must not be opted out.'),400
        cur=c.execute("insert into voice_calls(prospect_id,contact_id,status,created_at,updated_at) values(?,?,'Queued',?,?)",(x['prospect_id'],cid,NOW(),NOW())); call_id=cur.lastrowid
    base=request.url_root.rstrip('/'); result=create_twilio_call(phone,f'{base}/voice/answer/{call_id}',f'{base}/voice/status/{call_id}')
    with db() as c:c.execute("update voice_calls set twilio_sid=?,status=?,updated_at=? where id=?",(result.get('sid',''),result.get('status','queued'),NOW(),call_id))
    return jsonify(ok=True,call_id=call_id,status=result.get('status','queued'))

@app.post('/voice/answer/<int:call_id>')
def voice_answer(call_id):
    with db() as c:
        row=c.execute("select v.*,c.name,p.company from voice_calls v join contacts c on c.id=v.contact_id join prospects p on p.id=v.prospect_id where v.id=?",(call_id,)).fetchone()
    if not row:return Response(twiml(say('This call is unavailable. Goodbye.')),mimetype='text/xml')
    x=dict(row); first=(x.get('name') or 'there').split()[0]; answered=(request.form.get('AnsweredBy') or '').lower()
    with db() as c:c.execute('update voice_calls set answered_by=?,status=?,updated_at=? where id=?',(answered or 'unknown','In progress',NOW(),call_id))
    xml=voicemail(first,x['company']) if answered.startswith('machine') else human_greeting(first,x['company'],call_id)
    return Response(xml,mimetype='text/xml')

@app.post('/voice/respond/<int:call_id>')
def voice_respond(call_id):
    said=(request.form.get('SpeechResult') or request.form.get('Digits') or '').strip(); low=said.lower()
    with db() as c:
        row=c.execute("select v.*,c.name,p.company,p.ai_summary,p.product_fit from voice_calls v join contacts c on c.id=v.contact_id join prospects p on p.id=v.prospect_id where v.id=?",(call_id,)).fetchone()
    if not row:return Response(twiml(say('Goodbye.')),mimetype='text/xml')
    x=dict(row)
    if any(w in low for w in ['stop','remove me','do not call','don\'t call','opt out']):
        with db() as c:
            c.execute('update contacts set voice_opt_out=1,voice_consent=0,updated_at=? where id=?',(NOW(),x['contact_id']))
            c.execute("update voice_calls set disposition='Opted out',transcript=transcript||?,updated_at=? where id=?",('\nContact: '+said,NOW(),call_id))
        return Response(twiml(say('Understood. You will not receive additional automated calls from BrokerBeacon. Goodbye.')),mimetype='text/xml')
    if any(w in low for w in ['yes','sure','interested','appointment','schedule','meeting','talk']):
        slots=appointment_slots(); prompt='I can schedule a short call with Clay. Press 1 for '+slots[0].strftime('%A at %I %p')+', press 2 for '+slots[1].strftime('%A at %I %p')+', or press 3 for '+slots[2].strftime('%A at %I %p')+'.'
        with db() as c:c.execute("update voice_calls set transcript=transcript||?,updated_at=? where id=?",('\nContact: '+said,NOW(),call_id))
        return Response(twiml(f'<Gather input="dtmf speech" numDigits="1" action="/voice/schedule/{call_id}" method="POST" timeout="8">{say(prompt)}</Gather>{say("No selection was received. Clay will follow up personally. Goodbye.")}'),mimetype='text/xml')
    if any(w in low for w in ['no','not now','busy']):
        with db() as c:c.execute("update voice_calls set disposition='Not interested / busy',transcript=transcript||?,updated_at=? where id=?",('\nContact: '+said,NOW(),call_id))
        return Response(twiml(say('No problem. I will let Clay know. Thank you for your time. Goodbye.')),mimetype='text/xml')
    context=f"Company: {x['company']}. Stored summary: {x.get('ai_summary') or 'none'}. Product fit: {x.get('product_fit') or 'none'}."
    reply=ai_reply(said,context) or 'Thank you. I can arrange a short conversation with Clay to discuss that. Would you like to schedule a call?'
    with db() as c:c.execute("update voice_calls set transcript=transcript||?,updated_at=? where id=?",('\nContact: '+said+'\nAsh: '+reply,NOW(),call_id))
    return Response(twiml(f'<Gather input="speech dtmf" action="/voice/respond/{call_id}" method="POST" speechTimeout="auto" timeout="7">{say(reply)}</Gather>{say("Thank you. Goodbye.")}'),mimetype='text/xml')

@app.post('/voice/schedule/<int:call_id>')
def voice_schedule(call_id):
    choice=(request.form.get('Digits') or '').strip(); speech=(request.form.get('SpeechResult') or '').lower()
    if not choice:
        choice='1' if 'one' in speech or 'first' in speech else '2' if 'two' in speech or 'second' in speech else '3' if 'three' in speech or 'third' in speech else ''
    slots=appointment_slots(); idx={'1':0,'2':1,'3':2}.get(choice)
    if idx is None:return Response(twiml(say('I could not identify a time. Clay will follow up personally. Goodbye.')),mimetype='text/xml')
    slot=slots[idx]
    with db() as c:
        call=c.execute('select * from voice_calls where id=?',(call_id,)).fetchone()
        if not call:return Response(twiml(say('Goodbye.')),mimetype='text/xml')
        cur=c.execute("insert into appointments(prospect_id,contact_id,start_at,status,source,notes,created_at) values(?,?,?,'Scheduled','AI Voice Agent','Scheduled by disclosed automated call',?)",(call['prospect_id'],call['contact_id'],slot.isoformat(timespec='minutes'),NOW()))
        c.execute("update voice_calls set appointment_id=?,disposition='Appointment scheduled',status='Completed',updated_at=? where id=?",(cur.lastrowid,NOW(),call_id))
        c.execute("insert into memories(prospect_id,note_type,note,follow_up_date,created_at) values(?,?,?,?,?)",(call['prospect_id'],'AI Voice Appointment','Appointment scheduled by Ash AI Voice Agent for '+slot.strftime('%A, %B %d at %I:%M %p'),slot.date().isoformat(),NOW()))
    return Response(twiml(say('Your appointment with Clay is scheduled for '+slot.strftime('%A at %I %p')+'. Thank you. Goodbye.')),mimetype='text/xml')

@app.post('/voice/status/<int:call_id>')
def voice_status(call_id):
    status=request.form.get('CallStatus') or 'unknown'; answered=request.form.get('AnsweredBy') or ''
    with db() as c:c.execute('update voice_calls set status=?,answered_by=case when ?<>\'\' then ? else answered_by end,updated_at=? where id=?',(status,answered,answered,NOW(),call_id))
    return ('',204)

@app.post('/api/campaigns/preview')
def campaign_preview():
    eligible,suppressed=_campaign_audience(request.json or {})
    return jsonify(eligible=len(eligible),suppressed=suppressed,sample=[{'name':x['name'],'company':x['company'],'destination':x['destination']} for x in eligible[:8]])

@app.get('/api/campaigns')
def campaign_list():
    with db() as c:
        rows=[dict(x) for x in c.execute("""select c.*,s.name sequence_name from campaigns c left join sequences s on s.id=c.sequence_id order by c.id desc""")]
        for x in rows:
            stats={r['status']:r['n'] for r in c.execute("select status,count(*) n from campaign_recipients where campaign_id=? group by status",(x['id'],))}
            x.update(total=sum(stats.values()),queued=stats.get('Queued',0)+stats.get('Processing',0),sent=stats.get('Sent',0),failed=stats.get('Failed',0),suppressed=stats.get('Suppressed',0))
        due=c.execute("""select count(*) from campaign_recipients r join campaigns c on c.id=r.campaign_id where r.status='Queued' and c.status='Active' and (r.scheduled_at='' or r.scheduled_at<=?)""",(NOW(),)).fetchone()[0]
    return jsonify(items=rows,live_email=bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD')),live_sms=bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN') and os.getenv('TWILIO_FROM_NUMBER')),scheduler_ready=bool(os.getenv('CAMPAIGN_AUTOMATION_SECRET')),due_now=due)

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

def _send_email(to,subject,body,recipient_id=0):
    host=os.getenv('SMTP_HOST'); user=os.getenv('SMTP_USERNAME'); password=os.getenv('SMTP_PASSWORD'); sender=os.getenv('SMTP_FROM_EMAIL') or user
    if not all([host,user,password,sender]): return False,'SMTP credentials not configured',''
    port=int(os.getenv('SMTP_PORT','587')); base=os.getenv('APP_BASE_URL','').rstrip('/')
    safe=html.escape(body).replace('\n','<br>')
    if base and recipient_id:
        def tracked(match):
            url=match.group(0); return f'<a href="{base}/track/click/{recipient_id}?url={urllib.parse.quote(url,safe="")}">{html.escape(url)}</a>'
        safe=re.sub(r'https?://[^\s<]+',tracked,safe)
        safe+=f'<img src="{base}/track/open/{recipient_id}.gif" width="1" height="1" alt="">'
    msg=f'From: {sender}\r\nTo: {to}\r\nSubject: {subject}\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<div style="font-family:Arial,sans-serif;line-height:1.55">{safe}</div>'
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

def _automation_authorized():
    secret=os.getenv('CAMPAIGN_AUTOMATION_SECRET','').strip()
    if not secret:return False
    supplied=(request.headers.get('X-Automation-Secret') or request.args.get('secret') or '').strip()
    return supplied==secret

def _process_due_campaigns(batch_limit=100):
    now=datetime.now(); quiet_start=int(os.getenv('SMS_QUIET_START','20')); quiet_end=int(os.getenv('SMS_QUIET_END','9'))
    max_attempts=max(1,int(os.getenv('CAMPAIGN_MAX_ATTEMPTS','3')))
    # Release jobs abandoned by an interrupted worker after 20 minutes.
    stale=(now-timedelta(minutes=20)).isoformat(timespec='seconds')
    with db() as c:
        c.execute("update campaign_recipients set status='Queued' where status='Processing' and coalesce(last_attempt_at,'')<?",(stale,))
        candidates=[dict(x) for x in c.execute("""select r.*,c.channel,c.daily_limit,c.auto_stop,p.status prospect_status
          from campaign_recipients r join campaigns c on c.id=r.campaign_id join prospects p on p.id=r.prospect_id
          where r.status='Queued' and c.status='Active' and coalesce(r.attempts,0)<?
          and (r.scheduled_at='' or r.scheduled_at<=?) order by r.scheduled_at,r.id limit ?""",(max_attempts,NOW(),batch_limit))]
    sent=failed=skipped=suppressed=0
    for r in candidates:
        # Stop future sequence steps when a relationship has already progressed.
        if int(r.get('auto_stop') or 0) and r.get('prospect_status') in ('Replied','Meeting','Approved','Funded'):
            with db() as c:c.execute("update campaign_recipients set status='Suppressed',error=? where id=?",('Sequence stopped: relationship '+r['prospect_status'],r['id']))
            suppressed+=1;continue
        if r['channel']=='Sms' and (now.hour>=quiet_start or now.hour<quiet_end): skipped+=1;continue
        day_start=now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(timespec='seconds')
        with db() as c:
            sent_today=c.execute("select count(*) from campaign_recipients where campaign_id=? and status='Sent' and sent_at>=?",(r['campaign_id'],day_start)).fetchone()[0]
            if sent_today>=int(r['daily_limit'] or 50): skipped+=1;continue
            claimed=c.execute("update campaign_recipients set status='Processing',attempts=coalesce(attempts,0)+1,last_attempt_at=? where id=? and status='Queued'",(NOW(),r['id'])).rowcount
        if not claimed:continue
        ok,err,pid=_send_email(r['destination'],r['rendered_subject'],r['rendered_body'],r['id']) if r['channel']=='Email' else _send_sms(r['destination'],r['rendered_body'])
        with db() as c:
            attempts=c.execute('select attempts from campaign_recipients where id=?',(r['id'],)).fetchone()[0]
            next_status='Sent' if ok else ('Failed' if attempts>=max_attempts else 'Queued')
            next_due='' if ok or next_status=='Failed' else (datetime.now()+timedelta(minutes=min(60,5*(2**max(0,attempts-1))))).isoformat(timespec='seconds')
            c.execute("update campaign_recipients set status=?,sent_at=?,error=?,provider_id=?,scheduled_at=case when ?<>'' then ? else scheduled_at end where id=?",(next_status,NOW() if ok else '',err,pid,next_due,next_due,r['id']))
        sent+=1 if ok else 0;failed+=0 if ok else 1
    with db() as c:
        c.execute("""update campaigns set status='Completed',updated_at=? where status='Active' and not exists(select 1 from campaign_recipients r where r.campaign_id=campaigns.id and r.status in ('Queued','Processing'))""",(NOW(),))
        c.execute("insert into automation_runs(run_type,started_at,finished_at,sent,failed,skipped,suppressed,detail) values('Campaign delivery',?,?,?,?,?,?,?)",(NOW(),NOW(),sent,failed,skipped,suppressed,json.dumps({'batch_limit':batch_limit})))
    return {'sent':sent,'failed':failed,'skipped':skipped,'suppressed':suppressed}

@app.post('/api/campaigns/process')
def campaign_process():
    blocked=reject_demo_write()
    if blocked:return blocked
    return jsonify(_process_due_campaigns())

@app.route('/api/automation/run',methods=['GET','POST'])
def automation_run():
    if not _automation_authorized():return jsonify(error='Unauthorized automation request'),401
    return jsonify(ok=True,**_process_due_campaigns(max(1,min(500,int(request.args.get('limit','100'))))))

@app.post('/api/suppressions')
def add_suppression():
    d=request.json or {}; channel=(d.get('channel') or '').upper(); destination=(d.get('destination') or '').strip()
    if channel not in ('EMAIL','SMS') or not destination:return jsonify(error='Channel and destination required'),400
    with db() as c:c.execute("insert or ignore into suppressions(channel,destination,reason,created_at) values(?,?,?,?)",(channel,destination,d.get('reason','Opt-out'),NOW()))
    return jsonify(ok=True)


@app.get('/api/marketing')
def marketing_center_data():
    with db() as c:
        templates=[dict(x) for x in c.execute("select * from message_templates order by updated_at desc,name")]
        approvals=[dict(x) for x in c.execute("select * from marketing_approvals order by id desc limit 50")]
        triggers=[dict(x) for x in c.execute("select t.*,m.name template_name from marketing_triggers t left join message_templates m on m.id=t.template_id order by t.id desc")]
        assets=[dict(x) for x in c.execute("select * from marketing_assets order by id desc")]
    return jsonify(summary={'templates':len(templates),'pending':sum(1 for x in approvals if x['status']=='Pending'),'approved':sum(1 for x in approvals if x['status']=='Approved'),'active_triggers':sum(1 for x in triggers if x['status']=='Active')},templates=templates,approvals=approvals,triggers=triggers,assets=assets)

@app.post('/api/marketing/generate')
def marketing_generate():
    d=request.json or {};goal=(d.get('goal') or 'Product spotlight').strip();topic=(d.get('topic') or 'wholesale mortgage support').strip();channel=(d.get('channel') or 'Email').strip();tone=(d.get('tone') or 'Professional').strip();audience=(d.get('audience') or 'brokers').strip();cta=(d.get('cta') or 'Reply with a scenario you would like me to review.').strip();details=(d.get('details') or '').strip()
    subject=f"A quick {topic} resource for {{{{company}}}}"
    opener={'Warm':'I hope your week is going well.','Conversational':'I wanted to send over something that may help your team.','Concise':'A quick resource for your team:','Professional':'I am reaching out with a resource that may support your team.'}.get(tone,'I am reaching out with a resource that may support your team.')
    detail_line=details if details else f"Union Home Mortgage Wholesale can help with {topic}, responsive scenario support, and a second look when a file needs another option."
    if channel.upper()=='SMS':
        body=f"Hi {{{{first_name}}}}, {detail_line} {cta} - Clay, UHM Wholesale. Reply STOP to opt out."
        subject=''
    else:
        body=f"Hi {{{{first_name}}}},\n\n{opener}\n\n{detail_line}\n\n{cta}\n\nClay Carr\nUnion Home Mortgage Wholesale"
    return jsonify(subject=subject,body=body,review_note=f"Drafted for {audience.lower()} using a {tone.lower()} tone. Verify all product, pricing, and compliance statements before approval.")

@app.post('/api/marketing/templates')
def marketing_template_create():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};channel=d.get('channel','Email');body=(d.get('body') or '').strip()
    if not body:return jsonify(error='Template body is required'),400
    with db() as c:
        tid=c.execute("insert into message_templates(name,channel,category,subject,body,is_system,created_at,updated_at) values(?,?,?,?,?,0,?,?)",(d.get('name') or 'Marketing template',channel,d.get('category') or 'Marketing',d.get('subject') or '',body,NOW(),NOW())).lastrowid
    return jsonify(ok=True,id=tid)

@app.post('/api/marketing/approvals')
def marketing_approval_create():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};body=(d.get('body') or '').strip()
    if not body:return jsonify(error='Message body is required'),400
    with db() as c:c.execute("insert into marketing_approvals(name,channel,subject,body,status,submitted_at,created_at,updated_at) values(?,?,?,?,'Pending',?,?,?)",(d.get('name') or 'Marketing content',d.get('channel','Email'),d.get('subject',''),body,NOW(),NOW(),NOW()))
    return jsonify(ok=True)

@app.post('/api/marketing/approvals/<int:aid>')
def marketing_approval_review(aid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};status=d.get('status','Pending')
    if status not in ('Pending','Approved','Rejected'):return jsonify(error='Invalid approval status'),400
    with db() as c:c.execute("update marketing_approvals set status=?,reviewed_at=?,review_notes=?,updated_at=? where id=?",(status,NOW(),d.get('review_notes',''),NOW(),aid))
    return jsonify(ok=True)

@app.post('/api/marketing/triggers')
def marketing_trigger_create():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};tid=int(d.get('template_id') or 0)
    if not tid:return jsonify(error='Template is required'),400
    with db() as c:c.execute("insert into marketing_triggers(trigger_type,template_id,status,created_at,updated_at) values(?,?,'Active',?,?)",(d.get('trigger_type') or 'New prospect added',tid,NOW(),NOW()))
    return jsonify(ok=True)

@app.post('/api/marketing/triggers/<int:tid>')
def marketing_trigger_status(tid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};status=d.get('status','Paused')
    if status not in ('Active','Paused'):return jsonify(error='Invalid trigger status'),400
    with db() as c:c.execute("update marketing_triggers set status=?,updated_at=? where id=?",(status,NOW(),tid))
    return jsonify(ok=True)

@app.post('/api/marketing/assets')
def marketing_asset_create():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};name=(d.get('name') or '').strip();url=(d.get('url') or '').strip()
    if not name or not (url.startswith('https://') or url.startswith('http://')):return jsonify(error='A valid asset name and URL are required'),400
    with db() as c:c.execute("insert into marketing_assets(name,url,category,status,created_at,updated_at) values(?,?,?,'Approved',?,?)",(name,url,d.get('category','General'),NOW(),NOW()))
    return jsonify(ok=True)

@app.get('/api/templates')
def template_list():
    with db() as c: rows=[dict(x) for x in c.execute("select * from message_templates order by channel,category,name")]
    return jsonify(items=rows)

@app.put('/api/templates/<int:tid>')
def template_update(tid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}
    with db() as c:c.execute("update message_templates set name=?,category=?,subject=?,body=?,updated_at=? where id=?",(d.get('name',''),d.get('category',''),d.get('subject',''),d.get('body',''),NOW(),tid))
    return jsonify(ok=True)

@app.post('/api/templates/<int:tid>/personalize')
def template_personalize(tid):
    d=request.json or {};pid=int(d.get('prospect_id') or 0);tone=d.get('tone','Conversational')
    with db() as c:
        t=c.execute('select * from message_templates where id=?',(tid,)).fetchone();p=c.execute('select * from prospects where id=?',(pid,)).fetchone()
        contact=c.execute("select * from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,id limit 1",(pid,)).fetchone()
    if not t or not p:return jsonify(error='Template or prospect not found'),404
    p=dict(p);contact=dict(contact) if contact else {'name':p.get('owner','')}
    subject=_render_tokens(t['subject'],contact,p);body=_render_tokens(t['body'],contact,p)
    first=(contact.get('name') or p.get('owner') or 'there').split()[0]
    fit=p.get('product_fit') or 'scenario support';signal=p.get('signal') or 'recent activity'
    if tone=='Concise':
        body=f"Hi {first},\n\nI noticed {signal.lower()} at {p['company']}. I can help with {fit}. Do you have a scenario worth comparing this week?\n\nClay Carr\nUnion Home Mortgage Wholesale"
    elif tone=='Professional':
        body=f"Hi {first},\n\nI am reaching out regarding {p['company']} and {signal.lower()}. Union Home Mortgage Wholesale supports {fit}. I would welcome the opportunity to provide a pricing comparison or second opinion on an active scenario.\n\nSincerely,\nClay Carr"
    elif tone=='Warm':
        body=f"Hi {first},\n\nI hope your week is going well. I noticed {signal.lower()} at {p['company']} and wanted to introduce myself. I would be glad to help your team with {fit} whenever another option would be useful.\n\nThanks,\nClay"
    else:
        body=f"Hi {first},\n\nI noticed {signal.lower()} at {p['company']} and wanted to reach out. I help brokers with {fit}, and I would be happy to be a quick second set of eyes on anything difficult.\n\nClay Carr\nUnion Home Mortgage Wholesale"
    return jsonify(subject=subject,body=body,company=p['company'],reason=f"Used the prospect signal, product fit, company, and {tone.lower()} tone.")

@app.get('/api/sequences')
def sequence_list():
    with db() as c:
        rows=[dict(x) for x in c.execute('select * from sequences order by name')]
        for x in rows:x['steps']=[dict(y) for y in c.execute('select * from sequence_steps where sequence_id=? order by step_order',(x['id'],))]
    return jsonify(items=rows)

@app.put('/api/sequence-steps/<int:sid>')
def sequence_step_update(sid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}
    with db() as c:c.execute('update sequence_steps set delay_days=?,channel=?,subject=?,body=?,updated_at=? where id=?',(int(d.get('delay_days') or 0),d.get('channel','Email'),d.get('subject',''),d.get('body',''),NOW(),sid))
    return jsonify(ok=True)

@app.post('/api/sequences/<int:sid>/launch')
def sequence_launch(sid):
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {};start=d.get('start_date') or datetime.now().date().isoformat();base=datetime.fromisoformat(start)
    with db() as c:steps=[dict(x) for x in c.execute('select * from sequence_steps where sequence_id=? order by step_order',(sid,))]
    if not steps:return jsonify(error='Sequence has no steps'),400
    # Enroll against email-capable contacts; SMS steps independently enforce recorded consent.
    eligible,_=_campaign_audience({'channel':'Email','min_score':d.get('min_score',0),'state':d.get('state',''),'status_filter':d.get('status_filter','')})
    enrollments=messages=0
    with db() as c:
        for x in eligible:
            en=c.execute("insert into sequence_enrollments(sequence_id,prospect_id,contact_id,status,started_at,created_at) values(?,?,?,'Active',?,?)",(sid,x['prospect_id'],x['id'],base.isoformat(timespec='seconds'),NOW())).lastrowid;enrollments+=1
            prospect={'company':x['company'],'city':x['city'],'state':x['state'],'specialties':x['prospect_specialties']};contact=dict(x)
            for st in steps:
                due=(base+timedelta(days=int(st['delay_days']))).isoformat(timespec='seconds')
                if st['channel']=='Task':
                    c.execute("insert into memories(prospect_id,note_type,note,follow_up_date,created_at) values(?,?,?,?,?)",(x['prospect_id'],'Sequence task',_render_tokens(st['body'],contact,prospect),due[:10],NOW()));continue
                dest=x['email'] if st['channel']=='Email' else (x['mobile'] or x['phone'])
                if st['channel']=='SMS' and (not int(x.get('sms_consent') or 0) or not dest):continue
                if not dest:continue
                cname=f"Sequence {sid}: {st['name']}"
                delivery_channel='Sms' if st['channel']=='SMS' else st['channel']
                camp=c.execute("insert into campaigns(name,channel,subject,body,min_score,state,status_filter,scheduled_at,daily_limit,status,created_at,updated_at,sequence_id,auto_stop) values(?,?,?,?,0,'','',?,?, 'Active',?,?,?,1)",(cname,delivery_channel,st['subject'],st['body'],due,int(d.get('daily_limit') or 35),NOW(),NOW(),sid)).lastrowid
                c.execute("insert into campaign_recipients(campaign_id,prospect_id,contact_id,destination,rendered_subject,rendered_body,status,scheduled_at,created_at,sequence_enrollment_id,step_id) values(?,?,?,?,?,?,'Queued',?,?,?,?,?)",(camp,x['prospect_id'],x['id'],dest,_render_tokens(st['subject'],contact,prospect),_render_tokens(st['body'],contact,prospect),due,NOW(),en,st['id']));messages+=1
    return jsonify(ok=True,enrollments=enrollments,messages=messages)

@app.get('/api/campaigns/analytics')
def campaign_analytics():
    with db() as c:
        total=lambda field: c.execute(f"select count(*) from campaign_recipients where {field}").fetchone()[0]
        sent=total("status='Sent'");opened=total("opened_at<>''");clicked=total("clicked_at<>''");replied=total("replied_at<>''");bounced=total("bounced_at<>''");opt=total("unsubscribed_at<>''")
        camps=[dict(x) for x in c.execute("""select c.id,c.name,c.channel,sum(case when r.status='Sent' then 1 else 0 end) sent,sum(case when r.opened_at<>'' then 1 else 0 end) opened,sum(case when r.clicked_at<>'' then 1 else 0 end) clicked,sum(case when r.replied_at<>'' then 1 else 0 end) replied from campaigns c left join campaign_recipients r on r.campaign_id=c.id group by c.id order by c.id desc limit 20""")]
    return jsonify(summary={'sent':sent,'delivered':max(0,sent-bounced),'opened':opened,'clicked':clicked,'replied':replied,'bounced':bounced,'opted_out':opt,'reply_rate':round(replied/sent*100,1) if sent else 0},campaigns=camps)

@app.get('/track/open/<int:rid>.gif')
def track_open(rid):
    pixel=base64.b64decode('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
    with db() as c:
        c.execute("update campaign_recipients set opened_at=case when opened_at='' then ? else opened_at end where id=?",(NOW(),rid));c.execute("insert into message_events(recipient_id,event_type,event_at,detail) values(?,'Opened',?,'tracking pixel')",(rid,NOW()))
    return Response(pixel,mimetype='image/gif',headers={'Cache-Control':'no-store'})

@app.get('/track/click/<int:rid>')
def track_click(rid):
    target=request.args.get('url','')
    with db() as c:
        c.execute("update campaign_recipients set clicked_at=case when clicked_at='' then ? else clicked_at end where id=?",(NOW(),rid));c.execute("insert into message_events(recipient_id,event_type,event_at,detail) values(?,'Clicked',?,?)",(rid,NOW(),target[:500]))
    return redirect(target if target.startswith(('http://','https://')) else '/')

@app.post('/api/campaign-recipients/<int:rid>/event')
def recipient_event(rid):
    blocked=reject_demo_write()
    if blocked:return blocked
    event=(request.json or {}).get('event','').title(); fields={'Opened':'opened_at','Clicked':'clicked_at','Replied':'replied_at','Bounced':'bounced_at','Opted_Out':'unsubscribed_at','Opted Out':'unsubscribed_at'}
    field=fields.get(event)
    if not field:return jsonify(error='Unsupported event'),400
    with db() as c:
        c.execute(f"update campaign_recipients set {field}=? where id=?",(NOW(),rid));c.execute("insert into message_events(recipient_id,event_type,event_at,detail) values(?,?,?,?)",(rid,event,NOW(),(request.json or {}).get('detail','')))
        if field in ('replied_at','unsubscribed_at'):
            row=c.execute('select sequence_enrollment_id,destination from campaign_recipients where id=?',(rid,)).fetchone()
            if row and row['sequence_enrollment_id']:
                c.execute("update sequence_enrollments set status='Stopped',stopped_at=?,stop_reason=? where id=?",(NOW(),event,row['sequence_enrollment_id']))
                c.execute("update campaign_recipients set status='Suppressed',error=? where sequence_enrollment_id=? and status='Queued'",('Sequence stopped: '+event,row['sequence_enrollment_id']))
    return jsonify(ok=True)

@app.post('/webhooks/twilio/sms')
def twilio_inbound_sms():
    sender=(request.form.get('From') or '').strip();body=(request.form.get('Body') or '').strip();keyword=body.upper().split()[0] if body else ''
    if keyword in ('STOP','UNSUBSCRIBE','CANCEL','END','QUIT') and sender:
        with db() as c:
            c.execute("insert or ignore into suppressions(channel,destination,reason,created_at) values('SMS',?,'Inbound STOP',?)",(sender,NOW()))
            c.execute("update contacts set sms_opt_out=1 where replace(replace(replace(replace(coalesce(mobile,phone),'-',''),'(',''),')',''),' ','') like ?",('%'+re.sub(r'\D','',sender)[-10:],))
            c.execute("update campaign_recipients set unsubscribed_at=?,status='Suppressed',error='Inbound STOP' where destination=? and status='Queued'",(NOW(),sender))
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>',mimetype='application/xml')


def classify_reply(subject, body, contact=None, prospect=None):
    text=((subject or '')+' '+(body or '')).lower()
    if any(k in text for k in ['stop','unsubscribe','remove me']): cls,sent='Opt Out','Negative'
    elif any(k in text for k in ['not interested','no thanks','do not contact']): cls,sent='Not Interested','Negative'
    elif any(k in text for k in ['meeting','call me','schedule','available','interested','send me',"let's talk"]): cls,sent='Interested','Positive'
    elif '?' in (body or '') or any(k in text for k in ['what','how','can you','do you','rate','pricing','guideline']): cls,sent='Question','Neutral'
    else: cls,sent='General Reply','Neutral'
    first=((contact or {}).get('name','') or 'there').split()[0]
    company=(prospect or {}).get('company','your company')
    if cls=='Interested': draft=f"""Hi {first},

Great to hear from you. I would be glad to connect and learn what {company} needs most right now. What time works best for a brief call?

Thanks,
Clay"""
    elif cls=='Question': draft=f"""Hi {first},

Thanks for the question. I am reviewing this now and will get you a clear answer. If you send the basic scenario details, I can be more specific.

Clay"""
    elif cls in ('Opt Out','Not Interested'): draft=f"""Hi {first},

Understood. Thank you for letting me know, and I will update my records accordingly.

Clay"""
    else: draft=f"""Hi {first},

Thank you for getting back to me. I am happy to help. What would be most useful for you right now?

Clay"""
    return cls,sent,'Re: '+(subject or 'Your message'),draft

def capture_inbound(uid,sender_email,sender_name,subject,body,received_at):
    sender_email=(sender_email or '').strip().lower()
    with db() as c:
        if uid and c.execute('select id from inbound_messages where provider_uid=?',(uid,)).fetchone(): return False
        contact=c.execute('select * from contacts where lower(email)=?',(sender_email,)).fetchone()
        prospect=c.execute('select * from prospects where id=?',(contact['prospect_id'],)).fetchone() if contact else None
        cd=dict(contact) if contact else {}; pd=dict(prospect) if prospect else {}
        cls,sent,ss,sr=classify_reply(subject,body,cd,pd)
        stopped=0
        if contact:
            ens=[r['id'] for r in c.execute("select id from sequence_enrollments where contact_id=? and status='Active'",(contact['id'],))]
            for en in ens:
                c.execute("update sequence_enrollments set status='Stopped',stopped_at=?,stop_reason='Inbound reply' where id=?",(NOW(),en));c.execute("update campaign_recipients set status='Suppressed',error='Sequence stopped: inbound reply',replied_at=? where sequence_enrollment_id=? and status='Queued'",(NOW(),en));stopped+=1
            c.execute("update campaign_recipients set replied_at=case when replied_at='' then ? else replied_at end where contact_id=? and status='Sent'",(NOW(),contact['id']))
            c.execute("update prospects set status=case when status in ('New','Contacted') then 'Replied' else status end,updated_at=? where id=?",(NOW(),contact['prospect_id']))
        c.execute("insert into inbound_messages(provider_uid,sender_email,sender_name,subject,body,received_at,contact_id,prospect_id,classification,sentiment,status,suggested_subject,suggested_reply,sequences_stopped,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,'Needs Attention',?,?,?,?,?)",(uid,sender_email,sender_name,subject,body,received_at,contact['id'] if contact else None,contact['prospect_id'] if contact else None,cls,sent,ss,sr,stopped,NOW(),NOW()))
    return True

@app.get('/api/inbox')
def inbox_list():
    with db() as c:
        rows=[dict(x) for x in c.execute("select i.*,p.company from inbound_messages i left join prospects p on p.id=i.prospect_id order by i.received_at desc,i.id desc")]
    return jsonify(messages=rows,summary={'needs_attention':sum(x['status']=='Needs Attention' for x in rows),'positive':sum(x['sentiment']=='Positive' for x in rows),'questions':sum(x['classification']=='Question' for x in rows),'sequences_stopped':sum(int(x['sequences_stopped'] or 0) for x in rows)})

@app.post('/api/inbox/manual')
def inbox_manual():
    d=request.json or {}; capture_inbound('manual-'+str(time.time_ns()),d.get('sender_email'),d.get('sender_name',''),d.get('subject',''),d.get('body',''),NOW());return jsonify(ok=True)

@app.post('/api/inbox/sync')
def inbox_sync():
    host=os.getenv('INBOX_IMAP_HOST','imap.gmail.com'); user=os.getenv('INBOX_EMAIL') or os.getenv('SMTP_USERNAME'); password=os.getenv('INBOX_APP_PASSWORD') or os.getenv('SMTP_PASSWORD')
    if not user or not password:return jsonify(error='Set INBOX_EMAIL and INBOX_APP_PASSWORD in Render. For Gmail, use an app password.'),400
    imported=0
    try:
        m=imaplib.IMAP4_SSL(host,int(os.getenv('INBOX_IMAP_PORT','993')));m.login(user,password);m.select(os.getenv('INBOX_FOLDER','INBOX'));_,data=m.search(None,'UNSEEN')
        for num in data[0].split()[-100:]:
            _,raw=m.fetch(num,'(RFC822)');msg=email_pkg.message_from_bytes(raw[0][1]);addr=parseaddr(msg.get('From',''));subject=str(msg.get('Subject',''))
            body=''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type()=='text/plain' and 'attachment' not in str(part.get('Content-Disposition','')): body=part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8','replace');break
            else: body=msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8','replace')
            uid=str(msg.get('Message-ID') or f'imap-{num.decode()}')
            if capture_inbound(uid,addr[1],addr[0],subject,body[:20000],str(msg.get('Date') or NOW())): imported+=1
        m.logout()
    except Exception as e:return jsonify(error='Mailbox sync failed: '+str(e)),400
    return jsonify(ok=True,imported=imported)

@app.post('/api/inbox/<int:iid>/resolve')
def inbox_resolve(iid):
    with db() as c:c.execute("update inbound_messages set status='Resolved',updated_at=? where id=?",(NOW(),iid))
    return jsonify(ok=True)

@app.post('/api/inbox/<int:iid>/queue-reply')
def inbox_queue_reply(iid):
    d=request.json or {}
    with db() as c:
        x=c.execute('select * from inbound_messages where id=?',(iid,)).fetchone()
        if not x:return jsonify(error='Reply not found'),404
        if not x['prospect_id']:return jsonify(error='This sender is not matched to a BrokerBeacon contact'),400
        c.execute("insert into outreach(prospect_id,channel,subject,body,status,created_at) values(?,'Email',?,?,'Draft',?)",(x['prospect_id'],d.get('subject') or x['suggested_subject'],d.get('body') or x['suggested_reply'],NOW()))
        c.execute("update inbound_messages set status='Response Drafted',updated_at=? where id=?",(NOW(),iid))
    return jsonify(ok=True)


@app.get('/api/intelligence')
def opportunity_intelligence():
    with db() as c:return jsonify(intelligence_dashboard(c))

@app.post('/api/intelligence/settings')
def opportunity_settings():
    blocked=reject_demo_write()
    if blocked:return blocked
    d=request.json or {}; weights=d.get('weights') or {}
    with db() as c:
        for key,value in weights.items():
            try:value=max(0,min(40,int(value)))
            except (TypeError,ValueError):continue
            c.execute('update scoring_settings set weight=?,updated_at=? where key=?',(value,NOW(),key))
    return jsonify(ok=True)

@app.post('/api/intelligence/rescore')
def opportunity_rescore():
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:
        data=intelligence_dashboard(c);save_snapshots(c,data['opportunities'],NOW())
    log('Opportunity intelligence recalculated',f"{len(data['opportunities'])} prospects")
    return jsonify(ok=True,updated=len(data['opportunities']))


GUIDE_SOURCES = {
    "fannie": {"label":"Fannie Mae", "domains":["selling-guide.fanniemae.com", "singlefamily.fanniemae.com"], "type":"Selling Guide"},
    "freddie": {"label":"Freddie Mac", "domains":["guide.freddiemac.com", "sf.freddiemac.com"], "type":"Seller/Servicer Guide"},
    "fha": {"label":"FHA", "domains":["hud.gov", "www.hud.gov"], "type":"HUD Handbook 4000.1 / FHA policy"},
    "va": {"label":"VA", "domains":["benefits.va.gov", "www.benefits.va.gov"], "type":"VA Lenders Handbook / circular"},
    "usda": {"label":"USDA", "domains":["rd.usda.gov", "www.rd.usda.gov"], "type":"USDA HB-1-3555 / Rural Development"},
}
_GUIDE_CACHE = {}

def _clean_web_text(value):
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))
    return re.sub(r'\s+', ' ', value).strip()

def _official_url(raw):
    raw = html.unescape(raw or '')
    if 'uddg=' in raw:
        try: raw = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get('uddg',[raw])[0]
        except Exception: pass
    return raw

def _allowed_guide_url(url, domains):
    try:
        host=urllib.parse.urlparse(url).netloc.lower().split(':')[0]
        return any(host==d or host.endswith('.'+d) for d in domains)
    except Exception:return False

def _extract_section(title):
    m=re.search(r'\b([A-Z]\d(?:-[\d.]+){1,4}|Section\s+[\d.]+|Chapter\s+\d+)\b', title or '', re.I)
    return m.group(1) if m else ''

def _fetch_official_excerpt(url, query):
    if url.lower().endswith('.pdf'): return ''
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 BrokerBeaconGuidelineSearch/1.0'})
        with urllib.request.urlopen(req,timeout=7) as r:
            ctype=(r.headers.get('content-type') or '').lower()
            if 'html' not in ctype:return ''
            raw=r.read(500000).decode('utf-8','ignore')
        raw=re.sub(r'(?is)<(script|style|nav|footer|header).*?>.*?</\1>',' ',raw)
        text=_clean_web_text(raw)
        terms=[x.lower() for x in re.findall(r'[A-Za-z0-9-]{4,}',query)[:8]]
        low=text.lower();positions=[low.find(t) for t in terms if low.find(t)>=0]
        pos=min(positions) if positions else 0
        start=max(0,pos-180);end=min(len(text),pos+520)
        excerpt=text[start:end].strip(' .,:;-')
        return (('…' if start else '')+excerpt+('…' if end<len(text) else ''))[:720]
    except Exception:return ''

def _result_record(source, result_url, title, snippet, query):
    if not _allowed_guide_url(result_url, source['domains']):
        return None
    excerpt=_fetch_official_excerpt(result_url,query) or snippet
    parsed=urllib.parse.urlparse(result_url)
    return {
        'program':source['label'],
        'source_type':source['type'],
        'title':title or source['type'],
        'section':_extract_section(title),
        'url':result_url,
        'display_url':parsed.netloc+parsed.path,
        'excerpt':excerpt,
    }

def _bing_rss_official_search(query, source, limit=5):
    """Primary search path. Bing RSS is simpler and more stable than scraping result-page HTML."""
    site_clause=' OR '.join('site:'+d for d in source['domains'])
    search_q=f'({site_clause}) {query}'
    url='https://www.bing.com/search?'+urllib.parse.urlencode({'q':search_q,'format':'rss'})
    req=urllib.request.Request(url,headers={
        'User-Agent':'Mozilla/5.0 BrokerBeaconGuidelineSearch/1.1',
        'Accept':'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
        'Accept-Language':'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req,timeout=12) as r:
        raw=r.read(1000000).decode('utf-8','ignore')
    items=re.findall(r'(?is)<item>(.*?)</item>',raw)
    out=[];seen=set()
    for item in items:
        def tag(name):
            m=re.search(rf'(?is)<{name}>(.*?)</{name}>',item)
            return html.unescape(re.sub(r'^<!\[CDATA\[|\]\]>$','',m.group(1).strip())) if m else ''
        result_url=tag('link').strip()
        title=_clean_web_text(tag('title'))
        snippet=_clean_web_text(tag('description'))
        if not result_url or result_url in seen: continue
        record=_result_record(source,result_url,title,snippet,query)
        if not record: continue
        seen.add(result_url);out.append(record)
        if len(out)>=limit: break
    return out

def _duckduckgo_official_search(query, source, limit=5):
    """Secondary search path with parsers for both current HTML and Lite layouts."""
    domains=source['domains'];site_clause=' OR '.join('site:'+d for d in domains)
    search_q=f'({site_clause}) {query}'
    endpoints=[
        'https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':search_q}),
        'https://lite.duckduckgo.com/lite/?'+urllib.parse.urlencode({'q':search_q}),
    ]
    last_error=None
    for url in endpoints:
        try:
            req=urllib.request.Request(url,headers={
                'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36',
                'Accept-Language':'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req,timeout=12) as r: raw=r.read(1000000).decode('utf-8','ignore')
            out=[];seen=set()
            # Current HTML result links and Lite result links.
            links=re.findall(r'(?is)<a[^>]+(?:class="[^"]*(?:result__a|result-link)[^"]*"[^>]*)?href="([^"]+)"[^>]*>(.*?)</a>',raw)
            for href,title_html in links:
                result_url=_official_url(href)
                title=_clean_web_text(title_html)
                if not title or not result_url or result_url in seen: continue
                # Locate a nearby snippet without depending on one exact wrapper structure.
                idx=raw.find(href)
                nearby=raw[idx:idx+2500] if idx>=0 else ''
                sm=re.search(r'(?is)class="[^"]*(?:result__snippet|result-snippet)[^"]*"[^>]*>(.*?)</(?:a|div|td)>',nearby)
                snippet=_clean_web_text(sm.group(1) if sm else '')
                record=_result_record(source,result_url,title,snippet,query)
                if not record: continue
                seen.add(result_url);out.append(record)
                if len(out)>=limit:return out
            if out:return out
        except Exception as exc:
            last_error=exc
    if last_error: raise last_error
    return []

def _search_official_source(query, source, limit=5):
    errors=[]
    for backend in (_bing_rss_official_search,_duckduckgo_official_search):
        try:
            results=backend(query,source,limit)
            if results:return results,backend.__name__.replace('_official_search','').strip('_')
        except Exception as exc:
            errors.append(f'{backend.__name__}: {type(exc).__name__}')
    if errors: raise RuntimeError('; '.join(errors))
    return [],''

def _guide_fallback_links(keys, query):
    encoded=urllib.parse.quote_plus(query)
    links=[]
    bases={
      'fannie':f'https://selling-guide.fanniemae.com/search?query={encoded}',
      'freddie':f'https://guide.freddiemac.com/app/guide/search?query={encoded}',
      'fha':'https://www.hud.gov/hud-partners/single-family-handbook-policy',
      'va':'https://www.benefits.va.gov/warms/pam26_7.asp',
      'usda':'https://www.rd.usda.gov/resources/directives/handbooks',
    }
    for k in keys:links.append({'label':GUIDE_SOURCES[k]['label'],'url':bases[k]})
    return links


def _extract_response_text(payload):
    if isinstance(payload, dict):
        if payload.get('output_text'):
            return str(payload['output_text'])
        for item in payload.get('output', []):
            for content in item.get('content', []):
                if content.get('type') == 'output_text' and content.get('text'):
                    return content['text']
    return ''

def _citation_payload(results, limit=4):
    out=[]
    seen=set()
    for r in results:
        key=(r.get('program'),r.get('section'),r.get('title'))
        if key in seen: continue
        seen.add(key)
        out.append({'program':r.get('program',''),'section':r.get('section',''),'title':r.get('title',''),'url':r.get('url','')})
        if len(out)>=limit: break
    return out

def _fallback_plain_answer(query, results):
    q=query.lower()
    top=results[0] if results else None
    if not top:
        return {'classification':'unclear','verdict':'I do not have enough indexed guidance to answer that reliably.','explanation':'No sufficiently close official section was retrieved. Select an agency or use a shorter, more specific topic.','conditions':[],'needed_information':['Loan program','Occupancy','Property type or unit count','Transaction type'],'cautions':['Do not treat a missing search result as an approval.'],'citations':[],'basis':'No controlling source match was found.','confidence':'Limited','broker_script':'I do not have enough controlling guidance yet to give the broker a reliable answer. Let me confirm the loan program, occupancy, property type, and transaction type first.','executive_summary':'There is not enough indexed evidence to give the broker a dependable answer yet. Collect the missing scenario facts and rerun the analysis.','confidence_reasons':['No sufficiently close controlling section was retrieved.'],'related_topics':['Occupancy requirements','Property eligibility','Transaction type'],'follow_up_options':['Fannie Mae','Freddie Mac','FHA','VA','USDA']}
    program=top.get('program','the selected program'); section=top.get('section',''); title=top.get('title','the retrieved section')
    citations=_citation_payload(results)
    text=' '.join(re.sub(r'</?mark>','',r.get('excerpt') or '',flags=re.I) for r in results[:8]).lower()
    # Common, high-value interpretations anchored to indexed section language.
    if 'gift' in q and ('fannie' in q or program=='Fannie Mae'):
        if 'investment' in q:
            return {'classification':'no','verdict':'No — Fannie Mae gift funds are not supported for this investment-property scenario.','explanation':'The indexed Personal Gifts section addresses gift funds for eligible principal residences and second homes. Because the scenario is an investment property, the retrieved guidance does not support using gift funds for the required borrower funds.','conditions':['The conclusion assumes the property will be classified as an investment property.','A gift of equity is a separate concept and should be reviewed under its own section.'],'needed_information':['Confirm final occupancy classification','Confirm whether the funds are a personal gift or gift of equity','Review the AUS findings and applicable product matrix'],'cautions':['Verify current minimum-contribution rules and any UHM or investor overlay.'],'citations':citations,'basis':f"Primary support: {program} {section or title}, {title}.",'confidence':'High','broker_script':'For a Fannie Mae investment property, the indexed gift-fund guidance does not support using personal gift funds for the required borrower contribution. Let’s confirm occupancy, AUS findings, and whether this is actually a gift of equity before we commit.','executive_summary':'Treat personal gift funds as unavailable for the required borrower contribution on this Fannie Mae investment-property scenario unless the transaction facts change.','confidence_reasons':['Direct match to Fannie Mae B3-4.3-04 Personal Gifts.','The indexed language limits the relevant gift treatment to eligible principal residences and second homes.','No conflicting indexed Fannie guidance was retrieved.'],'related_topics':['Gifts of Equity','Minimum Borrower Contribution','Investment Property Reserves','Interested Party Contributions'],'follow_up_options':['Primary residence','Second home','Investment property','Gift of equity']}
        return {'classification':'conditional','verdict':'Yes — Fannie Mae generally permits gift funds, but only for eligible transactions and with required documentation.','explanation':'The indexed Personal Gifts guidance supports gift funds for eligible principal-residence and second-home transactions. Whether the funds can cover the entire required contribution depends on occupancy, property units, LTV, and the specific transaction.','conditions':['Eligible donor and acceptable gift letter','Document the donor’s ability to give the funds and the transfer','Principal residence or eligible second home','Meet any borrower minimum-contribution requirement'],'needed_information':['Occupancy','Number of units','Purchase price and LTV','Source and type of gift funds'],'cautions':['Investment-property treatment is different.','A gift of equity has separate requirements.'],'citations':citations,'basis':f"Primary support: {program} {section or title}, {title}.",'confidence':'High','broker_script':'Gift funds can generally work on an eligible Fannie Mae primary residence or second home when the donor, gift letter, transfer, and any minimum borrower contribution requirements are documented. Tell me the occupancy, unit count, and LTV and I can narrow it down.','executive_summary':'You can tell the broker gift funds are generally acceptable for eligible Fannie Mae primary residences and second homes, but confirm occupancy, units, LTV, AUS findings, and the borrower-contribution requirement before committing.','confidence_reasons':['Direct match to Fannie Mae B3-4.3-04 Personal Gifts.','The retrieved section specifically addresses eligible principal residences and second homes.','A corroborating Gifts of Equity section was also retrieved.'],'related_topics':['Gifts of Equity','Minimum Borrower Contribution','Interested Party Contributions','Reserves'],'follow_up_options':['Primary residence','Second home','Investment property','1-unit','2–4 units']}
    negative=any(x in text for x in ['not permitted','not allowed','ineligible','may not','cannot be used','must not'])
    positive=any(x in text for x in ['is permitted','are permitted','may be used','is allowed','are allowed','eligible for'])
    excerpt=re.sub(r'\s+',' ',re.sub(r'</?mark>','',top.get('excerpt') or '',flags=re.I)).strip()
    if len(excerpt)>300: excerpt=excerpt[:297].rsplit(' ',1)[0]+'…'
    if re.search(r'\b(can|may|is|are|does|do)\b',q):
        if negative and not positive: classification,verdict='no','The retrieved guidance points to no.'
        elif positive and not negative: classification,verdict='yes','The retrieved guidance points to yes, subject to its conditions.'
        else: classification,verdict='conditional','It may be possible, but the answer depends on transaction details not fully resolved by the retrieved excerpts.'
    else: classification,verdict='conditional',f'The most relevant rule appears to be {program} {section or title}.'
    return {'classification':classification,'verdict':verdict,'explanation':excerpt or 'Open the cited official source to review the controlling language and exceptions.','conditions':[],'needed_information':['Confirm the exact transaction facts that affect this rule.'],'cautions':['Review the complete cited section, effective date, AUS findings, and overlays.'],'citations':citations,'basis':f"Primary source: {program}{' · '+section if section else ''} · {title}.",'confidence':'Moderate' if classification!='unclear' else 'Limited','broker_script':f"The most relevant indexed guidance is {program} {section or title}. I would explain that the answer depends on the exact transaction facts and confirm the complete cited section before making a commitment.",'executive_summary':'Use the cited section as the starting point, but do not give the broker a definitive answer until the transaction facts and full controlling language are confirmed.','confidence_reasons':['A relevant official section was retrieved.','The excerpt does not resolve every transaction-specific condition.'],'related_topics':['Occupancy requirements','Documentation requirements','AUS findings'],'follow_up_options':['Primary residence','Second home','Investment property','Purchase','Refinance']}

def _plain_english_guideline_answer(query, results):
    fallback=_fallback_plain_answer(query, results)
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key or not results:
        return fallback
    evidence=[]
    for i,r in enumerate(results[:10],1):
        excerpt=re.sub(r'</?mark>','',r.get('excerpt') or '',flags=re.I)
        evidence.append(f"SOURCE {i}: {r.get('program')} | {r.get('section') or 'no section'} | {r.get('title')} | {r.get('url')}\n{excerpt[:1100]}")
    prompt=("You are Ash Underwriter in a wholesale mortgage AE tool. Give a concise, human answer using ONLY the supplied official-guide excerpts. "
            "Do not answer from memory. Do not invent a limit, exception, approval, or underwriting rule. If the evidence does not resolve the question, say what facts are missing. "
            "Return strict JSON only with these keys: classification, verdict, explanation, executive_summary, conditions, needed_information, cautions, citations, basis, confidence, confidence_reasons, broker_script, follow_up_options, related_topics. "
            "classification must be yes, no, conditional, or unclear. verdict must be one direct sentence, ideally beginning Yes, No, or It depends. "
            "explanation must be 2-4 short sentences in ordinary language. conditions, needed_information, and cautions must be arrays of short strings. "
            "citations must be an array of up to 4 objects with program, section, title, and url copied from the supplied sources. confidence must be High, Moderate, or Limited. executive_summary must be a one- or two-sentence bottom-line recommendation for an AE. confidence_reasons must be an array of 1-4 evidence-based reasons. broker_script must be 1-3 natural sentences an AE could say directly to a broker. follow_up_options must be an array of 2-5 short factual choices that would materially refine the answer. related_topics must be an array of 2-6 closely related guideline topics. "
            "The answer must appear before caveats. Distinguish personal gifts from gifts of equity when relevant.\n\nQUESTION:\n"+query+"\n\n"+'\n\n'.join(evidence))
    try:
        body=json.dumps({'model':os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini'),'input':prompt,'max_output_tokens':700}).encode()
        req=urllib.request.Request('https://api.openai.com/v1/responses',data=body,method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=22) as resp: raw=json.loads(resp.read().decode())
        text=_extract_response_text(raw).strip(); text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S)
        parsed=json.loads(text)
        required=['classification','verdict','explanation','basis']
        if all(parsed.get(k) for k in required):
            parsed['classification']=parsed.get('classification','unclear') if parsed.get('classification') in {'yes','no','conditional','unclear'} else 'unclear'
            parsed['confidence']=parsed.get('confidence','Moderate') if parsed.get('confidence') in {'High','Moderate','Limited'} else 'Moderate'
            for key_name in ['conditions','needed_information','cautions','citations','follow_up_options','confidence_reasons','related_topics']:
                if not isinstance(parsed.get(key_name),list): parsed[key_name]=[]
            return parsed
    except Exception as exc:
        app.logger.warning('Ash Underwriter reasoner fallback: %s',exc)
    return fallback

@app.get('/api/guidelines/search')
def guideline_search():
    query=(request.args.get('q') or '').strip()
    program=(request.args.get('program') or 'all').lower()
    if len(query)<3:return jsonify({'error':'Enter at least three characters.'}),400
    if len(query)>240:return jsonify({'error':'Keep the search under 240 characters.'}),400
    valid={'all','fannie','freddie','fha','va','usda'}
    if program not in valid:return jsonify({'error':'Unknown loan program.'}),400
    with db() as c:
        results=search_guideline_index(c,query,program,24)
        st=guideline_index_stats(c)
    labels={'all':'all five agency guides','fannie':'Fannie Mae','freddie':'Freddie Mac','fha':'FHA','va':'VA','usda':'USDA'}
    plain_answer=_plain_english_guideline_answer(query,results)
    return jsonify({'query':query,'program':program,'program_label':labels[program],
      'plain_answer':plain_answer,
      'results':results,'index_total':st['total'],'index_programs':st['programs'],
      'fallback_links':_guide_fallback_links(list(GUIDE_SOURCES) if program=='all' else [program],query),
      'warning':'' if results else 'No indexed section matched. Try the core topic and select one agency, or use the official-source links.'})

@app.get('/api/guidelines/index-status')
def guideline_index_status():
    with db() as c:return jsonify(guideline_index_stats(c))

@app.post('/api/guidelines/reindex')
def guideline_reindex():
    blocked=reject_demo_write()
    if blocked:return blocked
    with db() as c:
        seed_index(c)
        added=index_fha_pdf(c,Path(__file__).with_name('fha_handbook_4000_1.pdf'))
        st=guideline_index_stats(c)
    return jsonify(ok=True,fha_pages=added,**st)


def _prod_month_cutoff(months):
    if not months or months <= 0:
        return ''
    d = datetime.now().replace(day=1) - timedelta(days=31 * (months - 1))
    return d.strftime('%Y-%m')


def _prod_norm_loan_type(value):
    v = (value or '').strip().lower()
    if 'conventional' in v or 'conforming' in v:
        return 'Conventional'
    if 'fha' in v:
        return 'FHA'
    if re.search(r'(^|\W)va($|\W)', v):
        return 'VA'
    if 'usda' in v or 'rural' in v:
        return 'USDA'
    if 'jumbo' in v:
        return 'Jumbo'
    if 'heloc' in v or 'home equity' in v:
        return 'HELOC'
    if 'non-qm' in v or 'non qm' in v:
        return 'Non-QM'
    return (value or 'Other').strip().title() or 'Other'


def _prod_norm_purpose(value):
    v = (value or '').strip().lower()
    if 'purchase' in v:
        return 'Purchase'
    if 'cash' in v and 'out' in v:
        return 'Cash-Out Refinance'
    if 'refi' in v or 'refinance' in v:
        return 'Rate/Term Refinance'
    return (value or 'Other').strip().title() or 'Other'


def _prod_value(row, *names):
    normalized = {re.sub(r'[^a-z0-9]', '', str(k).lower()): v for k, v in row.items()}
    for name in names:
        key = re.sub(r'[^a-z0-9]', '', name.lower())
        if key in normalized and str(normalized[key]).strip():
            return str(normalized[key]).strip()
    return ''


def _prod_num(value, integer=False):
    text = re.sub(r'[^0-9.\-]', '', str(value or '0'))
    try:
        number = float(text or 0)
        return int(round(number)) if integer else number
    except ValueError:
        return 0 if integer else 0.0


def _prod_ash_summary(companies, totals):
    if not companies:
        return {
            'headline': 'No imported production data yet',
            'summary': 'Import an approved production CSV to rank companies, loan officers, product mix, units, and volume.',
            'recommendations': ['Use the provided template or map an approved provider export to the supported fields.'],
        }
    top = companies[0]
    rec = [f"Lead with {top.get('top_loan_type') or 'the dominant product mix'} when approaching {top['company']}."]
    if len(companies) > 1:
        rec.append(f"Compare {top['company']} with {companies[1]['company']} before planning territory travel or outreach.")
    rec.append('Use LO-level rankings only when the imported source includes named loan officers or NMLS identifiers.')
    return {
        'headline': f"{top['company']} leads the imported production view",
        'summary': (
            f"The selected period contains {totals['units']:,} funded unit(s) and ${totals['volume']:,.0f} "
            f"in volume across {totals['companies']} compan{'ies' if totals['companies'] != 1 else 'y'}. "
            f"{top['company']} represents the largest imported opportunity at ${top['volume']:,.0f}."
        ),
        'recommendations': rec,
    }


@app.get('/api/production/template')
def production_template():
    return send_file(
        Path(__file__).with_name('production_import_template.csv'),
        as_attachment=True,
        download_name='brokerbeacon_production_import_template.csv',
    )


@app.post('/api/production/import')
def production_import():
    blocked = reject_demo_write()
    if blocked:
        return blocked
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename.lower().endswith('.csv'):
        return jsonify(error='Choose a CSV file.'), 400
    try:
        raw = uploaded.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return jsonify(error='The CSV must use UTF-8 encoding.'), 400
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return jsonify(error='The CSV contains no data rows.'), 400

    parsed, errors = [], []
    for idx, row in enumerate(rows, 2):
        company = _prod_value(row, 'company', 'company name', 'lender name', 'broker company', 'institution name')
        period = _prod_value(row, 'period_month', 'period month', 'month', 'activity year month', 'reporting month')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', period):
            period = period[:7]
        if re.fullmatch(r'\d{6}', period):
            period = period[:4] + '-' + period[4:]
        if not company or not re.fullmatch(r'\d{4}-\d{2}', period):
            errors.append(f'Row {idx}: company and period_month (YYYY-MM) are required.')
            continue
        units = _prod_num(_prod_value(row, 'units', 'loan count', 'count', 'funded units', 'originations'), True)
        volume = _prod_num(_prod_value(row, 'volume', 'loan volume', 'funded volume', 'amount', 'loan amount'))
        if units <= 0 and volume > 0:
            units = 1
        if units <= 0 and volume <= 0:
            errors.append(f'Row {idx}: units or volume is required.')
            continue
        source = _prod_value(row, 'source_name', 'source', 'provider', 'data source') or 'Production CSV Import'
        data_as_of = _prod_value(row, 'data_as_of', 'data as of', 'as of date', 'freshness date') or datetime.now().date().isoformat()
        parsed.append({
            'company': company,
            'company_nmls': _prod_value(row, 'company_nmls', 'company nmls', 'institution nmls', 'lei'),
            'lo_name': _prod_value(row, 'lo_name', 'loan officer', 'loan officer name', 'originator name'),
            'lo_nmls': _prod_value(row, 'lo_nmls', 'lo nmls', 'loan originator nmls', 'originator nmls'),
            'period_month': period,
            'loan_type': _prod_norm_loan_type(_prod_value(row, 'loan_type', 'loan type', 'product', 'program')),
            'purpose': _prod_norm_purpose(_prod_value(row, 'purpose', 'loan purpose', 'transaction type')),
            'units': units,
            'volume': volume,
            'source_name': source,
            'data_as_of': data_as_of,
        })
    if not parsed:
        return jsonify(error='No valid rows were found.', details=errors[:12]), 400

    source_name = parsed[0]['source_name']
    data_as_of = max(item['data_as_of'] for item in parsed)
    with db() as conn:
        old_ids = [r[0] for r in conn.execute(
            'select id from production_imports where source_name=? and data_as_of=?',
            (source_name, data_as_of),
        )]
        if old_ids:
            marks = ','.join('?' * len(old_ids))
            conn.execute(f'delete from production_records where import_id in ({marks})', old_ids)
            conn.execute(f'delete from production_imports where id in ({marks})', old_ids)
        cur = conn.execute(
            'insert into production_imports(source_name,source_type,data_as_of,file_name,rows_imported,created_at) values(?,?,?,?,?,?)',
            (source_name, 'CSV', data_as_of, uploaded.filename, len(parsed), NOW()),
        )
        import_id = cur.lastrowid
        prospect_map = {
            re.sub(r'[^a-z0-9]', '', r['company'].lower()): r['id']
            for r in conn.execute('select id,company from prospects')
        }
        for item in parsed:
            prospect_id = prospect_map.get(re.sub(r'[^a-z0-9]', '', item['company'].lower()))
            conn.execute(
                'insert into production_records(import_id,prospect_id,company,company_nmls,lo_name,lo_nmls,period_month,loan_type,purpose,units,volume,source_name,data_as_of,created_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    import_id, prospect_id, item['company'], item['company_nmls'], item['lo_name'], item['lo_nmls'],
                    item['period_month'], item['loan_type'], item['purpose'], item['units'], item['volume'],
                    item['source_name'], item['data_as_of'], NOW(),
                ),
            )
    return jsonify(
        ok=True,
        rows_imported=len(parsed),
        rows_skipped=len(rows) - len(parsed),
        source_name=source_name,
        data_as_of=data_as_of,
        errors=errors[:12],
    )


@app.get('/api/production/summary')
def production_summary():
    try:
        months = max(0, min(60, int(request.args.get('months', '12'))))
    except ValueError:
        months = 12
    search = (request.args.get('search') or '').strip().lower()
    cutoff = _prod_month_cutoff(months)
    where, params = [], []
    if cutoff:
        where.append('period_month>=?')
        params.append(cutoff)
    if search:
        where.append('(lower(company) like ? or lower(lo_name) like ?)')
        params.extend([f'%{search}%', f'%{search}%'])
    clause = ' where ' + ' and '.join(where) if where else ''
    with db() as conn:
        companies = [dict(r) for r in conn.execute(
            f'select company,sum(units) units,sum(volume) volume,max(data_as_of) data_as_of,max(source_name) source_label from production_records{clause} group by company order by volume desc',
            params,
        )]
        totals_row = conn.execute(
            f'select count(distinct company),coalesce(sum(units),0),coalesce(sum(volume),0),max(data_as_of) from production_records{clause}',
            params,
        ).fetchone()
        for company in companies:
            sub_where = list(where) + ['company=?']
            sub_params = list(params) + [company['company']]
            sub_clause = ' where ' + ' and '.join(sub_where)
            top = conn.execute(
                f'select loan_type,sum(volume) v from production_records{sub_clause} group by loan_type order by v desc limit 1',
                sub_params,
            ).fetchone()
            company['average_loan'] = company['volume'] / company['units'] if company['units'] else 0
            company['top_loan_type'] = top[0] if top else 'Other'
            company['top_mix_pct'] = round((top[1] / company['volume'] * 100) if top and company['volume'] else 0)
        totals = {
            'companies': int(totals_row[0] or 0),
            'units': int(totals_row[1] or 0),
            'volume': float(totals_row[2] or 0),
        }
        totals['average_loan'] = totals['volume'] / totals['units'] if totals['units'] else 0
        latest = conn.execute('select source_name,data_as_of,created_at from production_imports order by id desc limit 1').fetchone()
    freshness = {
        'label': f"As of {latest['data_as_of']} · {latest['source_name']}" if latest else 'No data imported',
        'data_as_of': latest['data_as_of'] if latest else '',
        'source': latest['source_name'] if latest else '',
    }
    return jsonify(
        totals=totals,
        companies=companies,
        freshness=freshness,
        ash=_prod_ash_summary(companies, totals),
        period_months=months,
    )


@app.get('/api/production/company')
def production_company():
    company = (request.args.get('company') or '').strip()
    if not company:
        return jsonify(error='Company required'), 400
    try:
        months = max(0, min(60, int(request.args.get('months', '12'))))
    except ValueError:
        months = 12
    cutoff = _prod_month_cutoff(months)
    where, params = ['company=?'], [company]
    if cutoff:
        where.append('period_month>=?')
        params.append(cutoff)
    clause = ' where ' + ' and '.join(where)
    with db() as conn:
        total = conn.execute(
            f'select coalesce(sum(units),0),coalesce(sum(volume),0),max(data_as_of),max(source_name) from production_records{clause}',
            params,
        ).fetchone()
        loan_types = [dict(r) for r in conn.execute(
            f'select loan_type,sum(units) units,sum(volume) volume from production_records{clause} group by loan_type order by volume desc',
            params,
        )]
        monthly = [dict(r) for r in conn.execute(
            f'select period_month month,sum(units) units,sum(volume) volume from production_records{clause} group by period_month order by period_month',
            params,
        )]
        loan_officers = [dict(r) for r in conn.execute(
            f"select lo_name,lo_nmls,sum(units) units,sum(volume) volume from production_records{clause} and trim(lo_name)<>'' group by lo_name,lo_nmls order by volume desc",
            params,
        )]
        for lo in loan_officers:
            top = conn.execute(
                f"select loan_type,sum(volume) v from production_records{clause} and lo_name=? and coalesce(lo_nmls,'')=? group by loan_type order by v desc limit 1",
                params + [lo['lo_name'], lo['lo_nmls'] or ''],
            ).fetchone()
            lo['top_loan_type'] = top[0] if top else 'Other'
    totals = {'units': int(total[0] or 0), 'volume': float(total[1] or 0)}
    totals['average_loan'] = totals['volume'] / totals['units'] if totals['units'] else 0
    top = loan_types[0] if loan_types else {'loan_type': 'Other', 'units': 0, 'volume': 0}
    share = (top['volume'] / totals['volume'] * 100) if totals['volume'] else 0
    ash = {
        'headline': f"{top['loan_type']} is the leading imported product for {company}",
        'summary': (
            f"{company} shows {totals['units']:,} unit(s) and ${totals['volume']:,.0f} in imported production. "
            f"{top['loan_type']} represents approximately {share:.0f}% of volume in this view."
        ),
        'recommendations': [
            f"Lead with a {top['loan_type']}-specific value proposition.",
            (f"Prioritize {loan_officers[0]['lo_name']} as the highest-volume named LO in this source." if loan_officers else 'Import an approved LO-level source to identify individual producer targets.'),
            'Compare imported total production with internal UHM fundings before estimating wallet share.',
        ],
    }
    return jsonify(
        company=company,
        totals=totals,
        loan_types=loan_types,
        monthly=monthly,
        loan_officers=loan_officers,
        source_label=total[3] or 'Imported data',
        data_as_of=total[2] or '',
        period_label='All imported data' if not months else f'Trailing {months} months',
        ash=ash,
    )


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

def _scout_autopilot_worker():
    """Wake periodically while the Render service is running; database timing and budgets remain authoritative."""
    threading.Event().wait(60)
    while True:
        try:_run_scout_autopilot(force=False)
        except Exception as exc:print(f'Scout Autopilot worker: {type(exc).__name__}: {str(exc)[:160]}',flush=True)
        threading.Event().wait(900)

if os.getenv('ENABLE_SCOUT_AUTOPILOT_WORKER','1')=='1':
    threading.Thread(target=_scout_autopilot_worker,name='brokerbeacon-scout-autopilot',daemon=True).start()

if __name__=="__main__":
    init()
    app.run(host=os.getenv("HOST","127.0.0.1"), port=int(os.getenv("PORT","5000")), debug=False)
