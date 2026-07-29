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
BUILD_VERSION = "8.10.1"
BUILD_NAME = "ASH UNDERWRITER DEPLOYMENT FIX"
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
</style></head><body><div class="app"><aside><div class="brand">Broker<span>Beacon</span> AI</div><div class="version">VERSION 8.10.1 · ASH UNDERWRITER DEPLOYMENT FIX</div><nav><button class="active" data-v="dashboard">✦ Command Center</button><button data-v="salescoach">◈ Ash Sales Coach</button><button data-v="voiceagent">☎ AI Voice Agent</button><button data-v="copilot">✦ AI Copilot</button><button data-v="daily">⚡ Daily Plan</button><button data-v="prospects">◉ Prospects</button><button data-v="outreach">✎ Outreach</button><button data-v="campaigns">✉ Campaigns</button><button data-v="inbox">↩ Reply Inbox</button><button data-v="intelligence">◆ Opportunity Intelligence</button><button data-v="templates">▤ Templates & Sequences</button><button data-v="pipeline">▦ Pipeline</button><button data-v="followups">✓ Follow-ups</button><button data-v="territory">⌖ Territory</button><button data-v="guidelines">▣ Loan Guidelines</button><button data-v="boss">◆ Executive View</button><button data-v="integrations">⚙ Integrations</button></nav></aside><main><div class="top"><div><small>AI OPERATING SYSTEM FOR WHOLESALE AES</small><h1 id="title">Command Center</h1></div><div class="actions"><span class="today-chip" id="todayChip"></span><button class="btn theme-toggle" id="themeToggle" type="button" aria-label="Toggle dark mode">◐ Theme</button><button class="btn" id="import">Compliant Import</button><a class="btn" href="/api/export">Export CSV</a><button class="btn primary" id="add">+ Add Prospect</button></div></div>
<section id="dashboard" class="view active">
<div class="command-hero">
  <div class="command-copy"><div class="kicker">ASH · DAILY REVENUE COMMAND</div><h2>Good morning, Clay. Here is the fastest path to more business today.</h2><p>BrokerBeacon ranks the accounts, explains the opportunity, prepares the outreach, and converts the plan into action.</p></div>
  <button class="btn start-day" id="startMyDayBtn"><span>▶</span> Start My Day</button>
</div>
<div class="command-kpis">
  <div class="command-kpi"><span>Projected pipeline potential</span><strong id="mcPotential">$0</strong><small>Model-based, not recorded revenue</small></div>
  <div class="command-kpi"><span>Priority calls</span><strong id="mcCalls">0</strong><small>Highest-value contacts today</small></div>
  <div class="command-kpi"><span>Meeting opportunities</span><strong id="mcMeetingsNeeded">0</strong><small>Recommended next conversations</small></div>
  <div class="command-kpi"><span>Application opportunities</span><strong id="mcApps">0</strong><small>Projected from current funnel</small></div>
</div>
<div class="mission-grid">
  <div class="panel mission-span-2 morning-panel"><div class="profile-head"><div><div class="kicker">MORNING BRIEF</div><h3>What deserves attention now</h3></div><button class="btn smallbtn" onclick="missionControl()">Refresh</button></div><div id="mcBrief" class="brief-card muted">Loading…</div><div id="mcBriefFacts" class="brief-facts"></div></div>
  <div class="panel ash-panel"><div class="kicker">ASH RECOMMENDS</div><h3>Your next three moves</h3><div id="mcRecommendations" class="recommendations"></div></div>
  <div class="panel mission-span-2"><div class="profile-head"><div><h3>Today’s ranked accounts</h3><p class="muted">Opportunity score, relationship health, and recommended action.</p></div><button class="btn smallbtn" onclick="show('daily')">Open full plan</button></div><div id="mcPriorities" class="priority"></div></div>
  <div class="panel"><h3>Broker health</h3><div id="mcHealth" class="health-grid"></div></div>
  <div class="panel"><h3>New broker alerts</h3><div id="mcAlerts" class="activity"></div></div>
  <div class="panel"><h3>Relationships at risk</h3><div id="mcAtRisk" class="activity"></div></div>
  <div class="panel"><h3>Product opportunities</h3><div id="mcProducts" class="bars"></div></div>
  <div class="panel"><h3>This week’s goals</h3><div id="mcGoals"></div></div>
  <div class="panel"><h3>Campaign performance</h3><div id="mcCampaigns"></div><button class="btn smallbtn" onclick="show('campaigns')">Manage campaigns</button></div>
</div></section>
<section id="copilot" class="view"><div class="hero"><div><div class="kicker">BROKERBEACON COPILOT</div><h2>Ask your territory a question. Get a ranked, explainable answer.</h2><p>The Copilot uses your BrokerBeacon prospect, pipeline, follow-up, and activity data. It does not invent email opens, licensing events, or production data that are not stored in your database.</p></div><span class="pill">Database-grounded</span></div><div class="copilot-layout" style="margin-top:14px"><div class="panel"><h3>Ask BrokerBeacon</h3><div class="askbox"><input id="copilotQuestion" placeholder="Example: Who should I call first today?"><button class="btn primary" id="askCopilot">Ask</button></div><div class="suggestions"><button class="btn smallbtn copilotPrompt">Who should I call first today?</button><button class="btn smallbtn copilotPrompt">Which Charlotte prospects need attention?</button><button class="btn smallbtn copilotPrompt">Show overdue follow-ups</button><button class="btn smallbtn copilotPrompt">Find high-score government-loan prospects</button></div><div id="copilotAnswer" class="answer muted" style="margin-top:16px">Ask a question to generate a prioritized answer from your current database.</div></div><div class="panel"><h3>Morning briefing</h3><div id="morningBrief"><div class="empty">Loading briefing…</div></div><button class="btn" style="margin-top:12px" onclick="copilotBrief()">Refresh briefing</button></div></div></section><section id="daily" class="view"><div class="hero"><div><div class="kicker">AI-GUIDED WORKDAY</div><h2>Your five best actions, ranked and ready.</h2><p>BrokerBeacon combines opportunity score, pipeline stage, follow-up urgency, and recent activity to create a focused daily call plan.</p></div><button class="btn primary" onclick="dailyPlan()">Refresh plan</button></div><div class="metrics"><div class="metric"><span>Calls logged today</span><strong id="dcalls">0</strong></div><div class="metric"><span>Emails logged today</span><strong id="demails">0</strong></div><div class="metric"><span>Conversations this week</span><strong id="dconvos">0</strong></div><div class="metric"><span>Meetings created this week</span><strong id="dmeetings">0</strong></div></div><div class="plan-grid"><div class="panel"><div class="profile-head"><div><h3>Recommended action queue</h3><p class="muted">Highest-value unfinished actions appear first.</p></div><span class="pill">Top 5</span></div><div id="dailyQueue"></div></div><div><div class="panel"><h3>Daily activity goal</h3><div class="goalring" id="goalring" style="--goal:0"><div><span><strong id="goalPct">0%</strong><br><small class="muted">10 actions</small></span></div></div><div id="goalText" class="muted" style="text-align:center;margin-top:12px"></div></div><div class="panel" style="margin-top:14px"><h3>Recent sales activity</h3><div id="salesTimeline" class="timeline"></div></div></div></div></section><section id="prospects" class="view"><div class="filters"><input id="search" placeholder="Search company, owner, city"><select id="state"><option>All</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select><select id="signal"><option>All</option><option>Newly Licensed</option><option>Team Growth</option><option>VA/FHA Fit</option><option>Imported</option><option>Manual</option><option>Verified Public Record</option><option>Needs Verification</option></select><select id="pstatus"><option>All statuses</option><option>New</option><option>Contacted</option><option>Replied</option><option>Meeting</option><option>Approved</option></select><select id="minscore"><option value="0">Any score</option><option value="70">70+</option><option value="80">80+</option><option value="90">90+</option></select></div><div class="panel" style="overflow:auto"><table><thead><tr><th>Company</th><th>Contact</th><th>Signal</th><th>Location</th><th>Fit</th><th>Score</th><th>Verification</th><th>Status</th><th></th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section id="salescoach" class="view">
<div class="coach-hero">
  <div><div class="kicker">ASH · EXPLAINABLE SALES COACH</div><h2>Know exactly who to call—and what to say.</h2><p>Recommendations use your stored account data, relationship activity, opportunity score, and product fit. Response likelihood is a transparent heuristic, not a promise.</p></div>
  <button class="btn primary" onclick="salesCoach()">Refresh coaching</button>
</div>
<div class="command-kpis coach-kpis">
  <div class="command-kpi"><span>Call today</span><strong id="scCallToday">0</strong><small>Highest-priority conversations</small></div>
  <div class="command-kpi"><span>Relationships at risk</span><strong id="scAtRisk">0</strong><small>Accounts losing momentum</small></div>
  <div class="command-kpi"><span>High response potential</span><strong id="scHighResponse">0</strong><small>Modeled likelihood ≥ 75%</small></div>
  <div class="command-kpi"><span>Product matched</span><strong id="scProductMatched">0</strong><small>Accounts with a clear lead angle</small></div>
</div>
<div class="panel">
  <div class="profile-head"><div><h3>Today’s coaching queue</h3><p class="muted">Every recommendation includes the evidence behind it.</p></div><select id="scFilter" onchange="renderSalesCoach()"><option>All</option><option>Call Today</option><option>At Risk</option><option>High Response</option></select></div>
  <div id="scQueue" class="coach-queue"><div class="empty">Loading coaching recommendations…</div></div>
</div>
</section>
<section id="outreach" class="view"><div class="grid"><div class="panel"><h3>Personalized outreach builder</h3><label>Prospect</label><select id="op" class="full"></select><label>Channel</label><select id="channel" class="full"><option>Email</option><option>LinkedIn</option><option>Phone</option></select><label>Angle</label><select id="angle" class="full"><option>Recommended by intelligence engine</option><option>Congratulations + growth support</option><option>VA/FHA scenario support</option><option>Fast onboarding</option><option>HELOC and niche products</option></select><button class="btn primary full" id="gen" style="margin-top:15px">Generate personalized draft</button></div><div class="panel"><button class="btn primary" id="queue" disabled style="float:right">Approve & queue</button><h3>Review draft</h3><input id="subject" class="subject" placeholder="Subject"><textarea id="body"></textarea></div></div><div class="panel" style="margin-top:14px"><h3>Recent outreach</h3><div id="olist"></div></div></section>
<section id="campaigns" class="view"><div class="hero"><div><div class="kicker">AUTOMATED DRIP CAMPAIGNS</div><h2>Email and text follow-up that runs on schedule.</h2><p>Build one-time campaigns or launch multi-touch sequences. BrokerBeacon personalizes every message, respects SMS consent and quiet hours, stops future steps on replies or opt-outs, retries temporary failures, and records delivery history.</p></div><span class="pill" id="campaignMode">Checking providers…</span></div><div class="metrics"><div class="metric"><span>Automation</span><strong id="autoState" style="font-size:20px">—</strong></div><div class="metric"><span>Email provider</span><strong id="emailState" style="font-size:20px">—</strong></div><div class="metric"><span>Text provider</span><strong id="smsState" style="font-size:20px">—</strong></div><div class="metric"><span>Due now</span><strong id="dueNow">0</strong></div></div><div class="callout" id="automationHelp">A secure scheduler endpoint is included for Render Cron Jobs. Manual processing remains available for testing.</div><div class="campaign-layout"><div class="panel"><h3>Create campaign</h3><label>Campaign name<input id="campName" class="full" placeholder="Example: Carolinas VA Scenario Support"></label><div class="formgrid"><label>Channel<select id="campChannel"><option>Email</option><option>SMS</option></select></label><label>Minimum score<input id="campScore" type="number" min="0" max="100" value="70"></label><label>State<select id="campState"><option value="">All states</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select></label><label>Status<select id="campStatus"><option value="">Any status</option><option>New</option><option>Contacted</option><option>Replied</option><option>Meeting</option></select></label><label>Send date/time<input id="campSchedule" type="datetime-local"></label><label>Daily send limit<input id="campLimit" type="number" min="1" max="500" value="50"></label></div><label>Email subject<input id="campSubject" class="full" placeholder="A quick resource for {{company}}"></label><label>Message body<textarea id="campBody" placeholder="Hi {{first_name}},

I’m Clay with Union Home Mortgage...

