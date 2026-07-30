# BrokerBeacon AI
# Copyright © 2026 Clay Carr. All rights reserved.
# BrokerBeacon AI™ is a trademark of Clay Carr.
from flask import Flask, request, jsonify, render_template_string, Response, send_file, make_response, redirect
import sqlite3, io, csv, os, json, re, uuid, smtplib, ssl, urllib.parse, urllib.request, base64, html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from migrations import run_migrations
from intelligence import intelligence_dashboard, save_snapshots
from revenue_intelligence import executive_dashboard, log_revenue_event
from voice_agent import configured as voice_configured, create_twilio_call, human_greeting, voicemail, twiml, say, appointment_slots, ai_reply
from guideline_index import seed_index, index_fha_pdf, search as search_guideline_index, stats as guideline_index_stats

app = Flask(__name__)
BUILD_VERSION = "14.0"
BUILD_NAME = "SIGNAL GLASS"
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
.coach-grid{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:11px}.coach-block{border:1px solid #e0e7f0;background:#f8fafc;border-radius:11px;padding:12px}.coach-block b{display:block;margin-bottom:5px;color:#0d2347;font-size:11px;text-transform:uppercase;letter-spacing:.07em}.coach-block p{margin:0;line-height:1.48;font-size:13px}.coach-opening{grid-column:1/-1;border-left:4px solid #174ea6;background:#f4f8fd}.coach-reasons{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.coach-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding-top:13px;border-top:1px solid #e4eaf2}.