Reply STOP to opt out of texts."></textarea></label><p class="contact-note">Available fields: {{first_name}}, {{full_name}}, {{company}}, {{city}}, {{state}}, {{specialties}}. SMS recipients must have recorded consent.</p><div class="contact-tools"><button class="btn" id="previewCampaign">Preview audience</button><button class="btn primary" id="saveCampaign">Save & queue</button></div><div id="campaignPreview" class="roster-note"></div></div><div class="panel"><div class="profile-head"><div><h3>Campaign queue</h3><p class="muted">Paused campaigns never send. Processing can be triggered here or by a scheduled Render cron job.</p></div><button class="btn" id="processCampaigns">Process due queue</button></div><div id="campaignList"></div></div></div></section><section id="templates" class="view"><div class="hero"><div><div class="kicker">CAMPAIGN STUDIO</div><h2>Templates, personalization, sequences, and performance.</h2><p>Start from a proven wholesale-mortgage message, personalize it for a specific broker, or launch an editable multi-touch sequence. Email and SMS consent rules remain enforced by the campaign engine.</p></div><span class="pill">V7 AUTOMATION</span></div><div class="metrics"><div class="metric"><span>Email templates</span><strong id="tplEmailCount">0</strong></div><div class="metric"><span>SMS templates</span><strong id="tplSmsCount">0</strong></div><div class="metric"><span>Sequences</span><strong id="seqCount">0</strong></div><div class="metric"><span>Overall reply rate</span><strong id="replyRate">0%</strong></div></div><div class="template-grid"><div class="panel"><div class="library-tabs"><button class="btn active" data-lib="Email">Email</button><button class="btn" data-lib="SMS">SMS</button><button class="btn" data-lib="Sequences">Sequences</button></div><input id="templateSearch" class="full" placeholder="Search templates"><div id="templateList" class="template-list"></div></div><div class="panel"><div id="templateEditor"><h3>Choose a template</h3><p class="muted">Select a message from the library to edit, personalize, or load into the campaign builder.</p></div></div></div><div class="panel" style="margin-top:14px"><div class="profile-head"><div><h3>Campaign analytics</h3><p class="muted">Delivery, opens, clicks, replies, bounces, and opt-outs. Open/click tracking requires tracked HTML email delivery.</p></div><button class="btn" onclick="templateStudio()">Refresh</button></div><div id="campaignAnalytics" class="analytics-grid"></div><div id="campaignPerformance" style="margin-top:12px"></div></div></section><section id="inbox" class="view"><div class="hero"><div><div class="kicker">REPLY INTELLIGENCE</div><h2>Replies that need your attention.</h2><p>Sync inbound Gmail/IMAP messages, stop active sequences automatically, classify intent, and prepare an editable response draft.</p></div><button class="btn primary" onclick="syncInbox()">Sync mailbox</button></div><div class="metrics"><div class="metric"><span>Needs attention</span><strong id="inNeeds">0</strong></div><div class="metric"><span>Positive</span><strong id="inPositive">0</strong></div><div class="metric"><span>Questions</span><strong id="inQuestions">0</strong></div><div class="metric"><span>Sequences stopped</span><strong id="inStopped">0</strong></div></div><div class="grid"><div class="panel"><div class="profile-head"><div><h3>Inbound messages</h3><p class="muted">Newest replies appear first.</p></div><button class="btn" onclick="manualInbound()">Add test reply</button></div><div id="inboxList"></div></div><div class="panel"><div id="inboxDetail"><h3>Select a reply</h3><p class="muted">Review the message, classification, and suggested response.</p></div></div></div></section><section id="pipeline" class="view"><div class="hero"><div><div class="kicker">PIPELINE CONTROL</div><h2>Move prospects from discovery to approved account.</h2><p>Every status change updates the executive view and preserves a consistent sales process.</p></div><span class="pill">5-stage workflow</span></div><div id="board" class="board" style="margin-top:14px"></div></section><section id="followups" class="view"><div class="hero"><div><div class="kicker">FOLLOW-UP CENTER</div><h2>Never lose the next action.</h2><p>Relationship notes with follow-up dates are organized by urgency so the most important conversations stay visible.</p></div><button class="btn primary" onclick="show('prospects')">Open prospects</button></div><div class="metrics"><div class="metric"><span>Overdue</span><strong id="fo">0</strong></div><div class="metric"><span>Due today</span><strong id="ft">0</strong></div><div class="metric"><span>Next 7 days</span><strong id="fw">0</strong></div><div class="metric"><span>Unscheduled notes</span><strong id="fu">0</strong></div></div><div class="panel"><div id="followList"></div></div></section>

<section id="territory" class="view"><div class="hero"><div><div class="kicker">TERRITORY INTELLIGENCE</div><h2>See where broker opportunity is concentrated.</h2><p>Coverage by state and metro helps account executives prioritize travel, identify white space, and balance prospecting effort.</p></div><span class="pill">Public-web prospect coverage</span></div><div class="metrics"><div class="metric"><span>States covered</span><strong id="ts">0</strong></div><div class="metric"><span>Core Carolinas prospects</span><strong id="tc">0</strong></div><div class="metric"><span>Top metro concentration</span><strong id="tm">—</strong></div><div class="metric"><span>High-priority territories</span><strong id="th">0</strong></div></div><div class="grid"><div class="panel"><h3>State coverage map</h3><p class="muted">Tile-map view of the current prospect footprint. Darker fill indicates more discovered companies.</p><div id="stateMap" class="state-map"></div></div><div class="panel"><h3>Metro opportunity</h3><div id="metros" class="bars"></div><h3 style="margin-top:24px">Coverage gaps</h3><div id="gaps" class="activity"></div></div></div></section>
<section id="guidelines" class="view">
<div class="guide-hero"><div><div class="kicker">BROKERBEACON LOAN GUIDELINES LIBRARY</div><h2>Fast program guidance with links to the controlling sources.</h2><p>Use this workspace for sales conversations and initial scenario screening. It summarizes common agency requirements, but it does not replace the current agency guide, AUS findings, lender overlays, product matrices, or an underwriter’s decision.</p></div><div><span class="guide-chip">Reviewed July 29, 2026</span></div></div>
<div class="guide-live-search panel">
<div class="profile-head"><div><div class="kicker">ASH UNDERWRITER · LOCAL OFFICIAL-GUIDE INDEX</div><h3 style="margin:5px 0">Ask a guideline question or search a topic</h3><p class="muted" style="margin:0">BrokerBeacon searches its local index of official agency guide sections and handbook pages, then returns source excerpts, citations, and direct official links. Results are not generated from memory.</p></div><span class="guide-chip">Official sources only</span></div>
<div class="guide-query-row"><select id="guideProgram"><option value="all">All programs</option><option value="fannie">Fannie Mae</option><option value="freddie">Freddie Mac</option><option value="fha">FHA</option><option value="va">VA</option><option value="usda">USDA</option></select><input id="guideSearch" placeholder="Example: Can gift funds be used on a 2-unit primary residence?"><button class="btn primary" id="searchGuides" type="button">Search official guides</button></div>
<div class="guide-example-row"><button class="btn smallbtn guide-example">Fannie gift funds</button><button class="btn smallbtn guide-example">Freddie student loan payment</button><button class="btn smallbtn guide-example">FHA manual underwriting collections</button><button class="btn smallbtn guide-example">VA residual income</button><button class="btn smallbtn guide-example">USDA manufactured housing</button></div>
<div id="guideSearchStatus" class="muted" style="margin-top:10px"></div><div id="guideResults" class="guide-results"></div>
</div>
<div class="guide-tabs" id="guideTabs" style="margin:14px 0"><button class="btn active" data-guide="fannie" onclick="showGuide('fannie',this)">Fannie Mae overview</button><button class="btn" data-guide="freddie" onclick="showGuide('freddie',this)">Freddie Mac overview</button><button class="btn" data-guide="fha" onclick="showGuide('fha',this)">FHA overview</button><button class="btn" data-guide="va" onclick="showGuide('va',this)">VA overview</button><button class="btn" data-guide="usda" onclick="showGuide('usda',this)">USDA overview</button></div>
<div class="guide-alert" style="margin-bottom:14px"><b>Compliance checkpoint:</b> Search results are a research aid. Open the cited official source, confirm its effective date, review AUS findings and Union Home Mortgage overlays, and obtain underwriting guidance before making a credit decision.</div>

<div class="guide-program active" id="guide-fannie" data-program="Fannie Mae conventional DU Desktop Underwriter occupancy LTV DTI gifts reserves mortgage insurance">
<div class="guide-program-head"><div><h2>Fannie Mae conventional</h2><div class="muted">Selling Guide · Desktop Underwriter (DU)</div></div><span class="guide-chip">Conventional / conforming</span></div>
<div class="guide-grid">
<div class="guide-card"><h3>Core eligibility</h3><ul><li>Eligible transactions may include purchases and refinances secured by qualifying 1–4 unit residential property.</li><li>Principal residences, second homes, and investment properties may be eligible, subject to the specific product and Guide requirements.</li><li>Conforming loan limits, high-balance eligibility, and product terms must be checked for the property’s county and year.</li></ul></div>
<div class="guide-card"><h3>Down payment & mortgage insurance</h3><ul><li>Some eligible principal-residence programs permit financing up to 97% LTV, meaning as little as 3% down.</li><li>Mortgage insurance is generally required when a conventional first mortgage exceeds 80% LTV, unless another permitted structure applies.</li><li>Minimum borrower contribution, gift funds, and reserve requirements vary by occupancy, units, LTV, and transaction type.</li></ul></div>
<div class="guide-card"><h3>Underwriting focus</h3><ul><li>DU findings drive documentation and risk requirements for DU-underwritten files; manual underwriting rules apply when used.</li><li>Evaluate stable and continuing income, liabilities, assets, credit history, and the complete loan profile.</li><li>Property type, appraisal, condo/project eligibility, and interested-party contributions require separate review.</li></ul></div>
<div class="guide-card"><h3>AE conversation prompts</h3><ul><li>Is this a principal residence, second home, or investment property?</li><li>What is the estimated LTV and are gifts or grants involved?</li><li>Has DU been run, and are there project, income, or reserve conditions that need help?</li></ul></div>
</div><div class="source-links"><a target="_blank" rel="noopener" href="https://selling-guide.fanniemae.com/">↗ Fannie Mae Selling Guide</a><a target="_blank" rel="noopener" href="https://singlefamily.fanniemae.com/">↗ Single-Family resources</a></div></div>

<div class="guide-program" id="guide-freddie" data-program="Freddie Mac conventional LPA Loan Product Advisor occupancy LTV DTI gifts reserves mortgage insurance">
<div class="guide-program-head"><div><h2>Freddie Mac conventional</h2><div class="muted">Single-Family Seller/Servicer Guide · Loan Product Advisor (LPA)</div></div><span class="guide-chip">Conventional / conforming</span></div>
<div class="guide-grid">
<div class="guide-card"><h3>Core eligibility</h3><ul><li>Eligible mortgages include qualifying purchase and refinance transactions on residential property, subject to Guide and product requirements.</li><li>Occupancy may include primary residences, second homes, and investment properties where permitted.</li><li>Check current conforming limits, super-conforming eligibility, property requirements, and delivery terms.</li></ul></div>
<div class="guide-card"><h3>Down payment & mortgage insurance</h3><ul><li>Certain eligible primary-residence offerings permit up to 97% LTV.</li><li>Credit enhancement, commonly mortgage insurance, is generally required above 80% LTV unless a permitted alternative applies.</li><li>Source of funds, borrower contribution, gifts, and reserves depend on the transaction’s risk characteristics.</li></ul></div>
<div class="guide-card"><h3>Underwriting focus</h3><ul><li>LPA feedback certificates identify documentation and eligibility requirements for loans assessed through LPA.</li><li>Review stable monthly income, employment, assets, liabilities, credit, and layered risk.</li><li>Condo/project review, appraisal, property condition, and special collateral types require Guide-specific checks.</li></ul></div>
<div class="guide-card"><h3>AE conversation prompts</h3><ul><li>What did LPA return and which conditions are creating friction?</li><li>Is the borrower using gift funds, secondary financing, or affordable-lending assistance?</li><li>Is there a condo, manufactured-home, self-employment, or reserve issue to structure?</li></ul></div>
</div><div class="source-links"><a target="_blank" rel="noopener" href="https://guide.freddiemac.com/app/guide/segment/selling">↗ Freddie Mac Selling Guide</a><a target="_blank" rel="noopener" href="https://sf.freddiemac.com/">↗ Single-Family resources</a></div></div>

<div class="guide-program" id="guide-fha" data-program="FHA HUD 4000.1 primary residence 3.5 down mortgage insurance MIP TOTAL scorecard manual underwriting 1-4 units">
<div class="guide-program-head"><div><h2>FHA-insured financing</h2><div class="muted">HUD Handbook 4000.1 · TOTAL Mortgage Scorecard</div></div><span class="guide-chip">Government insured</span></div>
<div class="guide-grid">
<div class="guide-card"><h3>Core eligibility</h3><ul><li>Designed for owner-occupied principal residences; eligible properties may include 1–4 unit homes when program requirements are met.</li><li>The borrower must establish the property as a principal residence within the required timeframe and satisfy FHA identity-of-interest and occupancy rules.</li><li>Loan limits are county-specific and updated periodically.</li></ul></div>
<div class="guide-card"><h3>Down payment & mortgage insurance</h3><ul><li>Minimum required investment may be 3.5% for borrowers meeting FHA’s applicable credit requirements; lower credit profiles may require at least 10% down.</li><li>Upfront and annual mortgage insurance premiums generally apply, subject to current FHA policy.</li><li>Permitted sources may include borrower funds, eligible gifts, grants, and approved assistance, with documentation.</li></ul></div>
<div class="guide-card"><h3>Underwriting focus</h3><ul><li>TOTAL findings or manual underwriting requirements govern documentation and risk review.</li><li>Review credit history, capacity, effective income, debts, compensating factors, and federal delinquency/CAIVRS issues.</li><li>FHA appraisal and minimum property requirements apply; repairs and 203(k) options require separate analysis.</li></ul></div>
<div class="guide-card"><h3>AE conversation prompts</h3><ul><li>Has the file received an Accept/Approve or Refer recommendation?</li><li>Are gift funds, down-payment assistance, non-occupant co-borrowers, or manual underwriting involved?</li><li>Are there property-condition, self-employment, student-loan, or federal-debt concerns?</li></ul></div>
</div><div class="source-links"><a target="_blank" rel="noopener" href="https://www.hud.gov/hud-partners/single-family-handbook-4000-1">↗ FHA Handbook 4000.1</a><a target="_blank" rel="noopener" href="https://www.hud.gov/hud-partners/single-family-fha-info">↗ FHA INFO updates</a></div></div>

<div class="guide-program" id="guide-va" data-program="VA veteran COE entitlement residual income funding fee no monthly mortgage insurance primary residence escape clause NOV">
<div class="guide-program-head"><div><h2>VA-guaranteed financing</h2><div class="muted">VA Lenders Handbook · VA Circulars</div></div><span class="guide-chip">Government guaranteed</span></div>
<div class="guide-grid">
<div class="guide-card"><h3>Core eligibility</h3><ul><li>Borrower eligibility is established through military-service requirements and a valid Certificate of Eligibility (COE).</li><li>The home generally must be the veteran’s primary residence; occupancy and spouse-related rules must be reviewed.</li><li>Entitlement, county limits for borrowers with partial entitlement, and guaranty calculations affect maximum loan structure.</li></ul></div>
<div class="guide-card"><h3>Financing & fees</h3><ul><li>VA does not generally require a down payment when the price does not exceed reasonable value and sufficient entitlement is available, although lender requirements may still apply.</li><li>No monthly mortgage insurance is required. A VA funding fee generally applies unless the borrower is exempt.</li><li>Seller concessions, closing costs, gifts, and financed funding-fee treatment are governed by VA requirements.</li></ul></div>
<div class="guide-card"><h3>Underwriting focus</h3><ul><li>Residual income is a central VA capacity test; DTI is evaluated with the complete credit profile rather than as a stand-alone rule.</li><li>Review satisfactory credit, stable income, debts, maintenance/utilities, family size, and geographic residual-income tables.</li><li>VA appraisal/Notice of Value, Minimum Property Requirements, escape clause, and tidewater procedures may apply.</li></ul></div>
<div class="guide-card"><h3>AE conversation prompts</h3><ul><li>Does the borrower have full or partial entitlement, and is the COE accurate?</li><li>Is the funding-fee exemption verified?</li><li>What do residual income, DTI, and the AUS recommendation show—and is a manual underwrite needed?</li></ul></div>
</div><div class="source-links"><a target="_blank" rel="noopener" href="https://www.benefits.va.gov/homeloans/lenders.asp">↗ VA lender resources</a><a target="_blank" rel="noopener" href="https://www.benefits.va.gov/homeloans/resources_circulars.asp">↗ Current VA Circulars</a></div></div>

<div class="guide-program" id="guide-usda" data-program="USDA Rural Development guaranteed rural property income limits 100 percent financing GUS household income annual guarantee fee 30 year fixed primary residence">
<div class="guide-program-head"><div><h2>USDA Single Family Housing Guaranteed</h2><div class="muted">HB-1-3555 · Guaranteed Underwriting System (GUS)</div></div><span class="guide-chip">Government guaranteed</span></div>
<div class="guide-grid">
<div class="guide-card"><h3>Core eligibility</h3><ul><li>The property must be in an eligible rural area and used as the borrower’s permanent primary residence.</li><li>Adjusted annual household income must remain within the applicable area and household-size limit.</li><li>Eligible property types and uses are governed by HB-1-3555; income-producing property is generally not eligible.</li></ul></div>
<div class="guide-card"><h3>Financing & fees</h3><ul><li>Eligible transactions may provide 100% financing; certain allowable costs may be included when supported by appraised value and program rules.</li><li>The guaranteed program offers 30-year fixed-rate loans.</li><li>An upfront guarantee fee and annual fee generally apply at the rates in effect for the transaction.</li></ul></div>
<div class="guide-card"><h3>Underwriting focus</h3><ul><li>GUS recommendations determine automated-underwriting treatment; Refer or manually underwritten files require additional analysis.</li><li>USDA distinguishes household annual/adjusted income for eligibility from stable repayment income used to qualify.</li><li>Review credit, ratios, federal debt/CAIVRS, assets, property eligibility, appraisal, and inability to obtain conventional credit on reasonable terms as applicable.</li></ul></div>
<div class="guide-card"><h3>AE conversation prompts</h3><ul><li>Has the exact address been checked in USDA’s property-eligibility tool?</li><li>Has all adult household-member income been included for eligibility?</li><li>What is the GUS recommendation, and are ratio waivers or credit exceptions involved?</li></ul></div>
</div><div class="source-links"><a target="_blank" rel="noopener" href="https://www.rd.usda.gov/resources/directives/handbooks">↗ USDA HB-1-3555</a><a target="_blank" rel="noopener" href="https://www.rd.usda.gov/resources/usda-linc-training-resource-library">↗ USDA LINC resources</a><a target="_blank" rel="noopener" href="https://eligibility.sc.egov.usda.gov/eligibility/welcomeAction.do">↗ Property & income eligibility</a></div></div>
<div class="guide-note" style="margin-top:14px"><b>Designed for speed, not final underwriting.</b> BrokerBeacon intentionally avoids presenting mutable items such as current loan limits, fee percentages, county income limits, or company overlays as permanent facts. Use the official links above for the live rule.</div>
</section>
<section id="boss" class="view"><div class="hero exec"><div><div class="kicker">SPRINT 3 · REVENUE INTELLIGENCE</div><h2>Pipeline, conversion, and campaign attribution</h2><p>Separate actual recorded outcomes from configurable projections. Track applications, submissions, fundings, funded volume, estimated revenue, and which campaign preceded an outcome.</p></div><div class="contact-tools"><select id="execPeriod"><option value="30">30 days</option><option value="90" selected>90 days</option><option value="365">12 months</option></select><button class="btn primary" onclick="boss()">Refresh</button><button class="btn" onclick="window.print()">Print / Save PDF</button></div></div><div class="metrics"><div class="metric"><span>Recorded funded volume</span><strong id="eFunded">$0</strong></div><div class="metric"><span>Recorded fundings</span><strong id="eUnits">0</strong></div><div class="metric"><span>Estimated actual revenue</span><strong id="eRevenue">$0</strong></div><div class="metric"><span>Projected pipeline volume</span><strong id="eProjected">$0</strong></div></div><div class="grid"><div class="panel"><h3>Conversion funnel</h3><div id="execFunnel" class="bars"></div><div id="execConversion" class="scoregrid" style="margin-top:14px"></div></div><div class="panel"><h3>Record an outcome</h3><p class="muted">Log only real business events. BrokerBeacon attributes the outcome to the most recent sent campaign within 90 days when one exists.</p><label>Broker<select id="revProspect" class="full"></select></label><div class="formgrid"><label>Outcome<select id="revType"><option>Application</option><option>Submitted</option><option>Funded</option><option>Lost</option></select></label><label>Amount<input id="revAmount" type="number" min="0" step="1000" value="0"></label><label>Date/time<input id="revDate" type="datetime-local"></label><label>Loan count<input id="revCount" type="number" min="1" value="1"></label></div><label>Notes<input id="revNotes" class="full" placeholder="Optional scenario or outcome note"></label><button class="btn primary" id="saveRevenue">Save outcome</button></div></div><div class="grid" style="margin-top:14px"><div class="panel"><h3>Campaign-to-outcome attribution</h3><div id="execCampaigns"></div></div><div class="panel"><h3>Top accounts by recorded results</h3><div id="execTop"></div></div></div><div class="grid" style="margin-top:14px"><div class="panel"><h3>Recent outcomes</h3><div id="execRecent" class="activity"></div></div><div class="panel"><h3>Projection assumptions</h3><p class="muted">These settings affect projected figures only. They do not alter recorded production.</p><div id="revenueSettings"></div><button class="btn" id="saveRevenueSettings">Save assumptions</button></div></div></section>
<section id="voiceagent" class="view"><div class="hero"><div><div class="kicker">CONSENT-FIRST AUTOMATION</div><h2>Ash AI Voice Agent</h2><p>Place disclosed automated calls with a professional female voice, detect voicemail, handle a brief conversation, and schedule appointments. Calls are allowed only for contacts explicitly marked as having voice consent.</p></div><span class="pill" id="voiceStatus">Checking connection…</span></div><div class="callout" style="margin:14px 0"><b>Compliance guardrails:</b> no cold-call automation, no voice cloning, no calls to opted-out contacts, and the AI identifies itself at the beginning of every live conversation.</div><div class="grid"><div class="panel"><div class="profile-head"><div><h3>Eligible contacts</h3><p class="muted">Review each contact before calling.</p></div><button class="btn" onclick="voiceAgent()">Refresh</button></div><div id="voiceContacts"></div></div><div><div class="panel"><h3>Upcoming appointments</h3><div id="voiceAppointments"></div></div><div class="panel" style="margin-top:14px"><h3>Recent call activity</h3><div id="voiceCalls"></div></div></div></div></section><section id="integrations" class="view"><div class="int"><div class="panel integration"><b>✉ Gmail</b><p>Future OAuth draft creation and reply tracking.</p><input type="checkbox" data-key="gmail_connected"></div><div class="panel integration"><b>H HubSpot</b><p>Future prospect and lifecycle synchronization.</p><input type="checkbox" data-key="hubspot_connected"></div><div class="panel integration"><b>N Licensing feed</b><p>Future authorized broker-data import adapter.</p><input type="checkbox" data-key="nmls_source_configured"></div></div><div class="panel" style="margin-top:14px;color:var(--m)"><b>Demo safety:</b> connection toggles store flags only. No passwords, tokens, or paid-data credentials are stored. Live research and integrations require approved data sources and credentials.</div></section>

<section id="intelligence" class="view"><div class="hero"><div><div class="kicker">EXPLAINABLE REVENUE INTELLIGENCE</div><h2>Know who to call, why they matter, and what to lead with.</h2><p>Scores are calculated from verified data, roster size, product fit, relationship stage, follow-up urgency, and inactivity. Every recommendation includes its reasoning and confidence.</p></div><button class="btn primary" onclick="rescoreIntelligence()">Recalculate all</button></div><div class="metrics"><div class="metric"><span>Hot opportunities</span><strong id="oiHot">0</strong></div><div class="metric"><span>Warm opportunities</span><strong id="oiWarm">0</strong></div><div class="metric"><span>Due today</span><strong id="oiDue">0</strong></div><div class="metric"><span>Product matched</span><strong id="oiMatched">0</strong></div></div><div class="grid"><div class="panel" style="grid-column:1/-1"><div class="profile-head"><div><h3>Ranked opportunities</h3><p class="muted">The score is transparent and configurable. It is not a production-volume claim.</p></div><select id="oiTier" onchange="renderIntelligence()"><option>All</option><option>Hot</option><option>Warm</option><option>Developing</option><option>Research</option></select></div><div id="oiRows"></div></div><div class="panel"><h3>Scoring controls</h3><p class="muted">Adjust how much each verified signal contributes.</p><div id="oiSettings"></div><button class="btn primary" onclick="saveIntelligenceSettings()">Save weights</button></div><div class="panel"><h3>Union Home product catalog</h3><p class="muted">Editable talking points used by the product-match engine.</p><div id="oiProducts"></div></div></div></section>
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
function applyTheme(mode){
  document.body.classList.toggle('dark-mode',mode==='dark');
  localStorage.setItem('bb-theme',mode);
  const b=$('#themeToggle');
  if(b){b.textContent=mode==='dark'?'☀ Light':'◐ Theme';b.setAttribute('aria-label',mode==='dark'?'Use light mode':'Use dark mode')}
}
function initProfessionalShell(){
  const preferred=localStorage.getItem('bb-theme')||'light';
  applyTheme(preferred);
  const chip=$('#todayChip');
  if(chip)chip.textContent=new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric'}).format(new Date());
  const toggle=$('#themeToggle');
  if(toggle)toggle.addEventListener('click',()=>applyTheme(document.body.classList.contains('dark-mode')?'light':'dark'));
}

async function api(u,o={}){
  let r=await fetch(u,{headers:{'Content-Type':'application/json',...(o.headers||{})},...o});
  let text=await r.text(),d;
  try{d=text?JSON.parse(text):{}}catch(e){
    throw Error(r.ok?'Server returned an unreadable response':`Server error ${r.status} at ${u}`);
  }
  if(!r.ok)throw Error(d.error||`Request failed (${r.status})`);
  return d;
}
function esc(x){return String(x??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function telHref(x){return 'tel:'+String(x||'').replace(/[^0-9+]/g,'')}
function mailHref(x){return 'mailto:'+String(x||'').trim()}
async function copyText(x){try{await navigator.clipboard.writeText(x);msg('Copied')}catch(e){msg('Copy failed')}}
function safeUrl(x){let s=String(x||'').trim();return s&&!/^https?:\/\//i.test(s)?'https://'+s:s}
function contactButtons(p,compact=false){let a=[];if(p.phone)a.push(`<a class="btn smallbtn" href="${telHref(p.phone)}">☎ ${compact?'Call':'Call '+esc(p.phone)}</a>`);if(p.email)a.push(`<a class="btn smallbtn" href="${mailHref(p.email)}">✉ ${compact?'Email':'Email'}</a>`);if(p.website)a.push(`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(safeUrl(p.website))}">↗ Website</a>`);return a.join(' ')}


function showGuide(name,btn){
  $$('.guide-program').forEach(x=>x.classList.toggle('active',x.id==='guide-'+name));
  $$('#guideTabs button').forEach(x=>x.classList.toggle('active',x===btn));
}
function filterGuidelines(){ /* retained for backward compatibility */ }
async function searchOfficialGuides(){
  const q=($('#guideSearch')?.value||'').trim(),program=$('#guideProgram')?.value||'all';
  if(q.length<3)return msg('Enter a guideline question or topic');
  const box=$('#guideResults'),status=$('#guideSearchStatus'),btn=$('#searchGuides');
  btn.disabled=true;btn.textContent='Searching…';status.textContent='Searching the locally indexed official guides…';box.innerHTML='<div class="guide-loading">Searching indexed guide sections and handbook pages…</div>';
  try{
    const d=await api('/api/guidelines/search?'+new URLSearchParams({q,program}));
    status.textContent=`${d.results.length} indexed result${d.results.length===1?'':'s'} · ${d.index_total||0} guide sections/pages available`; 
    box.innerHTML=d.results.length?d.results.map(r=>`<article class="guide-result"><div class="guide-result-head"><div><div class="source-label">${esc(r.program)} · ${esc(r.source_type)}${r.page?' · page '+r.page:''}</div><h4>${esc(r.title)}</h4></div><a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(r.url)}">Open official source ↗</a></div>${r.section?`<div class="guide-chip">${esc(r.section)}</div>`:''}<div class="excerpt">${String(r.excerpt||'Open the official source to review the controlling language.').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/&lt;mark&gt;/g,'<mark>').replace(/&lt;\/mark&gt;/g,'</mark>')}</div><div class="indexed-meta">Locally indexed from the cited official source. Verify current effective dates, AUS findings, and lender overlays.</div><div class="result-url">${esc(r.display_url||r.url)}</div></article>`).join(''):`<div class="guide-empty"><b>No exact official page was returned.</b><p>Try fewer words or search one program at a time.</p>${(d.fallback_links||[]).map(x=>`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(x.url)}">Search ${esc(x.label)} ↗</a>`).join(' ')}</div>`;
    if(d.warning)box.insertAdjacentHTML('beforeend',`<div class="guide-warning">${esc(d.warning)}</div>`);
  }catch(e){status.textContent='Search unavailable';box.innerHTML=`<div class="guide-empty"><b>Could not reach the official-guide search.</b><p>${esc(e.message)}</p><p>Use the direct official guide links below while the connection is unavailable.</p></div>`}
  finally{btn.disabled=false;btn.textContent='Search official guides'}
}

$('#searchGuides').onclick=searchOfficialGuides;$('#guideSearch').onkeydown=e=>{if(e.key==='Enter')searchOfficialGuides()};$$('.guide-example').forEach(b=>b.onclick=()=>{$('#guideSearch').value=b.textContent;searchOfficialGuides()});
function msg(x){let t=$('#toast');t.textContent=x;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
function show(v){$$('.view').forEach(x=>x.classList.toggle('active',x.id===v));$$('nav button').forEach(x=>x.classList.toggle('active',x.dataset.v===v));const titles={dashboard:'Command Center',salescoach:'Ash Sales Coach',voiceagent:'AI Voice Agent',boss:'Executive View',followups:'Follow-ups',intelligence:'Opportunity Intelligence',templates:'Templates & Sequences',guidelines:'Loan Guidelines Library'};$('#title').textContent=titles[v]||v[0].toUpperCase()+v.slice(1);if(v==='salescoach')salesCoach();if(v==='voiceagent')voiceAgent();if(v==='copilot'){copilotBrief()}if(v==='daily')dailyPlan();if(v==='pipeline')pipe();if(v==='followups')followups();if(v==='outreach')outreach();if(v==='campaigns')campaigns();if(v==='inbox')replyInbox();if(v==='intelligence')loadIntelligence();if(v==='templates')templateStudio();if(v==='territory')territory();if(v==='boss')boss()}
$$('nav button').forEach(b=>b.onclick=()=>show(b.dataset.v));
async function copilotBrief(){let d=await api('/api/copilot/brief');$('#morningBrief').innerHTML=`<div class="briefline"><b>${esc(d.greeting)}</b><div class="muted">${esc(d.summary)}</div></div>`+d.highlights.map(x=>`<div class="briefline"><b>${esc(x.label)}</b><div class="muted">${esc(x.value)}</div></div>`).join('')+`<div class="briefline"><b>Recommended first move</b><div class="nextaction">${esc(d.first_move)}</div></div>`}
async function askCopilot(){let q=$('#copilotQuestion').value.trim();if(!q)return msg('Enter a question');$('#copilotAnswer').innerHTML='<div class="empty">Analyzing your database…</div>';try{let d=await api('/api/copilot/ask',{method:'POST',body:JSON.stringify({question:q})});$('#copilotAnswer').innerHTML=`<b>${esc(d.title)}</b><div class="confidence">${esc(d.scope)}</div><p>${esc(d.answer)}</p>`+(d.results||[]).map((x,i)=>`<div class="priority-card"><div class="orb" style="--s:${x.priority_score||x.score||0}">${x.priority_score||x.score||0}</div><div><b>${i+1}. ${esc(x.company)}</b><div class="reason">${esc(x.reason)}</div><div><span class="tag">${esc(x.city||'')}${x.state?', '+esc(x.state):''}</span><span class="tag">${esc(x.status||'')}</span></div></div><button class="btn smallbtn" onclick="profile(${x.id})">Open</button></div>`).join('');}catch(e){$('#copilotAnswer').textContent=e.message}}
$('#askCopilot').onclick=askCopilot;$('#copilotQuestion').onkeydown=e=>{if(e.key==='Enter')askCopilot()};$$('.copilotPrompt').forEach(b=>b.onclick=()=>{$('#copilotQuestion').value=b.textContent;askCopilot()});

async function load(){let q=new URLSearchParams({search:$('#search').value,state:$('#state').value,signal:$('#signal').value,status:$('#pstatus').value,min_score:$('#minscore').value});P=await api('/api/prospects?'+q);$('#rows').innerHTML=P.map(p=>`<tr><td><b>${esc(p.company)}</b><br><small>${esc(p.owner||'Primary contact not named')}</small></td><td class="contact-cell">${p.phone?`<a href="${telHref(p.phone)}">${esc(p.phone)}</a>`:''}${p.email?`<a href="${mailHref(p.email)}">${esc(p.email)}</a>`:''}${!p.phone&&!p.email?'<span class="contact-missing">Use company website</span>':''}<div>${contactButtons(p,true)}</div></td><td><span class="pill">${esc(p.signal)}</span></td><td>${esc(p.city||'')}, ${esc(p.state||'')}</td><td>${(p.product_fit||'').split(',').slice(0,2).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</td><td class="score">${p.score}</td><td><span class="pill">${esc(p.verification_status||'Needs verification')}</span></td><td>${esc(p.status)}</td><td><button class="btn smallbtn" onclick="profile(${p.id})">Intelligence</button></td></tr>`).join('');$('#op').innerHTML=P.map(p=>`<option value="${p.id}">${esc(p.company)}</option>`).join('')}
async function dash(){let d=await api('/api/dashboard');$('#mt').textContent=d.total;$('#ms').textContent=d.avg;$('#mq').textContent=d.queued;$('#mm').textContent=d.status.Meeting||0;$('#snapshot').innerHTML=['New','Contacted','Replied','Meeting','Approved'].map(x=>`<p>${x}<b style="float:right">${d.status[x]||0}</b></p>`).join('');$('#activity').innerHTML=d.activity.map(a=>`<div><b>${esc(a.action)}</b><br><small>${esc(a.detail||'')} · ${esc(a.created_at.replace('T',' '))}</small></div>`).join('')||'<div class=empty>No activity yet.</div>';$('#priority').innerHTML=d.priorities.map(p=>`<div class="priority-card"><div class="orb" style="--s:${p.score}">${p.score}</div><div><b>${esc(p.company)}</b><div class="reason">${esc(p.next_best_action)}</div><div>${(p.product_fit||'').split(',').slice(0,3).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</div></div><button class="btn smallbtn" onclick="profile(${p.id})">Open</button></div>`).join('')||'<div class=empty>Add or import prospects to begin.</div>'}
function personCard(c){return `<div class="person-card ${c.is_primary?'primary-contact':''}"><div class="person-top"><div><b>${esc(c.name||'Company Contact Desk')}</b>${c.is_decision_maker?' <span class="decision">DECISION-MAKER</span>':''}<div class="person-meta">${esc(c.role||'Contact')} ${c.is_primary?'· Primary':''} ${c.roster_status?`· ${esc(c.roster_status)}`:''}</div></div><div>${document.body.dataset.demo==='1'?'':`<button class="btn copybtn" onclick="editContact(${c.id})">Edit</button>`}</div></div><div class="officer-details">${c.nmls?`<div><small>NMLS</small>${esc(c.nmls)}</div>`:''}${c.office_location?`<div><small>Office</small>${esc(c.office_location)}</div>`:''}${c.specialties?`<div><small>Specialties</small>${esc(c.specialties)}</div>`:''}${c.languages?`<div><small>Languages</small>${esc(c.languages)}</div>`:''}${c.preferred_method?`<div><small>Preferred contact</small>${esc(c.preferred_method)}</div>`:''}${c.verified_at?`<div><small>Verified</small>${esc(c.verified_at)}</div>`:''}</div>${c.phone?`<div><a href="${telHref(c.phone)}">☎ ${esc(c.phone)}</a> <button class="btn copybtn" onclick="copyText('${esc(c.phone).replace(/'/g,"&#39;")}')">Copy</button></div>`:''}${c.mobile?`<div><a href="${telHref(c.mobile)}">📱 ${esc(c.mobile)}</a></div>`:''}${c.email?`<div><a href="${mailHref(c.email)}">✉ ${esc(c.email)}</a> <button class="btn copybtn" onclick="copyText('${esc(c.email).replace(/'/g,"&#39;")}')">Copy</button></div>`:''}<div class="contact-tools">${c.phone||c.mobile?`<a class="btn smallbtn" href="${telHref(c.mobile||c.phone)}">Call</a>`:''}${c.email?`<a class="btn smallbtn" href="${mailHref(c.email)}">Email</a>`:''}${c.linkedin_url?`<a class="btn smallbtn" target="_blank" rel="noopener" href="${esc(safeUrl(c.linkedin_url))}">Profile</a>`:''}${c.source_url?`<a class="source-link" target="_blank" rel="noopener" href="${esc(safeUrl(c.source_url))}">Verify source</a>`:''}<button class="btn smallbtn" onclick="buildOfficerOutreach(${c.id})">AI outreach</button></div>${c.notes?`<div class="contact-note">${esc(c.notes)}</div>`:''}</div>`}
function renderContacts(items){let q=($('#contactSearch')?.value||'').toLowerCase();let visible=items.filter(c=>!q||[c.name,c.role,c.email,c.phone,c.mobile,c.nmls,c.specialties,c.languages,c.office_location].join(' ').toLowerCase().includes(q));$('#contactCount').textContent=items.length+' person'+(items.length===1?'':'s');let groups=[['Decision-makers',visible.filter(c=>c.is_decision_maker)],['Loan officers',visible.filter(c=>!c.is_decision_maker&&!/desk|office|general/i.test((c.role||'')+' '+(c.name||'')))],['Company contact desk',visible.filter(c=>/desk|office|general/i.test((c.role||'')+' '+(c.name||'')))]];$('#contactList').innerHTML=groups.filter(g=>g[1].length).map(g=>`<section class="roster-section"><div class="roster-title"><h4>${g[0]}</h4><span class="pill">${g[1].length}</span></div>${g[1].map(personCard).join('')}</section>`).join('')||'<div class="empty">No matching contacts entered.</div>';let named=items.filter(c=>c.name&&c.name!=='Company Contact Desk').length;$('#rosterStatus').textContent=named?`${named} named team member${named===1?'':'s'} stored. Public rosters may be incomplete; use Review company website to stage newly published contacts.`:'No named loan officers are stored yet. Review the company website or add verified officers manually.'}
async function buildOfficerOutreach(id){
  const c=(current.contacts||[]).find(x=>x.id===id);
  if(!c)return msg('Contact not found');
  const channel=c.email?'Email':'Phone';
  try{
    const d=await api('/api/generate',{method:'POST',body:JSON.stringify({id:current.id,contact_id:c.id,channel:channel,angle:'Recommended by intelligence engine'})});
    draft=d.id;
    show('outreach');
    $('#op').value=String(current.id);
    $('#channel').value=channel;
    $('#subject').value=d.subject||'';
    $('#subject').style.display=channel==='Email'?'block':'none';
    $('#body').value=d.body||'';
    $('#queue').disabled=false;
    if($('#profile').open)$('#profile').close();
    await outreach();
    msg('Draft personalized for '+(c.name||'contact'));
  }catch(e){msg(e.message||'Could not generate outreach')}
}
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


async function missionControl(){
  let d=await api('/api/mission-control');
  $('#mcPotential').textContent=money(d.metrics.projected_pipeline_potential||0);
  $('#mcCalls').textContent=d.metrics.priority_calls;
  $('#mcMeetingsNeeded').textContent=d.metrics.meeting_opportunities||0;
  $('#mcApps').textContent=d.metrics.application_opportunities||0;
  $('#mcPriorities').innerHTML=d.priorities.map(p=>`<div class="priority-card pro-priority"><div class="orb" style="--s:${p.score}">${p.score}</div><div><div class="priority-title"><b>${esc(p.company)}</b><span class="health ${p.health.toLowerCase().replace(' ','-')}">${esc(p.health)}</span></div><div class="reason">${esc(p.reason)}</div><small class="muted">${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.status)} · ${p.days_inactive>=999?'No activity logged':p.days_inactive+' days since activity'}</small></div><div class="priority-actions"><button class="btn smallbtn" onclick="profile(${p.id})">Call prep</button><button class="btn smallbtn accent" onclick="quickDraft(${p.id})">Draft outreach</button></div></div>`).join('')||'<div class="empty">No urgent priorities.</div>';
  $('#mcBrief').textContent=d.brief;
  $('#mcBriefFacts').innerHTML=`<span><b>${d.metrics.new_alerts}</b> new alerts</span><span><b>${d.metrics.at_risk}</b> at risk</span><span><b>${d.metrics.replies_attention||0}</b> replies needing attention</span>`;
  $('#mcRecommendations').innerHTML=d.recommendations.map((x,i)=>`<div class="recommendation"><span>${i+1}</span><div><b>${esc(x.title)}</b><small>${esc(x.detail)}</small></div></div>`).join('');
  $('#mcHealth').innerHTML=['Healthy','Cooling','At Risk'].map(x=>`<div class="health-row"><span class="health ${x.toLowerCase().replace(' ','-')}">${x}</span><b>${d.health[x]||0}</b></div>`).join('');
  $('#mcAlerts').innerHTML=d.new_alerts.map(x=>`<div><b>${esc(x.company)}</b><br><small>${esc(x.signal||'New prospect')} · Score ${x.score}</small></div>`).join('')||'<div class="empty">No new alerts.</div>';
  $('#mcAtRisk').innerHTML=d.at_risk.map(x=>`<div><b>${esc(x.company)}</b><br><small>${x.days_inactive} days without activity · <a href="#" onclick="profile(${x.id});return false">Open</a></small></div>`).join('')||'<div class="empty">No relationships at risk.</div>';
  let mx=Math.max(1,...d.products.map(x=>x.count));
  $('#mcProducts').innerHTML=d.products.map(x=>`<div class="barrow"><span>${esc(x.name)}</span><div class="bartrack"><div class="barfill" style="width:${x.count/mx*100}%"></div></div><b>${x.count}</b></div>`).join('');
  $('#mcGoals').innerHTML=`<div class="goalring" style="--goal:${d.goals.percent}"><div><span><strong>${d.goals.percent}%</strong><br><small>${d.goals.completed}/${d.goals.target}</small></span></div></div><p class="muted" style="text-align:center">Weekly selling actions</p>`;
  $('#mcCampaigns').innerHTML=`<p>Active <b style="float:right">${d.campaigns.active}</b></p><p>Queued <b style="float:right">${d.campaigns.queued}</b></p><p>Sent <b style="float:right">${d.campaigns.sent}</b></p><p>Failed <b style="float:right">${d.campaigns.failed}</b></p>`;
}
async function runStartMyDay(){
  const b=$('#startMyDayBtn');
  if(!b||b.disabled)return;
  b.disabled=true;
  b.innerHTML='Preparing your day…';
  try{
    const d=await api('/api/start-my-day',{method:'POST',body:'{}'});
    msg(`${d.call_list} calls prioritized · ${d.drafts_created} drafts created · ${d.followups_created} follow-ups created`);
    await Promise.all([missionControl(),dailyPlan(),outreach(),followups()]);
    show('daily');
  }catch(e){
    console.error('Start My Day failed',e);
    msg(e.message||'Unable to prepare the day');
  }finally{
    b.disabled=false;
    b.innerHTML='<span>▶</span> Start My Day';
  }
}
document.addEventListener('DOMContentLoaded',()=>{
  initProfessionalShell();
  const b=$('#startMyDayBtn');
  if(b)b.addEventListener('click',runStartMyDay);
});
async function quickDraft(id){let d=await api('/api/start-my-day',{method:'POST',body:JSON.stringify({prospect_id:id})});msg(d.drafts_created?'Personalized draft created':'A draft already exists for this account today');outreach();show('outreach')}
async function campaigns(){let d=await api('/api/campaigns');$('#campaignMode').textContent=d.live_email||d.live_sms?'Live delivery enabled':'Provider setup required';$('#autoState').textContent=d.scheduler_ready?'Cron ready':'Add secret';$('#emailState').textContent=d.live_email?'Connected':'Not connected';$('#smsState').textContent=d.live_sms?'Connected':'Not connected';$('#dueNow').textContent=d.due_now||0;$('#automationHelp').innerHTML=d.scheduler_ready?'Render scheduler endpoint is secured and ready. Set a Cron Job to call <b>/api/automation/run</b> every 5–15 minutes.':'Add <b>CAMPAIGN_AUTOMATION_SECRET</b> in Render, then create a Render Cron Job using the included setup guide.';$('#campaignList').innerHTML=d.items.length?d.items.map(x=>`<div class="campaign-row"><div class="profile-head"><div><b>${esc(x.name)}</b> <span class="pill">${esc(x.channel)}</span><div class="mini">${esc(x.status)} · Scheduled ${esc((x.scheduled_at||'Immediately').replace('T',' '))}${x.sequence_name?' · '+esc(x.sequence_name):''}</div></div><div><button class="btn smallbtn" onclick="toggleCampaign(${x.id},'${x.status==='Paused'?'Active':'Paused'}')">${x.status==='Paused'?'Resume':'Pause'}</button></div></div><div class="campaign-stats"><div><b>${x.total}</b><small>Total</small></div><div><b>${x.queued}</b><small>Queued</small></div><div><b>${x.sent}</b><small>Sent</small></div><div><b>${x.failed}</b><small>Failed</small></div><div><b>${x.suppressed}</b><small>Suppressed</small></div></div></div>`).join(''):'<div class="empty">No campaigns created yet.</div>'}
async function toggleCampaign(id,status){await api('/api/campaigns/'+id+'/status',{method:'POST',body:JSON.stringify({status})});msg('Campaign updated');campaigns();missionControl()}
$('#previewCampaign').onclick=previewCampaign;$('#saveCampaign').onclick=async()=>{let d=await api('/api/campaigns',{method:'POST',body:JSON.stringify(campaignPayload())});msg(`Campaign queued for ${d.queued} contacts`);campaigns();missionControl()};$('#processCampaigns').onclick=async()=>{let d=await api('/api/campaigns/process',{method:'POST'});msg(`${d.sent} sent · ${d.failed} failed · ${d.skipped} skipped`);campaigns();missionControl()};

const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(Number(n||0));
async function boss(){let days=$('#execPeriod')?.value||90,d=await api('/api/executive?days='+days);$('#eFunded').textContent=money(d.funded_volume);$('#eUnits').textContent=d.funded_units;$('#eRevenue').textContent=money(d.actual_revenue);$('#eProjected').textContent=money(d.projected_volume);let stages={...d.pipeline,Application:d.outcomes.Application,Submitted:d.outcomes.Submitted,Funded:d.outcomes.Funded};let max=Math.max(1,...Object.values(stages));$('#execFunnel').innerHTML=Object.entries(stages).map(([k,v])=>`<div class=barrow><span>${esc(k)}</span><div class=bartrack><div class=barfill style="width:${v/max*100}%"></div></div><b>${v}</b></div>`).join('');$('#execConversion').innerHTML=Object.entries(d.conversion).map(([k,v])=>`<div class=scorebox><small>${esc(k.replaceAll('_',' '))}</small><strong>${v}%</strong></div>`).join('');$('#execCampaigns').innerHTML=d.campaigns.length?`<div style="overflow:auto"><table><thead><tr><th>Campaign</th><th>Sent</th><th>Replies</th><th>Applications</th><th>Fundings</th><th>Funded volume</th></tr></thead><tbody>${d.campaigns.map(x=>`<tr><td><b>${esc(x.name)}</b><div class=mini>${esc(x.channel)}</div></td><td>${x.sent}</td><td>${x.replied}</td><td>${x.applications}</td><td>${x.fundings}</td><td>${money(x.funded_volume)}</td></tr>`).join('')}</tbody></table></div>`:'<div class=empty>No campaigns yet.</div>';$('#execTop').innerHTML=d.top_accounts.map((x,i)=>`<div class=top-account><div class=rank>#${i+1}</div><div><b>${esc(x.company)}</b><div class=mini>${esc(x.city||'')}, ${esc(x.state||'')} · ${esc(x.status||'')}</div></div><div><span class=tag>${x.applications||0} apps</span><span class=tag>${x.fundings||0} funded</span></div><div class=score>${money(x.funded_volume)}</div></div>`).join('')||'<div class=empty>No outcomes logged yet.</div>';$('#execRecent').innerHTML=d.recent_events.map(x=>`<div><b>${esc(x.company)} · ${esc(x.event_type)}</b><div class=mini>${money(x.amount)} · ${esc((x.event_at||'').replace('T',' '))}${x.campaign_name?' · attributed to '+esc(x.campaign_name):''}</div></div>`).join('')||'<div class=empty>No recorded outcomes yet.</div>';$('#revenueSettings').innerHTML=Object.entries(d.settings).map(([k,v])=>`<label>${esc(k.replaceAll('_',' '))}<input class="full rev-setting" data-key="${esc(k)}" type=number step="${k.includes('rate')?'.01':'1'}" value="${v}"></label>`).join('');let ps=await api('/api/prospects');$('#revProspect').innerHTML=ps.map(x=>`<option value=${x.id}>${esc(x.company)}</option>`).join('');if(!$('#revDate').value)$('#revDate').value=new Date().toISOString().slice(0,16)}
$('#saveRevenue').onclick=async()=>{let d=await api('/api/revenue-events',{method:'POST',body:JSON.stringify({prospect_id:$('#revProspect').value,event_type:$('#revType').value,amount:$('#revAmount').value,loan_count:$('#revCount').value,event_at:$('#revDate').value,notes:$('#revNotes').value})});msg(d.attributed_campaign?`Outcome saved and attributed to ${d.attributed_campaign.name}`:'Outcome saved');boss()};
$('#saveRevenueSettings').onclick=async()=>{let settings={};$$('.rev-setting').forEach(x=>settings[x.dataset.key]=x.value);await api('/api/revenue-settings',{method:'POST',body:JSON.stringify({settings})});msg('Projection assumptions saved');boss()};

async function voiceAgent(){let d=await api('/api/voice-agent');$('#voiceStatus').textContent=d.connected?'Twilio connected · female voice':'Setup required';$('#voiceStatus').className='pill';$('#voiceContacts').innerHTML=d.contacts.length?d.contacts.map(x=>`<div class="contact-card"><div class="contact-line"><div><b>${esc(x.name||'Unnamed contact')}</b><div class="mini">${esc(x.company)} · ${esc(x.phone||'No phone')}</div></div><span class="pill">${x.voice_consent?'Consent recorded':'No consent'}</span></div><div class="contact-actions"><button class="btn smallbtn" onclick="setVoiceConsent(${x.id},${x.voice_consent?0:1})">${x.voice_consent?'Remove consent':'Record consent'}</button><button class="btn primary smallbtn" ${(!x.voice_consent||!x.phone||!d.connected)?'disabled':''} onclick="startVoiceCall(${x.id})">Call with Ash</button></div></div>`).join(''):'<div class="empty">No contacts with callable phone numbers.</div>';$('#voiceAppointments').innerHTML=d.appointments.length?d.appointments.map(x=>`<div class="timeline-item"><b>${esc(x.company)} · ${esc(x.name)}</b><div class="mini">${esc((x.start_at||'').replace('T',' '))} · ${esc(x.status)}</div></div>`).join(''):'<div class="empty">No AI-scheduled appointments yet.</div>';$('#voiceCalls').innerHTML=d.calls.length?d.calls.map(x=>`<div class="timeline-item"><b>${esc(x.company)} · ${esc(x.name)}</b><div class="mini">${esc(x.status)}${x.answered_by?' · '+esc(x.answered_by):''} · ${esc((x.created_at||'').replace('T',' '))}</div></div>`).join(''):'<div class="empty">No voice calls yet.</div>'}
async function setVoiceConsent(id,value){await api('/api/voice-agent/consent',{method:'POST',body:JSON.stringify({contact_id:id,consent:value})});msg(value?'Voice consent recorded':'Voice consent removed');voiceAgent()}
async function startVoiceCall(id){if(!confirm('Place a disclosed automated call to this consented contact now?'))return;let d=await api('/api/voice-agent/call',{method:'POST',body:JSON.stringify({contact_id:id})});msg('Call queued · '+d.status);voiceAgent()}
async function ints(){let d=await api('/api/integrations');$$('[data-key]').forEach(x=>{x.checked=d[x.dataset.key];x.onchange=()=>api('/api/integrations',{method:'POST',body:JSON.stringify({key:x.dataset.key,value:x.checked})})})}
if(document.body.dataset.demo==='1'){
  const banner=document.createElement('div');banner.className='demo-banner';banner.innerHTML='<b>Executive demo mode</b> · Explore every workflow. Data-changing actions are disabled.';document.querySelector('main').insertBefore(banner,document.querySelector('.top').nextSibling);
  const badge=document.createElement('span');badge.className='pill';badge.textContent='FULL-FEATURE READ-ONLY DEMO';document.querySelector('.top small').after(badge);
  document.querySelectorAll('#import,#add,#queue,#gen,#msave,#form button[type="submit"],#importForm button[type="submit"],#actionForm button[type="submit"],#saveContact,[data-key]').forEach(x=>{x.disabled=true;x.classList.add('demo-lock');x.title='Disabled in executive demo mode'});
  document.querySelectorAll('#subject,#body,#mnote,#mdate,#mtype,#actionType,#actionOutcome,#actionNotes,#actionFollow').forEach(x=>{x.disabled=true;x.classList.add('demo-lock')});
  document.querySelectorAll('.actions a').forEach(x=>x.style.display='none');
  show('dashboard');
}

let templateChannel='Email',templateCache=[],sequenceCache=[];
function templateTokens(){return `<div class="contact-note">Fields: {{first_name}}, {{full_name}}, {{company}}, {{city}}, {{state}}, {{specialties}}, {{my_name}}, {{my_company}}.</div>`}
async function templateStudio(){let [t,sq,a]=await Promise.all([api('/api/templates'),api('/api/sequences'),api('/api/campaigns/analytics')]);templateCache=t.items;sequenceCache=sq.items;$('#tplEmailCount').textContent=t.items.filter(x=>x.channel==='Email').length;$('#tplSmsCount').textContent=t.items.filter(x=>x.channel==='SMS').length;$('#seqCount').textContent=sq.items.length;$('#replyRate').textContent=(a.summary.reply_rate||0)+'%';renderTemplateList();$('#campaignAnalytics').innerHTML=[['Sent',a.summary.sent],['Delivered',a.summary.delivered],['Opened',a.summary.opened],['Clicked',a.summary.clicked],['Replied',a.summary.replied],['Opt-outs',a.summary.opted_out]].map(x=>`<div><b>${x[1]}</b><small>${x[0]}</small></div>`).join('');$('#campaignPerformance').innerHTML=a.campaigns.length?`<table><thead><tr><th>Campaign</th><th>Channel</th><th>Sent</th><th>Opened</th><th>Clicked</th><th>Replied</th></tr></thead><tbody>${a.campaigns.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.channel)}</td><td>${x.sent}</td><td>${x.opened}</td><td>${x.clicked}</td><td>${x.replied}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">No delivery analytics yet.</div>'}
function renderTemplateList(){let q=($('#templateSearch')?.value||'').toLowerCase();$$('[data-lib]').forEach(b=>b.classList.toggle('active',b.dataset.lib===templateChannel));let list=templateChannel==='Sequences'?sequenceCache:templateCache.filter(x=>x.channel===templateChannel);list=list.filter(x=>!q||[x.name,x.category,x.subject,x.body].join(' ').toLowerCase().includes(q));$('#templateList').innerHTML=list.map(x=>`<div class="template-item" onclick="${templateChannel==='Sequences'?'editSequence':'editTemplate'}(${x.id})"><b>${esc(x.name)}</b><small>${esc(x.category||'Sequence')} ${x.channel?'· '+esc(x.channel):''}</small></div>`).join('')||'<div class="empty">No matching items.</div>'}
$$('[data-lib]').forEach(b=>b.onclick=()=>{templateChannel=b.dataset.lib;renderTemplateList();$('#templateEditor').innerHTML='<h3>Choose a '+(templateChannel==='Sequences'?'sequence':'template')+'</h3>'});$('#templateSearch').oninput=renderTemplateList;
function editTemplate(id){let x=templateCache.find(y=>y.id===id);if(!x)return;$('#templateEditor').innerHTML=`<div class="profile-head"><div><div class="kicker">${esc(x.category)}</div><h3>${esc(x.name)}</h3></div><span class="pill">${esc(x.channel)}</span></div><label>Template name<input id="teName" class="full" value="${esc(x.name)}"></label><label>Category<input id="teCategory" class="full" value="${esc(x.category)}"></label>${x.channel==='Email'?`<label>Subject<input id="teSubject" class="full" value="${esc(x.subject||'')}"></label>`:''}<label>Message<textarea id="teBody">${esc(x.body)}</textarea></label>${templateTokens()}<label>Personalize for prospect<select id="teProspect" class="full"><option value="">Choose a prospect</option>${P.map(p=>`<option value="${p.id}">${esc(p.company)}</option>`).join('')}</select></label><div class="tone-row"><button class="btn active" data-tone="Conversational">Conversational</button><button class="btn" data-tone="Professional">Professional</button><button class="btn" data-tone="Concise">Concise</button><button class="btn" data-tone="Warm">Warm</button></div><div class="contact-tools"><button class="btn" onclick="personalizeTemplate(${x.id})">AI personalize</button><button class="btn" onclick="loadTemplateCampaign(${x.id})">Use in campaign</button><button class="btn primary" onclick="saveTemplate(${x.id})">Save changes</button></div><div id="personalizedPreview"></div>`;$$('[data-tone]').forEach(b=>b.onclick=()=>{$$('[data-tone]').forEach(z=>z.classList.toggle('active',z===b))})}
async function saveTemplate(id){let x=templateCache.find(y=>y.id===id);await api('/api/templates/'+id,{method:'PUT',body:JSON.stringify({name:$('#teName').value,category:$('#teCategory').value,subject:x.channel==='Email'?$('#teSubject').value:'',body:$('#teBody').value})});msg('Template saved');templateStudio()}
async function personalizeTemplate(id){let pid=+($('#teProspect').value||0);if(!pid)return msg('Choose a prospect');let tone=document.querySelector('[data-tone].active')?.dataset.tone||'Conversational';let d=await api('/api/templates/'+id+'/personalize',{method:'POST',body:JSON.stringify({prospect_id:pid,tone})});$('#teSubject')&&($('#teSubject').value=d.subject||'');$('#teBody').value=d.body;$('#personalizedPreview').innerHTML='<div class="callout" style="margin-top:10px"><b>Personalized for '+esc(d.company)+'</b><br><small>'+esc(d.reason)+'</small></div>';msg('Message personalized')}
function loadTemplateCampaign(id){let x=templateCache.find(y=>y.id===id);$('#campChannel').value=x.channel==='SMS'?'SMS':'Email';$('#campName').value=x.name;$('#campSubject').value=x.subject||'';$('#campBody').value=x.body;show('campaigns');msg('Template loaded into campaign builder')}
function editSequence(id){let x=sequenceCache.find(y=>y.id===id);if(!x)return;$('#templateEditor').innerHTML=`<div class="profile-head"><div><div class="kicker">AUTOMATED SEQUENCE</div><h3>${esc(x.name)}</h3><p class="muted">${esc(x.description||'')}</p></div><button class="btn primary" onclick="launchSequence(${x.id})">Launch sequence</button></div><div>${x.steps.map((st,i)=>`<div class="sequence-step"><div class="day">Day ${st.delay_days}</div><span class="pill">${esc(st.channel)}</span><div><b>${esc(st.name)}</b><div class="mini">${esc(st.subject||st.body.slice(0,90))}</div></div><button class="btn smallbtn" onclick="editSequenceStep(${st.id},${x.id})">Edit</button></div>`).join('')}</div><div class="callout">Sequences automatically stop for a contact when the relationship is marked Replied, Meeting, Approved, or the recipient opts out.</div>`}
async function editSequenceStep(stepId,seqId){let x=sequenceCache.find(y=>y.id===seqId),st=x.steps.find(y=>y.id===stepId);$('#templateEditor').innerHTML+=`<div class="step-editor"><h4>Edit ${esc(st.name)}</h4><div class="formgrid"><label>Day<input id="seDay" type="number" min="0" value="${st.delay_days}"></label><label>Channel<select id="seChannel"><option ${st.channel==='Email'?'selected':''}>Email</option><option ${st.channel==='SMS'?'selected':''}>SMS</option><option ${st.channel==='Task'?'selected':''}>Task</option></select></label></div><label>Subject<input id="seSubject" class="full" value="${esc(st.subject||'')}"></label><label>Message / task<textarea id="seBody">${esc(st.body)}</textarea></label><button class="btn primary" onclick="saveSequenceStep(${stepId})">Save step</button></div>`}
async function saveSequenceStep(id){await api('/api/sequence-steps/'+id,{method:'PUT',body:JSON.stringify({delay_days:+$('#seDay').value,channel:$('#seChannel').value,subject:$('#seSubject').value,body:$('#seBody').value})});msg('Sequence step saved');templateStudio()}
async function launchSequence(id){let x=sequenceCache.find(y=>y.id===id);$('#templateEditor').innerHTML+=`<div class="step-editor"><h4>Launch ${esc(x.name)}</h4><div class="formgrid"><label>Minimum score<input id="lsScore" type="number" value="70"></label><label>State<select id="lsState"><option value="">All states</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select></label><label>Start date<input id="lsStart" type="date"></label><label>Daily limit<input id="lsLimit" type="number" value="35"></label></div><button class="btn primary" onclick="confirmLaunchSequence(${id})">Create sequence campaign</button></div>`}
async function confirmLaunchSequence(id){let d=await api('/api/sequences/'+id+'/launch',{method:'POST',body:JSON.stringify({min_score:+$('#lsScore').value,state:$('#lsState').value,start_date:$('#lsStart').value,daily_limit:+$('#lsLimit').value})});msg(`${d.enrollments} contacts enrolled · ${d.messages} touches scheduled`);campaigns();missionControl()}

let inboxCache=[];
async function replyInbox(){let d=await api('/api/inbox');inboxCache=d.messages;$('#inNeeds').textContent=d.summary.needs_attention;$('#inPositive').textContent=d.summary.positive;$('#inQuestions').textContent=d.summary.questions;$('#inStopped').textContent=d.summary.sequences_stopped;$('#inboxList').innerHTML=d.messages.length?d.messages.map(x=>`<div class="person-card" onclick="openReply(${x.id})" style="cursor:pointer"><div class="person-top"><div><b>${esc(x.sender_name||x.sender_email)}</b><div class="person-meta">${esc(x.company||'Unmatched contact')} · ${esc(x.received_at)}</div></div><span class="pill">${esc(x.classification)}</span></div><div style="margin-top:8px">${esc(x.subject||'(no subject)')}</div><div class="mini">${esc((x.body||'').slice(0,150))}</div></div>`).join(''):'<div class="empty">No inbound replies yet.</div>'}
function openReply(id){let x=inboxCache.find(y=>y.id===id);if(!x)return;$('#inboxDetail').innerHTML=`<div class="kicker">${esc(x.classification)} · ${esc(x.sentiment)}</div><h3>${esc(x.subject||'(no subject)')}</h3><p class="muted">From ${esc(x.sender_name||'')} &lt;${esc(x.sender_email)}&gt;</p><div class="callout" style="white-space:pre-wrap">${esc(x.body)}</div><label>Suggested response<input id="replySubject" class="full" value="${esc(x.suggested_subject||'Re: '+x.subject)}"></label><textarea id="replyDraft">${esc(x.suggested_reply||'')}</textarea><div class="contact-tools"><button class="btn primary" onclick="queueReply(${id})">Queue email reply</button><button class="btn" onclick="resolveReply(${id})">Mark resolved</button></div>`}
async function syncInbox(){try{let d=await api('/api/inbox/sync',{method:'POST',body:'{}'});msg(`${d.imported} new replies synced`);replyInbox()}catch(e){msg(e.message)}}
async function resolveReply(id){await api('/api/inbox/'+id+'/resolve',{method:'POST',body:'{}'});msg('Reply resolved');replyInbox()}
async function queueReply(id){let d=await api('/api/inbox/'+id+'/queue-reply',{method:'POST',body:JSON.stringify({subject:$('#replySubject').value,body:$('#replyDraft').value})});msg('Response added to outreach queue');show('outreach');outreach()}
async function manualInbound(){let sender=prompt('Sender email');if(!sender)return;let body=prompt('Reply message');if(!body)return;await api('/api/inbox/manual',{method:'POST',body:JSON.stringify({sender_email:sender,subject:'Manual reply',body})});replyInbox();msg('Reply captured')}


let OI=null;
let SC={items:[],summary:{}};
async function salesCoach(){
  try{
    SC=await api('/api/sales-coach');
    $('#scCallToday').textContent=SC.summary.call_today||0;
    $('#scAtRisk').textContent=SC.summary.at_risk||0;
    $('#scHighResponse').textContent=SC.summary.high_response||0;
    $('#scProductMatched').textContent=SC.summary.product_matched||0;
    renderSalesCoach();
  }catch(e){$('#scQueue').innerHTML=`<div class="empty">Unable to load sales coaching: ${esc(e.message)}</div>`}
}
function renderSalesCoach(){
  let filter=$('#scFilter')?.value||'All';let items=SC.items||[];
  if(filter==='Call Today')items=items.filter(x=>x.recommended_action==='Call today');
  if(filter==='At Risk')items=items.filter(x=>x.relationship_health==='At Risk');
  if(filter==='High Response')items=items.filter(x=>x.response_likelihood>=75);
  $('#scQueue').innerHTML=items.length?items.map(x=>`<article class="coach-card">
    <div class="coach-card-head"><div><div class="coach-company">${esc(x.company)}</div><div class="coach-meta"><span class="pill">Score ${x.opportunity_score}</span><span class="coach-action-label coach-health-${x.relationship_health.toLowerCase().replaceAll(' ','-')}">${esc(x.relationship_health)}</span><span class="coach-action-label">${esc(x.recommended_action)}</span>${x.contact_name?`<span class="pill">${esc(x.contact_name)}</span>`:''}</div></div><div class="coach-score"><strong>${x.response_likelihood}%</strong><small>Modeled response likelihood</small></div></div>
    <div class="coach-grid"><div class="coach-block"><b>Why today</b><p>${esc(x.why_today)}</p></div><div class="coach-block"><b>Opportunity</b><p>${esc(x.opportunity)}</p></div><div class="coach-block"><b>Likely objection</b><p>${esc(x.likely_objection||'No objection has been recorded yet.')}</p></div><div class="coach-block coach-opening"><b>Suggested opening</b><p>“${esc(x.suggested_opening)}”</p></div></div>
    <div class="coach-reasons">${(x.evidence||[]).map(r=>`<span class="tag">${esc(r)}</span>`).join('')}</div>
    <div class="coach-actions"><button class="btn primary smallbtn" onclick="prepareCoachAccount(${x.prospect_id})">Prepare this account</button><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Open intelligence</button>${x.phone?`<a class="btn smallbtn" href="${telHref(x.phone)}">Call</a>`:''}${x.email?`<a class="btn smallbtn" href="${mailHref(x.email)}">Email</a>`:''}</div>
  </article>`).join(''):'<div class="empty">No accounts match this coaching filter.</div>';
}
async function prepareCoachAccount(id){
  try{let d=await api('/api/start-my-day',{method:'POST',body:JSON.stringify({prospect_id:id})});msg(`Account prepared · ${d.drafts_created} draft · ${d.followups_created} follow-up`);await Promise.all([missionControl(),dailyPlan(),outreach(),followups()]);}
  catch(e){msg('Unable to prepare account: '+e.message)}
}
async function loadIntelligence(){OI=await api('/api/intelligence');$('#oiHot').textContent=OI.summary.hot;$('#oiWarm').textContent=OI.summary.warm;$('#oiDue').textContent=OI.summary.due_today;$('#oiMatched').textContent=OI.summary.product_matches;renderIntelligence();$('#oiSettings').innerHTML=OI.settings.map(x=>`<div class="memory-item"><div class="profile-head"><div><b>${esc(x.label)}</b><div class="muted">${esc(x.description)}</div></div><input style="width:76px" type="number" min="0" max="40" data-weight="${esc(x.key)}" value="${x.weight}"></div></div>`).join('');$('#oiProducts').innerHTML=OI.products.map(x=>`<div class="memory-item"><b>${esc(x.name)}</b> <span class="pill">${esc(x.category)}</span><div class="muted" style="margin-top:5px">${esc(x.talking_point)}</div></div>`).join('')}
function renderIntelligence(){if(!OI)return;let tier=$('#oiTier').value;let xs=OI.opportunities.filter(x=>tier==='All'||x.tier===tier);$('#oiRows').innerHTML=xs.slice(0,50).map(x=>`<div class="priority-card"><div class="orb" style="--s:${x.score}">${x.score}</div><div><div><b>${esc(x.company)}</b> <span class="pill">${esc(x.tier)}</span> <span class="mini">${x.confidence}% confidence</span></div><div class="reason"><b>Next:</b> ${esc(x.next_action)}</div><div>${x.products.map(p=>`<span class="tag" title="${esc(p.talking_point)}">${esc(p.name)} · ${p.strength}</span>`).join('')}</div><div class="mini">${x.reasons.slice(0,3).map(r=>`+${r.points} ${esc(r.reason)}`).join(' · ')}</div></div><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Open</button></div>`).join('')||'<div class="empty">No opportunities in this tier.</div>'}
async function saveIntelligenceSettings(){let weights={};$$('[data-weight]').forEach(x=>weights[x.dataset.weight]=+x.value);await api('/api/intelligence/settings',{method:'POST',body:JSON.stringify({weights})});msg('Scoring weights saved');await rescoreIntelligence()}
async function rescoreIntelligence(){let d=await api('/api/intelligence/rescore',{method:'POST'});msg(`${d.updated} prospects rescored`);await loadIntelligence();missionControl();load()}

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


def seed_templates(c):
    if c.execute("select count(*) from message_templates").fetchone()[0]==0:
        email=[
        ('New Broker Congratulations','Congratulations','Congratulations on {{company}}','Hi {{first_name}},\n\nCongratulations on the growth of {{company}}. I am Clay with Union Home Mortgage Wholesale, and I wanted to introduce myself as a resource whenever you need another lending option.\n\nWe support conventional, FHA, VA, USDA, jumbo, HELOC, renovation, down-payment-assistance, and lower-FICO government scenarios. I would appreciate the opportunity to help with a difficult file or provide a quick second opinion.\n\nThanks,\nClay Carr'),
        ('First Introduction','Introduction','Another lending resource for {{company}}','Hi {{first_name}},\n\nI wanted to introduce myself as a wholesale lending resource for {{company}}. My goal is not to replace your existing partners—just to be available when you need strong pricing, fast scenario help, or another option for a difficult file.\n\nWould a brief introduction next week be useful?\n\nClay Carr\nUnion Home Mortgage Wholesale'),
        ('Reactivation Check-In','Reactivation','Checking in with {{company}}','Hi {{first_name}},\n\nIt has been a little while since we connected, so I wanted to check in. Are there any scenarios on your desk that could use another set of eyes?\n\nI am happy to help with pricing, structuring, or difficult government files.\n\nClay'),
        ('Scenario Support','Follow-up','Anything I can help structure?','Hi {{first_name}},\n\nDo you have any files this week that could use a second look? I can help with conventional through lower-FICO government scenarios, plus HELOC and niche options.\n\nSend over the basics whenever convenient and I will take a look.\n\nClay'),
        ('VA Opportunity','Product: VA','VA scenario support for {{company}}','Hi {{first_name}},\n\nI noticed {{company}} may be a strong fit for additional VA support. Union Home Mortgage Wholesale can help with VA purchases, refinances, and challenging scenarios.\n\nI would be glad to compare a live file or provide a quick eligibility review.\n\nClay'),
        ('FHA & Low-FICO','Product: FHA','Another option for difficult FHA files','Hi {{first_name}},\n\nWhen an FHA file gets difficult because of credit, ratios, or layered risk, I would be happy to provide a second look. We support a broad range of government scenarios and focus on finding a responsible path forward.\n\nClay'),
        ('Down Payment Assistance','Product: DPA','Local down-payment-assistance options','Hi {{first_name}},\n\nI wanted to make sure you knew we support local down-payment-assistance programs that may help qualified first-time and repeat buyers.\n\nI would be glad to review a borrower scenario or send a quick program overview for your market.\n\nClay'),
        ('HELOC Introduction','Product: HELOC','HELOC options without replacing the first mortgage','Hi {{first_name}},\n\nFor homeowners who need equity access but want to keep their existing first mortgage, we offer HELOC options that may be worth comparing.\n\nLet me know if you have a borrower who needs cash without a full refinance.\n\nClay'),
        ('Jumbo & Niche','Product: Jumbo','Jumbo and niche scenario support','Hi {{first_name}},\n\nI am reaching out because {{company}} appears well positioned for jumbo or niche scenarios. I would be glad to help compare structure, pricing, and documentation options on a current file.\n\nClay'),
        ('Renovation Lending','Product: Renovation','Financing the purchase and improvements','Hi {{first_name}},\n\nWhen a property needs work, renovation financing can help borrowers combine the purchase and eligible improvements. I would be happy to help structure a scenario or confirm whether the property and project fit.\n\nClay'),
        ('Pricing Improvement','Market Update','A quick pricing update','Hi {{first_name}},\n\nWe have seen some useful pricing opportunities, and I wanted to offer a comparison on anything you are quoting today. No obligation—just another data point for your borrower.\n\nClay'),
        ('After Voicemail','Follow-up','Following up on my voicemail','Hi {{first_name}},\n\nI just left you a quick voicemail. There is no rush to respond; I simply wanted to introduce myself and let you know I am available whenever {{company}} needs another lending option or scenario review.\n\nClay'),
        ('Meeting Follow-Up','Meeting','Thank you for your time','Hi {{first_name}},\n\nThank you for taking the time to speak with me. I appreciated learning more about {{company}} and the types of borrowers you serve.\n\nI will follow up on the items we discussed and remain available for any scenarios that come up.\n\nClay'),
        ('Broker Appreciation','Relationship','Appreciate the opportunity to help','Hi {{first_name}},\n\nI appreciate every opportunity {{company}} gives us to help. Thank you for the partnership and for trusting me with your borrowers and scenarios.\n\nClay'),
        ('Referral Request','Relationship','Who else could use another lending resource?','Hi {{first_name}},\n\nI am glad we have had the chance to work together. If you know another broker or loan officer who could use a responsive wholesale lending resource, I would appreciate an introduction.\n\nClay'),
        ('Post-Closing Thank You','Post-closing','Thank you for the closing','Hi {{first_name}},\n\nThank you for the opportunity to help close this loan. I appreciate the teamwork and look forward to supporting the next borrower.\n\nClay'),
        ('New Year Greeting','Holiday','Happy New Year','Hi {{first_name}},\n\nHappy New Year to you and the team at {{company}}. I hope the year brings strong production, smooth closings, and plenty of opportunities. I am here whenever you need scenario support.\n\nClay'),
        ('Thanksgiving Greeting','Holiday','Happy Thanksgiving','Hi {{first_name}},\n\nHappy Thanksgiving to you and everyone at {{company}}. I appreciate the relationship and hope you have a wonderful holiday.\n\nClay'),
        ('Christmas Greeting','Holiday','Merry Christmas','Hi {{first_name}},\n\nMerry Christmas to you and the team at {{company}}. I hope you have a relaxing holiday and a strong finish to the year.\n\nClay'),
        ('Thirty-Day Final Check-In','Sequence','Still available whenever you need me','Hi {{first_name}},\n\nI wanted to make one final check-in for now. I am available whenever {{company}} needs a pricing comparison, a difficult-file review, or another lending option.\n\nI will stay in touch periodically, and you are always welcome to reach out directly.\n\nClay')]
        sms=[
        ('SMS Introduction','Introduction','', 'Hi {{first_name}}, this is Clay with Union Home Mortgage Wholesale. I wanted to introduce myself as another lending resource for {{company}}. Reply STOP to opt out.'),
        ('SMS Quick Check-In','Follow-up','', 'Hi {{first_name}}, do you have any scenarios this week that could use a second look? Clay with Union Home Mortgage Wholesale. Reply STOP to opt out.'),
        ('SMS After Voicemail','Follow-up','', 'Hi {{first_name}}, I just left you a quick voicemail. No rush—I am here whenever you need another lending option. Clay, UHM Wholesale. Reply STOP to opt out.'),
        ('SMS Pricing Update','Market Update','', 'Morning {{first_name}}—I have some useful pricing opportunities today and would be glad to compare anything you are quoting. Clay, UHM Wholesale. Reply STOP to opt out.'),
        ('SMS VA','Product: VA','', 'Hi {{first_name}}, we are available to help with VA purchases, refinances, and difficult scenarios. Send me anything you would like compared. Reply STOP to opt out.'),
        ('SMS FHA Low-FICO','Product: FHA','', 'Hi {{first_name}}, I can help review difficult FHA or lower-credit government scenarios. Happy to be a second set of eyes. Reply STOP to opt out.'),
        ('SMS HELOC','Product: HELOC','', 'Hi {{first_name}}, we have HELOC options for borrowers who want equity access without replacing their first mortgage. Happy to review a scenario. Reply STOP to opt out.'),
        ('SMS DPA','Product: DPA','', 'Hi {{first_name}}, we support local down-payment-assistance options. I would be glad to review eligibility on a borrower scenario. Reply STOP to opt out.'),
        ('SMS Meeting Reminder','Meeting','', 'Hi {{first_name}}, looking forward to our conversation today. This is Clay with Union Home Mortgage Wholesale. Reply STOP to opt out.'),
        ('SMS Thank You','Relationship','', 'Thanks for the opportunity to help, {{first_name}}. I appreciate the partnership with {{company}}. Clay, UHM Wholesale. Reply STOP to opt out.'),
        ('SMS Holiday','Holiday','', 'Hi {{first_name}}, wishing you and the team at {{company}} a wonderful holiday. Clay with Union Home Mortgage Wholesale. Reply STOP to opt out.'),
        ('SMS Final Check-In','Sequence','', 'Hi {{first_name}}, I will close the loop for now, but I am always available for pricing or scenario help. Clay, UHM Wholesale. Reply STOP to opt out.')]
        for name,cat,subject,body in email:
            c.execute("insert into message_templates(name,channel,category,subject,body,is_system,created_at,updated_at) values(?,?,?,?,?,1,?,?)",(name,'Email',cat,subject,body,NOW(),NOW()))
        for name,cat,subject,body in sms:
            c.execute("insert into message_templates(name,channel,category,subject,body,is_system,created_at,updated_at) values(?,?,?,?,?,1,?,?)",(name,'SMS',cat,subject,body,NOW(),NOW()))
    if c.execute("select count(*) from sequences").fetchone()[0]==0:
        sequences=[
          ('30-Day New Broker Introduction','Six-touch introduction sequence with email, consented SMS, value-add follow-ups, and a final check-in.',[(0,'Email','Introduction','Another lending resource for {{company}}','Hi {{first_name}},\n\nI wanted to introduce myself as another wholesale lending resource for {{company}}. I can help with conventional, government, HELOC, DPA, jumbo, and difficult scenarios.\n\nWould a brief introduction next week be useful?\n\nClay Carr'),(3,'SMS','Quick text follow-up','', 'Hi {{first_name}}, this is Clay with UHM Wholesale. I am available whenever you need another lending option. Reply STOP to opt out.'),(7,'Email','Product value','A useful option for {{company}}','Hi {{first_name}},\n\nBased on {{company}} and your market, I thought our {{specialties}} support could be useful. I would be glad to compare a live scenario.\n\nClay'),(14,'Task','Personal call task','', 'Call {{full_name}} at {{company}} and ask what type of file is hardest to place right now.'),(21,'Email','Scenario check-in','Anything I can help structure?','Hi {{first_name}},\n\nDo you have anything this week that could use a second look? I am happy to help with structure or pricing.\n\nClay'),(30,'Email','Final check-in','Still available whenever you need me','Hi {{first_name}},\n\nI will close the loop for now, but I remain available whenever {{company}} needs another lending option.\n\nClay')]),
          ('Government Lending Opportunity','Four-touch FHA/VA/DPA sequence.',[(0,'Email','Government introduction','Government-loan support for {{company}}','Hi {{first_name}},\n\nI wanted to introduce our FHA, VA, USDA, and local DPA support. I would be glad to review a difficult government scenario.\n\nClay'),(5,'Task','Call task','', 'Call {{full_name}} and ask about current FHA, VA, or DPA volume.'),(10,'Email','Low-FICO value','Another look at difficult government files','Hi {{first_name}},\n\nWhen a government file is difficult because of credit, ratios, or layered risk, I would be glad to provide a responsible second look.\n\nClay'),(18,'SMS','Government check-in','', 'Hi {{first_name}}, any FHA, VA, or DPA scenarios I can review this week? Clay, UHM Wholesale. Reply STOP to opt out.')]),
          ('Dormant Relationship Reactivation','Four-touch reactivation sequence for inactive broker relationships.',[(0,'Email','Reconnect','Checking in with {{company}}','Hi {{first_name}},\n\nIt has been a while since we connected. Are there any scenarios on your desk that could use another option?\n\nClay'),(4,'Task','Call task','', 'Call {{full_name}} to reconnect and ask what has changed in their business.'),(10,'Email','Product reminder','A few ways I can help','Hi {{first_name}},\n\nI can help with conventional, government, HELOC, DPA, jumbo, and difficult-file reviews. I would appreciate another opportunity to earn your business.\n\nClay'),(21,'Email','Close loop','Here whenever you need me','Hi {{first_name}},\n\nI will close the loop for now, but I remain available whenever {{company}} needs another lending option.\n\nClay')])]
        for name,desc,steps in sequences:
            cur=c.execute("insert into sequences(name,description,status,created_at,updated_at) values(?,?,'Active',?,?)",(name,desc,NOW(),NOW()));sid=cur.lastrowid
            for i,(delay,ch,nm,sub,body) in enumerate(steps,1):
                c.execute("insert into sequence_steps(sequence_id,step_order,delay_days,channel,name,subject,body,create_task,stop_on_response,created_at,updated_at) values(?,?,?,?,?,?,?, ?,1,?,?)",(sid,i,delay,ch,nm,sub,body,1 if ch=='Task' else 0,NOW(),NOW()))

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

        create table if not exists message_templates(id integer primary key,name text,channel text,category text,subject text,body text,is_system integer default 1,created_at text,updated_at text);
        create table if not exists sequences(id integer primary key,name text,description text,status text default 'Active',created_at text,updated_at text);
        create table if not exists sequence_steps(id integer primary key,sequence_id integer,step_order integer,delay_days integer,channel text,name text,subject text,body text,create_task integer default 0,stop_on_response integer default 1,created_at text,updated_at text);
        create table if not exists sequence_enrollments(id integer primary key,sequence_id integer,prospect_id integer,contact_id integer,status text default 'Active',started_at text,stopped_at text,stop_reason text,created_at text);
        create table if not exists message_events(id integer primary key,recipient_id integer,event_type text,event_at text,detail text);
        create table if not exists inbound_messages(id integer primary key,provider_uid text unique,sender_email text,sender_name text,subject text,body text,received_at text,contact_id integer,prospect_id integer,classification text,sentiment text,status text default 'Needs Attention',suggested_subject text,suggested_reply text,sequences_stopped integer default 0,created_at text,updated_at text);

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
        for definition in ["sequence_id integer default 0", "auto_stop integer default 1"]:
            addcol(c, "campaigns", definition)
        for definition in ["opened_at text default ''", "clicked_at text default ''", "replied_at text default ''", "bounced_at text default ''", "unsubscribed_at text default ''", "sequence_enrollment_id integer default 0", "step_id integer default 0"]:
            addcol(c, "campaign_recipients", definition)
        seed_templates(c)
        seed_index(c)
        index_fha_pdf(c, Path(__file__).with_name('fha_handbook_4000_1.pdf'))
        run_migrations(c)
        # No fictional prospect records. Templates are editable system content.
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
print(f"BrokerBeacon startup: VERSION {BUILD_VERSION} · {BUILD_NAME}", flush=True)

@app.after_request
def add_build_headers(response):
    response.headers["X-BrokerBeacon-Version"] = BUILD_VERSION
    response.headers["X-BrokerBeacon-Build"] = BUILD_NAME
    if request.path == "/" or request.path.startswith("/api/guidelines") or request.path in {"/health", "/api/version"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/api/version")
def api_version():
    with db() as c:
        index_stats = guideline_index_stats(c)
    return jsonify(version=BUILD_VERSION, build=BUILD_NAME, guideline_index=index_stats)

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
        return jsonify(status="ok", prospects=prospect_count, version=BUILD_VERSION, build=BUILD_NAME)
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
    with db() as c:
        c.execute("update prospects set status=?,updated_at=? where id=?",(s,NOW(),pid))
        if s in ("Replied","Meeting","Approved"):
            c.execute("update sequence_enrollments set status='Stopped',stopped_at=?,stop_reason=? where prospect_id=? and status='Active'",(NOW(),"Prospect moved to "+s,pid))
            c.execute("update campaign_recipients set status='Suppressed',error=? where prospect_id=? and status='Queued' and sequence_enrollment_id>0",("Sequence stopped: "+s,pid))
    log("Status updated",f"Prospect {pid}: {s}"); return jsonify(ok=True)

@app.post("/api/generate")
def generate():
    blocked = reject_demo_write()
    if blocked: return blocked
    d=request.json or {}
    with db() as c:
        p=c.execute("select * from prospects where id=?",(d.get("id"),)).fetchone()
        contact=None
        if d.get("contact_id"):
            contact=c.execute("select * from contacts where id=? and prospect_id=?",(d.get("contact_id"),d.get("id"))).fetchone()
    if not p:return jsonify(error="Prospect not found"),404
    p=dict(p); contact=dict(contact) if contact else {}
    recipient_name=(contact.get("name") or p.get("owner") or "there").strip()
    first=recipient_name.split()[0] if recipient_name else "there"
    ch=d.get("channel","Email"); angle=d.get("angle","")
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
    detail=p["company"]+(" · "+recipient_name if contact else "")
    log("Outreach generated",detail); return jsonify(id=cur.lastrowid,subject=sub,body=body,contact_id=contact.get("id"),recipient=recipient_name)

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
    try:days=max(1,min(3650,int(request.args.get("days",90))))
    except ValueError:days=90
    with db() as c:return jsonify(executive_dashboard(c,days))

@app.post("/api/revenue-events")
def create_revenue_event():
    blocked=reject_demo_write()
    if blocked:return blocked
    try:
        with db() as c:result=log_revenue_event(c,request.json or {},NOW())
    except (ValueError,TypeError) as e:return jsonify(error=str(e)),400
    log("Revenue outcome recorded",str((request.json or {}).get("event_type") or ""))
    return jsonify(ok=True,**result)

@app.post("/api/revenue-settings")
def update_revenue_settings():
    blocked=reject_demo_write()
    if blocked:return blocked
    values=(request.json or {}).get("settings") or {}
    allowed={"average_loan_amount","revenue_bps","meeting_to_application_rate","application_to_funding_rate"}
    with db() as c:
        for key,value in values.items():
            if key not in allowed:continue
            try:value=float(value)
            except (TypeError,ValueError):continue
            if key.endswith("_rate"):value=max(0,min(1,value))
            else:value=max(0,value)
            c.execute("update revenue_settings set value=?,updated_at=? where key=?",(value,NOW(),key))
    return jsonify(ok=True)

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

@app.get('/api/sales-coach')
def sales_coach():
    """Explainable, deterministic coaching based only on stored BrokerBeacon data."""
    now=datetime.now()
    with db() as c:
        prospects=[dict(r) for r in c.execute("select * from prospects where status not in ('Funded') order by score desc")]
        last_actions={r['prospect_id']:dict(r) for r in c.execute("""
            select s.* from sales_actions s join (
                select prospect_id,max(id) max_id from sales_actions group by prospect_id
            ) x on x.max_id=s.id
        """)}
        action_counts={r['prospect_id']:r['n'] for r in c.execute("select prospect_id,count(*) n from sales_actions group by prospect_id")}
        contacts={}
        for r in c.execute("select * from contacts order by is_primary desc,is_decision_maker desc,id"):
            contacts.setdefault(r['prospect_id'],dict(r))
        reply_counts={r['prospect_id']:r['n'] for r in c.execute("select prospect_id,count(*) n from inbound_messages where prospect_id is not null group by prospect_id")} if c.execute("select 1 from sqlite_master where type='table' and name='inbound_messages'").fetchone() else {}
    items=[]
    for p in prospects:
        last=last_actions.get(p['id']); days_inactive=999
        if last and last.get('created_at'):
            try: days_inactive=max(0,(now-datetime.fromisoformat(last['created_at'])).days)
            except Exception: pass
        status=p.get('status') or 'New'
        if status in ('Replied','Meeting','Approved') and days_inactive<21: health='Healthy'
        elif days_inactive>=30 or (status=='Contacted' and days_inactive>=21): health='At Risk'
        else: health='Cooling'
        score=int(p.get('score') or 0); replies=int(reply_counts.get(p['id'],0)); actions=int(action_counts.get(p['id'],0))
        likelihood=35+round(score*.38)
        if replies: likelihood+=8
        if status in ('Replied','Meeting','Approved'): likelihood+=8
        if days_inactive>=30: likelihood-=6
        if actions>=3: likelihood+=4
        likelihood=max(20,min(92,likelihood))
        if health=='At Risk': action='Call today'
        elif score>=78: action='Call today'
        elif p.get('email'): action='Send personalized email'
        else: action='Research contact'
        product=(p.get('product_fit') or '').strip()
        why=[]
        if days_inactive==999: why.append('No completed sales activity is recorded')
        elif days_inactive>=30: why.append(f'{days_inactive} days since the last recorded activity')
        elif days_inactive>=14: why.append(f'{days_inactive} days since the last recorded activity')
        else: why.append(f'Recent activity {days_inactive} days ago')
        if score>=80: why.append(f'High opportunity score of {score}')
        if p.get('signal'): why.append(str(p['signal']))
        why_today='. '.join(why[:2])+'.'
        if product:
            opportunity=f"Lead with {product.split(',')[0].strip()}. {p.get('next_best_action') or 'Offer to review a live scenario and compare available options.'}"
        else:
            opportunity=p.get('next_best_action') or 'Use a discovery call to identify the account’s strongest product need.'
        opener=(p.get('call_opener') or '').strip()
        if not opener:
            first=(contacts.get(p['id'],{}).get('name') or p.get('owner') or 'there').split()[0]
            angle=product.split(',')[0].strip() if product else 'a current lending scenario'
            opener=f"Hi {first}, it’s Clay with Union Home Mortgage. I wanted to connect because I may be able to help {p['company']} with {angle}. Do you have two minutes?"
        evidence=[f"Opportunity score: {score}",f"Relationship: {health}"]
        if product: evidence.append(f"Product fit: {product.split(',')[0].strip()}")
        if replies: evidence.append(f"{replies} recorded repl{'y' if replies==1 else 'ies'}")
        if actions: evidence.append(f"{actions} recorded sales action{'s' if actions!=1 else ''}")
        contact=contacts.get(p['id'],{})
        priority=score+(20 if health=='At Risk' else 8 if health=='Cooling' else 0)+(5 if replies else 0)
        items.append(dict(prospect_id=p['id'],company=p['company'],opportunity_score=score,relationship_health=health,
            response_likelihood=likelihood,recommended_action=action,why_today=why_today,opportunity=opportunity,
            suggested_opening=opener,likely_objection=p.get('likely_objection') or '',objection_response=p.get('objection_response') or '',
            evidence=evidence,contact_name=contact.get('name') or p.get('owner') or '',phone=contact.get('phone') or contact.get('mobile') or p.get('phone') or '',
            email=contact.get('email') or p.get('email') or '',priority=priority))
    items.sort(key=lambda x:(-x['priority'],-x['response_likelihood'],x['company']))
    top=items[:15]
    return jsonify(items=top,summary={
        'call_today':sum(1 for x in top if x['recommended_action']=='Call today'),
        'at_risk':sum(1 for x in items if x['relationship_health']=='At Risk'),
        'high_response':sum(1 for x in top if x['response_likelihood']>=75),
        'product_matched':sum(1 for x in top if any(e.startswith('Product fit:') for e in x['evidence']))
    },methodology='Deterministic heuristic using stored score, relationship status, activity recency, replies, and product fit. It does not predict guaranteed outcomes.')

@app.get('/api/mission-control')
def mission_control():
    today=datetime.now().date(); week_start=today-timedelta(days=today.weekday())
    with db() as c:
        prospects=[dict(x) for x in c.execute("select * from prospects order by score desc")]
        last={r['prospect_id']:r['last_at'] for r in c.execute("select prospect_id,max(created_at) last_at from sales_actions group by prospect_id")}
        meetings=c.execute("select count(*) from sales_actions where (action_type='Meeting' or outcome='Meeting scheduled') and date(created_at)>=?",(week_start.isoformat(),)).fetchone()[0]
        actions_week=c.execute("select count(*) from sales_actions where date(created_at)>=?",(week_start.isoformat(),)).fetchone()[0]
        camps={r['status']:r['n'] for r in c.execute("select status,count(*) n from campaign_recipients group by status")}
        active=c.execute("select count(*) from campaigns where status='Active'").fetchone()[0]
        # Reply Inbox stores attention state in the status column. Older builds
        # incorrectly queried a non-existent needs_attention column, causing this
        # endpoint to return HTML 500 errors after Start My Day completed.
        if c.execute("select 1 from sqlite_master where type='table' and name='inbound_messages'").fetchone():
            inbound_columns={r[1] for r in c.execute("pragma table_info(inbound_messages)")}
            if 'status' in inbound_columns:
                replies_attention=c.execute(
                    "select count(*) from inbound_messages where coalesce(status,'Needs Attention')='Needs Attention'"
                ).fetchone()[0]
            elif 'needs_attention' in inbound_columns:
                replies_attention=c.execute(
                    "select count(*) from inbound_messages where coalesce(needs_attention,1)=1"
                ).fetchone()[0]
            else:
                replies_attention=0
        else:
            replies_attention=0
        settings={r['key']:float(r['value']) for r in c.execute("select key,value from revenue_settings")}
    ranked=[]; at_risk=[]; health={'Healthy':0,'Cooling':0,'At Risk':0}
    for p in prospects:
        days=999
        if last.get(p['id']):
            try: days=(datetime.now()-datetime.fromisoformat(last[p['id']])).days
            except Exception: pass
        if p['status'] in ('Replied','Meeting','Approved') and days<21: h='Healthy'
        elif days>=30 or (p['status']=='Contacted' and days>=21): h='At Risk'
        else: h='Cooling'
        health[h]+=1
        if h=='At Risk': at_risk.append({**p,'days_inactive':days,'health':h})
        urgency=min(days,20) if days!=999 else 20
        ranked.append({**p,'priority':int(p.get('score') or 0)+urgency,'reason':p.get('next_best_action') or 'Make the next relationship-building touch.','days_inactive':days,'health':h})
    ranked.sort(key=lambda x:-x['priority']); at_risk.sort(key=lambda x:-x['days_inactive'])
    alerts=[p for p in prospects if 'new' in (p.get('signal') or '').lower() or (p.get('created_at') or '')[:10]>=(today-timedelta(days=14)).isoformat()][:6]
    products=[]
    for name,terms in [('VA / FHA',['VA','FHA']),('DPA',['DPA']),('HELOC',['HELOC']),('Jumbo / niche',['Jumbo','niche']),('Low-FICO',['Lower-FICO'])]:
        products.append({'name':name,'count':sum(1 for p in prospects if any(t.lower() in (p.get('product_fit') or '').lower() for t in terms))})
    top=ranked[:5]
    avg_loan=settings.get('average_loan_amount',260000)
    projected_apps=max(1,round(len(top)*settings.get('meeting_to_application_rate',.35))) if top else 0
    projected_pipeline=projected_apps*avg_loan
    strongest=max(products,key=lambda x:x['count'])['name'] if products else 'scenario support'
    lead=top[0] if top else None
    brief=(f"Start with {lead['company']}. {lead['reason']} " if lead else "Start with the highest-ranked account. ") + f"There are {len(alerts)} new-account alerts, {len(at_risk)} relationships at risk, and {replies_attention} replies needing attention. The strongest product lane in the current database is {strongest}."
    recommendations=[]
    for x in top[:3]: recommendations.append({'title':f"{x['company']} · {x['health']}",'detail':x['reason']})
    return jsonify(metrics={'priority_calls':len(top),'new_alerts':len(alerts),'at_risk':len(at_risk),'meetings_week':meetings,'meeting_opportunities':min(4,max(0,len([x for x in top if x['score']>=75]))),'application_opportunities':projected_apps,'projected_pipeline_potential':projected_pipeline,'replies_attention':replies_attention},priorities=top,new_alerts=alerts,at_risk=at_risk[:6],products=products,health=health,recommendations=recommendations,goals={'completed':actions_week,'target':50,'percent':min(100,round(actions_week/50*100))},campaigns={'active':active,'queued':camps.get('Queued',0),'sent':camps.get('Sent',0),'failed':camps.get('Failed',0)},brief=brief)

@app.post('/api/start-my-day')
def start_my_day():
    blocked=reject_demo_write()
    if blocked:return blocked
    payload=request.get_json(silent=True) or {}; only_id=int(payload.get('prospect_id') or 0); today=datetime.now().date().isoformat()
    with db() as c:
        sql="select * from prospects where status not in ('Approved','Funded')"
        params=[]
        if only_id: sql+=" and id=?";params.append(only_id)
        sql+=" order by score desc limit ?";params.append(1 if only_id else 5)
        prospects=[dict(x) for x in c.execute(sql,params)]
        drafts=followups=0
        for p in prospects:
            contact=c.execute("select * from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,id limit 1",(p['id'],)).fetchone()
            contact=dict(contact) if contact else {'name':p.get('owner') or 'there','email':p.get('email') or '','phone':p.get('phone') or ''}
            name=(contact.get('name') or 'there').split()[0]
            channel='Email' if contact.get('email') else 'Phone'
            existing=c.execute("select id from outreach where prospect_id=? and date(created_at)=?",(p['id'],today)).fetchone()
            if not existing:
                subject=f"A lending resource for {p['company']}"
                body=f"Hi {name},\n\nI wanted to reach out because {p.get('next_best_action') or 'I believe we may be able to help with a current lending scenario.'}\n\nI would be glad to compare a live file or give you a quick overview of the options most relevant to {p['company']}.\n\nClay"
                c.execute("insert into outreach(prospect_id,channel,subject,body,status,created_at) values(?,?,?,?,?,?)",(p['id'],channel,subject,body,'Draft',NOW()));drafts+=1
            existing_fu=c.execute("select id from memories where prospect_id=? and note_type='Start My Day' and date(created_at)=?",(p['id'],today)).fetchone()
            if not existing_fu:
                c.execute("insert into memories(prospect_id,note_type,note,follow_up_date,created_at) values(?,?,?,?,?)",(p['id'],'Start My Day',p.get('next_best_action') or 'Complete the recommended outreach and record the result.',today,NOW()));followups+=1
        c.execute("insert into activity(action,detail,created_at) values(?,?,?)",('Start My Day prepared',f'{len(prospects)} priority accounts · {drafts} drafts · {followups} follow-ups',NOW()))
    return jsonify(ok=True,call_list=len(prospects),drafts_created=drafts,followups_created=followups)

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
    return jsonify({'query':query,'program':program,'program_label':labels[program],
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
