from flask import Flask, request, jsonify, render_template_string, Response, send_file, make_response
import sqlite3, io, csv, os, json, re, uuid
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
DB = Path(__file__).with_name("brokerbeacon.db")
NOW = lambda: datetime.now().isoformat(timespec="seconds")

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BrokerBeacon AI</title>
<style>
:root{--b:#060916;--p:#10182f;--p2:#0b1226;--l:#ffffff18;--t:#f7f8ff;--m:#9aa5c8;--v:#7c5cff;--c:#23d4fd;--g:#43dfa7;--y:#ffd166;--r:#ff6b8a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 12% 0,#5d3fff55,transparent 28%),radial-gradient(circle at 100% 15%,#23d4fd22,transparent 24%),var(--b);color:var(--t);font:14px Inter,Segoe UI,Arial,sans-serif}.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}aside{padding:24px 16px;border-right:1px solid var(--l);background:#080d1dee;position:sticky;top:0;height:100vh}.brand{font-size:20px;font-weight:850;margin-bottom:8px}.brand span{color:var(--c)}.version{font-size:10px;color:var(--m);margin-bottom:25px}nav button{display:block;width:100%;border:0;background:transparent;color:var(--m);text-align:left;padding:12px;border-radius:10px;margin:5px 0;cursor:pointer}nav button.active,nav button:hover{background:#7c5cff22;color:white}main{padding:28px;min-width:0}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--l);background:#ffffff0b;color:white;padding:10px 13px;border-radius:10px;cursor:pointer;text-decoration:none}.btn:hover{background:#ffffff16}.primary{background:linear-gradient(135deg,var(--v),#5a9cff);border:0}.danger{color:#ff9bb1}.view{display:none}.view.active{display:block}.hero,.panel,.metric{background:#111a34dd;border:1px solid var(--l);border-radius:17px;box-shadow:0 22px 60px #0005;backdrop-filter:blur(10px)}.hero{padding:24px;display:flex;justify-content:space-between;align-items:end;gap:20px}.hero p,.muted{color:var(--m);line-height:1.55}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.metric{padding:18px}.metric span{color:var(--m);font-size:12px}.metric strong{display:block;font-size:30px;margin-top:8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel{padding:19px}.filters{display:flex;gap:8px;margin-bottom:12px}input,select,textarea{background:#0c142a;color:white;border:1px solid var(--l);border-radius:9px;padding:10px;outline:0}.filters input{flex:1}table{width:100%;border-collapse:collapse}th,td{padding:13px;border-bottom:1px solid var(--l);text-align:left;vertical-align:middle}th{font-size:10px;color:var(--m);text-transform:uppercase}.pill{background:#23d4fd15;color:#8cecff;padding:5px 8px;border-radius:999px;font-size:10px;white-space:nowrap}.score{color:var(--g);font-weight:800}.board{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.col{min-height:420px;background:#ffffff06;border:1px solid var(--l);border-radius:13px;padding:10px}.card{background:var(--p);border:1px solid var(--l);border-radius:10px;padding:11px;margin:8px 0}.card small{color:var(--m)}label{display:block;color:var(--m);font-size:11px;margin:13px 0 6px}.full{width:100%}textarea{width:100%;min-height:220px;line-height:1.5}.subject{width:100%;margin:10px 0}.int{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.integration{text-align:center}.integration b{font-size:18px}.integration p{color:var(--m);min-height:45px}.activity div{padding:9px 0;border-bottom:1px solid var(--l)}dialog{background:#0d1428;color:white;border:1px solid var(--l);border-radius:15px;width:min(860px,94vw);max-height:90vh;overflow:auto}dialog::backdrop{background:#000b}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.formgrid input,.formgrid select,.formgrid textarea{width:100%}.toast{position:fixed;right:20px;bottom:20px;background:var(--p);padding:12px;border:1px solid var(--l);border-radius:10px;display:none;z-index:99}.priority{display:grid;gap:10px}.priority-card{display:grid;grid-template-columns:64px 1fr auto;gap:14px;align-items:center;padding:13px;border:1px solid var(--l);border-radius:13px;background:#ffffff06}.orb{width:56px;height:56px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--g) calc(var(--s)*1%),#ffffff12 0);font-weight:900}.orb:before{content:"";position:absolute}.reason{color:var(--m);font-size:12px;margin-top:4px}.tag{display:inline-block;padding:4px 7px;border-radius:999px;background:#ffffff0d;color:#c8d0ec;font-size:10px;margin:2px}.scoregrid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.scorebox{padding:13px;border:1px solid var(--l);border-radius:12px;background:#ffffff06}.scorebox strong{display:block;font-size:24px;margin-top:5px}.profile-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.tabs{display:flex;gap:6px;margin:14px 0}.tabs button{flex:1}.tabpane{display:none}.tabpane.active{display:block}.memory-item{padding:10px;border-left:3px solid var(--v);background:#ffffff05;margin:8px 0;border-radius:0 10px 10px 0}.smallbtn{padding:7px 9px;font-size:12px}.kicker{font-size:10px;letter-spacing:.12em;color:var(--c);font-weight:800}.nextaction{border-left:4px solid var(--g);padding:12px 14px;background:#43dfa710;border-radius:0 12px 12px 0}.explain li{margin:8px 0;color:#cfd5ed}.empty{padding:30px;text-align:center;color:var(--m)}.bars{display:grid;gap:12px}.barrow{display:grid;grid-template-columns:110px 1fr 42px;gap:10px;align-items:center}.bartrack{height:10px;background:#ffffff0b;border-radius:999px;overflow:hidden}.barfill{height:100%;background:linear-gradient(90deg,var(--v),var(--c));border-radius:999px}.exec{background:linear-gradient(135deg,#171f3e,#0e1733)}.top-account{display:grid;grid-template-columns:54px 1fr 120px 90px;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--l)}.rank{font-size:24px;color:var(--c);font-weight:900}.mini{font-size:11px;color:var(--m)}.state-map{display:grid;grid-template-columns:repeat(5,1fr);grid-template-areas:"mi . va . ." ". tn nc . ." ". . sc . ." ". . ga . .";gap:10px;min-height:300px;align-content:center}.state-tile{aspect-ratio:1.15;border:1px solid var(--l);border-radius:15px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:rgba(124,92,255,var(--heat));transition:.2s}.state-tile:hover{transform:translateY(-2px)}.state-tile b{font-size:24px}.state-tile span{color:var(--m);font-size:11px;margin-top:4px}.demo-lock{opacity:.55;cursor:not-allowed!important}.demo-banner{padding:10px 14px;border:1px solid #23d4fd44;background:#23d4fd10;border-radius:12px;margin-bottom:14px;color:#ccefff}.value-story{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.value-story>div{padding:14px;border:1px solid var(--l);border-radius:12px;background:#ffffff06}.value-story b{display:block;margin-bottom:5px}@media(max-width:700px){.state-map{grid-template-columns:repeat(3,1fr);grid-template-areas:"mi va va" "tn nc nc" "ga sc sc"}.value-story{grid-template-columns:1fr}}@media print{aside,.top .actions,nav,.btn{display:none!important}.app{display:block}.view{display:none!important}#boss{display:block!important}main{padding:0;background:white;color:#111}.hero,.panel,.metric{box-shadow:none;background:white;color:#111;border:1px solid #ddd}.muted,.mini{color:#555}.tag,.pill{border:1px solid #bbb;color:#222;background:#f5f5f5}}
@media(max-width:1050px){.board{grid-template-columns:repeat(2,1fr)}.scoregrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:900px){.app{grid-template-columns:1fr}aside{display:none}.metrics,.grid,.int{grid-template-columns:1fr 1fr}}@media(max-width:600px){main{padding:15px}.metrics,.grid,.board,.int,.formgrid,.scoregrid{grid-template-columns:1fr}.top,.hero,.profile-head{align-items:flex-start;flex-direction:column;gap:12px}.filters{flex-direction:column}.priority-card{grid-template-columns:56px 1fr}.priority-card>button{grid-column:1/-1}.actions{width:100%}.actions>*{flex:1;text-align:center}}
</style></head><body><div class="app"><aside><div class="brand">Broker<span>Beacon</span> AI</div><div class="version">VERSION 2.1 · SALES OPERATING SYSTEM</div><nav><button class="active" data-v="dashboard">✦ Command Center</button><button data-v="prospects">◉ Prospects</button><button data-v="outreach">✎ Outreach</button><button data-v="pipeline">▦ Pipeline</button><button data-v="followups">✓ Follow-ups</button><button data-v="territory">⌖ Territory</button><button data-v="boss">◆ Executive View</button><button data-v="integrations">⚙ Integrations</button></nav></aside><main><div class="top"><div><small>AI OPERATING SYSTEM FOR WHOLESALE AES</small><h1 id="title">Command Center</h1></div><div class="actions"><button class="btn" id="import">Compliant Import</button><a class="btn" href="/api/export">Export CSV</a><button class="btn primary" id="add">+ Add Prospect</button></div></div>
<section id="dashboard" class="view active"><div class="hero"><div><div class="kicker">DAILY BRIEFING</div><h2>Good morning, Clay. Your highest-value opportunities are ready.</h2><p>BrokerBeacon scores every prospect, explains the opportunity, recommends Union Home Mortgage products, and remembers relationship details.</p></div><button class="btn primary" onclick="show('prospects')">Review all prospects</button></div><div class="metrics"><div class="metric"><span>Total prospects</span><strong id="mt">0</strong></div><div class="metric"><span>Average opportunity score</span><strong id="ms">0</strong></div><div class="metric"><span>Queued outreach</span><strong id="mq">0</strong></div><div class="metric"><span>Meetings</span><strong id="mm">0</strong></div></div><div class="grid"><div class="panel"><h3>Today's priorities</h3><div id="priority" class="priority"></div></div><div class="panel"><h3>Pipeline snapshot</h3><div id="snapshot"></div><h3 style="margin-top:24px">Recent activity</h3><div id="activity" class="activity"></div></div></div></section>
<section id="prospects" class="view"><div class="filters"><input id="search" placeholder="Search company, owner, city"><select id="state"><option>All</option><option>NC</option><option>SC</option><option>VA</option><option>GA</option><option>TN</option><option>MI</option></select><select id="signal"><option>All</option><option>Newly Licensed</option><option>Team Growth</option><option>VA/FHA Fit</option><option>Imported</option><option>Manual</option><option>Verified Public Record</option><option>Needs Verification</option></select><select id="pstatus"><option>All statuses</option><option>New</option><option>Contacted</option><option>Replied</option><option>Meeting</option><option>Approved</option></select><select id="minscore"><option value="0">Any score</option><option value="70">70+</option><option value="80">80+</option><option value="90">90+</option></select></div><div class="panel" style="overflow:auto"><table><thead><tr><th>Company</th><th>Signal</th><th>Location</th><th>Fit</th><th>Score</th><th>Verification</th><th>Status</th><th></th></tr></thead><tbody id="rows"></tbody></table></div></section>
<section id="outreach" class="view"><div class="grid"><div class="panel"><h3>Personalized outreach builder</h3><label>Prospect</label><select id="op" class="full"></select><label>Channel</label><select id="channel" class="full"><option>Email</option><option>LinkedIn</option><option>Phone</option></select><label>Angle</label><select id="angle" class="full"><option>Recommended by intelligence engine</option><option>Congratulations + growth support</option><option>VA/FHA scenario support</option><option>Fast onboarding</option><option>HELOC and niche products</option></select><button class="btn primary full" id="gen" style="margin-top:15px">Generate personalized draft</button></div><div class="panel"><button class="btn primary" id="queue" disabled style="float:right">Approve & queue</button><h3>Review draft</h3><input id="subject" class="subject" placeholder="Subject"><textarea id="body"></textarea></div></div><div class="panel" style="margin-top:14px"><h3>Recent outreach</h3><div id="olist"></div></div></section>
<section id="pipeline" class="view"><div class="hero"><div><div class="kicker">PIPELINE CONTROL</div><h2>Move prospects from discovery to approved account.</h2><p>Every status change updates the executive view and preserves a consistent sales process.</p></div><span class="pill">5-stage workflow</span></div><div id="board" class="board" style="margin-top:14px"></div></section><section id="followups" class="view"><div class="hero"><div><div class="kicker">FOLLOW-UP CENTER</div><h2>Never lose the next action.</h2><p>Relationship notes with follow-up dates are organized by urgency so the most important conversations stay visible.</p></div><button class="btn primary" onclick="show('prospects')">Open prospects</button></div><div class="metrics"><div class="metric"><span>Overdue</span><strong id="fo">0</strong></div><div class="metric"><span>Due today</span><strong id="ft">0</strong></div><div class="metric"><span>Next 7 days</span><strong id="fw">0</strong></div><div class="metric"><span>Unscheduled notes</span><strong id="fu">0</strong></div></div><div class="panel"><div id="followList"></div></div></section>

<section id="territory" class="view"><div class="hero"><div><div class="kicker">TERRITORY INTELLIGENCE</div><h2>See where broker opportunity is concentrated.</h2><p>Coverage by state and metro helps account executives prioritize travel, identify white space, and balance prospecting effort.</p></div><span class="pill">Public-web prospect coverage</span></div><div class="metrics"><div class="metric"><span>States covered</span><strong id="ts">0</strong></div><div class="metric"><span>Core Carolinas prospects</span><strong id="tc">0</strong></div><div class="metric"><span>Top metro concentration</span><strong id="tm">—</strong></div><div class="metric"><span>High-priority territories</span><strong id="th">0</strong></div></div><div class="grid"><div class="panel"><h3>State coverage map</h3><p class="muted">Tile-map view of the current prospect footprint. Darker fill indicates more discovered companies.</p><div id="stateMap" class="state-map"></div></div><div class="panel"><h3>Metro opportunity</h3><div id="metros" class="bars"></div><h3 style="margin-top:24px">Coverage gaps</h3><div id="gaps" class="activity"></div></div></div></section>
<section id="boss" class="view"><div class="hero exec"><div><div class="kicker">EXECUTIVE DEMO VIEW</div><h2>Broker Development Intelligence</h2><p>A presentation-ready summary of prospecting activity, account quality, product alignment, territory coverage, and pipeline momentum.</p><div class="value-story"><div><b>Find faster</b><span class="muted">Consolidates compliant public-web prospect discovery.</span></div><div><b>Prioritize smarter</b><span class="muted">Scores fit, growth potential, and recommended product angles.</span></div><div><b>Act consistently</b><span class="muted">Turns intelligence into outreach and pipeline action.</span></div></div></div><button class="btn primary" onclick="window.print()">Print / Save PDF</button></div><div class="metrics"><div class="metric"><span>Active prospects</span><strong id="bt">0</strong></div><div class="metric"><span>High priority</span><strong id="bh">0</strong></div><div class="metric"><span>Meetings scheduled</span><strong id="bm">0</strong></div><div class="metric"><span>Weighted opportunity index</span><strong id="bi">0</strong></div></div><div class="grid"><div class="panel"><h3>Pipeline health</h3><div id="bossPipeline" class="bars"></div></div><div class="panel"><h3>Product opportunity mix</h3><div id="bossProducts" class="bars"></div></div></div><div class="panel" style="margin-top:14px"><div class="profile-head"><div><h3>Top strategic accounts</h3><p class="muted">Highest-scoring prospects currently requiring action.</p></div><span class="pill">Union Home Mortgage Demo</span></div><div id="bossTop"></div></div></section>
<section id="integrations" class="view"><div class="int"><div class="panel integration"><b>✉ Gmail</b><p>Future OAuth draft creation and reply tracking.</p><input type="checkbox" data-key="gmail_connected"></div><div class="panel integration"><b>H HubSpot</b><p>Future prospect and lifecycle synchronization.</p><input type="checkbox" data-key="hubspot_connected"></div><div class="panel integration"><b>N Licensing feed</b><p>Future authorized broker-data import adapter.</p><input type="checkbox" data-key="nmls_source_configured"></div></div><div class="panel" style="margin-top:14px;color:var(--m)"><b>Demo safety:</b> connection toggles store flags only. No passwords, tokens, or paid-data credentials are stored. Live research and integrations require approved data sources and credentials.</div></section>
</main></div><input type="file" id="file" accept=".csv" hidden>
<dialog id="dlg"><form id="form"><h3>Add Prospect</h3><div class="formgrid"><label>Company<input name="company" required></label><label>Owner<input name="owner"></label><label>City<input name="city"></label><label>State<input name="state" maxlength="2"></label><label>Signal<select name="signal"><option>Newly Licensed</option><option>Team Growth</option><option>VA/FHA Fit</option><option>Manual</option></select></label><label>Team size<input name="team" type="number"></label><label>Email<input name="email" type="email"></label><label>Phone<input name="phone"></label><label>Website<input name="website"></label><label>NMLS<input name="nmls"></label><label>Specialties<input name="specialties" placeholder="VA, FHA, DPA"></label><label>License type<input name="license_type" placeholder="Mortgage broker / lender-broker"></label><label>Source name<input name="source_name" placeholder="State regulator, company website, authorized vendor"></label><label>Source URL<input name="source_url" type="url"></label><label>Verification status<select name="verification_status"><option>Needs verification</option><option>Verified licensed company</option><option>Verified mortgage broker</option><option>Verified lender/broker combined</option></select></label><label>Verified date<input name="verified_at" type="date"></label><label>Verification notes<input name="verification_notes"></label><label>Hiring?<select name="hiring"><option value="0">No / Unknown</option><option value="1">Yes</option></select></label><label><input name="authorized_use" type="checkbox" value="1" required> I am authorized to store and use this record</label></div><button class="btn primary full" style="margin-top:14px">Save & score</button></form></dialog>
<dialog id="importDlg"><form id="importForm"><div class="profile-head"><div><div class="kicker">COMPLIANT DATA INGESTION</div><h3>Import regulator, CRM, or approved-vendor data</h3></div><button type="button" class="btn" onclick="document.querySelector('#importDlg').close()">Close</button></div><p class="muted">BrokerBeacon detects common column names, previews the file, validates supported states, and deduplicates by NMLS ID or company/location.</p><label>CSV file<input id="importFile" name="file" type="file" accept=".csv,text/csv" required class="full"></label><div class="formgrid"><label>Default source name<input id="defaultSource" placeholder="Example: SC DCA licensee export"></label><label>Default source URL<input id="defaultSourceUrl" type="url" placeholder="Official regulator or approved source"></label><label>Default verification status<select id="defaultVerify"><option>Needs verification</option><option>Verified licensed company</option><option>Verified mortgage broker</option><option>Verified lender/broker combined</option></select></label><label>Default license type<input id="defaultLicense" placeholder="Mortgage broker"></label></div><label style="padding:12px;border:1px solid var(--l);border-radius:10px;background:#ffffff06"><input id="importAuthorized" type="checkbox" required> I confirm this file was obtained lawfully and I am authorized to store and use it for this business purpose.</label><div class="actions" style="margin:14px 0"><button type="button" class="btn" id="previewImport">Preview & validate</button><button type="submit" class="btn primary">Import approved rows</button><a class="btn" href="/api/import/template">Download template</a></div><div id="importPreview" class="panel" style="display:none;max-height:320px;overflow:auto"></div></form></dialog>
<dialog id="profile"><div class="profile-head"><div><div class="kicker">BROKER INTELLIGENCE PROFILE</div><h2 id="pc"></h2><div id="ploc" class="muted"></div></div><button class="btn" onclick="$('#profile').close()">Close</button></div><div id="ptags" style="margin:12px 0"></div><div id="scores" class="scoregrid"></div><div class="tabs"><button class="btn primary" data-tab="intel">Intelligence</button><button class="btn" data-tab="strategy">Sales strategy</button><button class="btn" data-tab="memory">Relationship memory</button></div><div id="intel" class="tabpane active"><div class="grid"><div class="panel"><h3>AI-style summary</h3><p id="psum" class="muted"></p><h3>Why this score</h3><ul id="preasons" class="explain"></ul><h3>Source & verification</h3><div id="psource" class="muted"></div></div><div class="panel"><h3>Recommended product fit</h3><div id="pproducts"></div><h3>Next best action</h3><div id="pnext" class="nextaction"></div></div></div></div><div id="strategy" class="tabpane"><div class="grid"><div class="panel"><h3>Call opener</h3><textarea id="pcall" readonly></textarea></div><div class="panel"><h3>Likely objection & response</h3><p><b id="pobj"></b></p><p id="presp" class="muted"></p><button class="btn primary" id="profileOut">Build outreach</button></div></div></div><div id="memory" class="tabpane"><div class="panel"><h3>Add relationship memory</h3><div class="formgrid"><label>Type<select id="mtype"><option>Call note</option><option>Personal detail</option><option>Product interest</option><option>Follow-up</option></select></label><label>Follow-up date<input id="mdate" type="date"></label></div><textarea id="mnote" placeholder="Example: Interested in HELOCs; prefers text; reconnect after purchase season."></textarea><button class="btn primary" id="msave">Save memory</button><div id="mlist"></div></div></div></dialog><div class="toast" id="toast"></div>
<script>
let P=[],draft=null,current=null;const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
async function api(u,o={}){let r=await fetch(u,{headers:{'Content-Type':'application/json',...(o.headers||{})},...o});let d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
function esc(x){return String(x??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function msg(x){let t=$('#toast');t.textContent=x;t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
function show(v){$$('.view').forEach(x=>x.classList.toggle('active',x.id===v));$$('nav button').forEach(x=>x.classList.toggle('active',x.dataset.v===v));$('#title').textContent=v==='dashboard'?'Command Center':v[0].toUpperCase()+v.slice(1);if(v==='pipeline')pipe();if(v==='followups')followups();if(v==='outreach')outreach();if(v==='territory')territory();if(v==='boss')boss()}
$$('nav button').forEach(b=>b.onclick=()=>show(b.dataset.v));
async function load(){let q=new URLSearchParams({search:$('#search').value,state:$('#state').value,signal:$('#signal').value,status:$('#pstatus').value,min_score:$('#minscore').value});P=await api('/api/prospects?'+q);$('#rows').innerHTML=P.map(p=>`<tr><td><b>${esc(p.company)}</b><br><small>${esc(p.owner||'')}</small></td><td><span class="pill">${esc(p.signal)}</span></td><td>${esc(p.city||'')}, ${esc(p.state||'')}</td><td>${(p.product_fit||'').split(',').slice(0,2).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</td><td class="score">${p.score}</td><td><span class="pill">${esc(p.verification_status||'Needs verification')}</span></td><td>${esc(p.status)}</td><td><button class="btn smallbtn" onclick="profile(${p.id})">Intelligence</button></td></tr>`).join('');$('#op').innerHTML=P.map(p=>`<option value="${p.id}">${esc(p.company)}</option>`).join('')}
async function dash(){let d=await api('/api/dashboard');$('#mt').textContent=d.total;$('#ms').textContent=d.avg;$('#mq').textContent=d.queued;$('#mm').textContent=d.status.Meeting||0;$('#snapshot').innerHTML=['New','Contacted','Replied','Meeting','Approved'].map(x=>`<p>${x}<b style="float:right">${d.status[x]||0}</b></p>`).join('');$('#activity').innerHTML=d.activity.map(a=>`<div><b>${esc(a.action)}</b><br><small>${esc(a.detail||'')} · ${esc(a.created_at.replace('T',' '))}</small></div>`).join('')||'<div class=empty>No activity yet.</div>';$('#priority').innerHTML=d.priorities.map(p=>`<div class="priority-card"><div class="orb" style="--s:${p.score}">${p.score}</div><div><b>${esc(p.company)}</b><div class="reason">${esc(p.next_best_action)}</div><div>${(p.product_fit||'').split(',').slice(0,3).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</div></div><button class="btn smallbtn" onclick="profile(${p.id})">Open</button></div>`).join('')||'<div class=empty>Add or import prospects to begin.</div>'}
async function profile(id){let p=await api('/api/prospects/'+id);current=p;$('#pc').textContent=p.company;$('#ploc').textContent=[p.owner,p.city,p.state,p.nmls?'NMLS '+p.nmls:'',p.verification_status,p.verified_at?'Verified '+p.verified_at:''].filter(Boolean).join(' · ');$('#ptags').innerHTML=[p.signal,p.status,p.license_type,p.source_name,p.hiring?'Hiring':''].filter(Boolean).map(x=>`<span class=tag>${esc(x)}</span>`).join('');$('#scores').innerHTML=[['Opportunity',p.score],['Growth',p.growth_score],['Government fit',p.gov_fit],['HELOC/Jumbo',p.niche_fit]].map(x=>`<div class=scorebox><span class=muted>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');$('#psum').textContent=p.ai_summary;$('#preasons').innerHTML=p.score_reasons.map(x=>`<li>${esc(x)}</li>`).join('');$('#psource').innerHTML=[p.source_name?'<b>Source:</b> '+esc(p.source_name):'',p.source_url?'<a class="btn smallbtn" target="_blank" rel="noopener" href="'+esc(p.source_url)+'">Open source</a>':'',p.nmls?'<a class="btn smallbtn" target="_blank" rel="noopener" href="https://www.nmlsconsumeraccess.org/">Verify in NMLS Consumer Access</a>':'',p.verification_notes?'<div style="margin-top:8px">'+esc(p.verification_notes)+'</div>':''].filter(Boolean).join(' ');$('#pproducts').innerHTML=p.product_fit.split(',').filter(Boolean).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('');$('#pnext').textContent=p.next_best_action;$('#pcall').value=p.call_opener;$('#pobj').textContent=p.likely_objection;$('#presp').textContent=p.objection_response;$('#profileOut').onclick=()=>{show('outreach');$('#op').value=p.id;$('#profile').close()};renderMemory(p.memories);$('#profile').showModal()}
function renderMemory(m){$('#mlist').innerHTML='<h3 style="margin-top:22px">Saved memory</h3>'+((m||[]).map(x=>`<div class=memory-item><b>${esc(x.note_type)}</b><br>${esc(x.note)}<br><small class=muted>${esc(x.created_at.replace('T',' '))}${x.follow_up_date?' · Follow up '+esc(x.follow_up_date):''}</small></div>`).join('')||'<div class=empty>No relationship memory yet.</div>')}
$$('[data-tab]').forEach(b=>b.onclick=()=>{$$('[data-tab]').forEach(x=>x.classList.toggle('primary',x===b));$$('.tabpane').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab))});
$('#msave').onclick=async()=>{if(!$('#mnote').value.trim())return msg('Enter a note');let m=await api('/api/prospects/'+current.id+'/memory',{method:'POST',body:JSON.stringify({note_type:$('#mtype').value,note:$('#mnote').value,follow_up_date:$('#mdate').value})});$('#mnote').value='';$('#mdate').value='';renderMemory(m);msg('Memory saved');dash()}
async function pipe(){P=await api('/api/prospects');let S=['New','Contacted','Replied','Meeting','Approved'];$('#board').innerHTML=S.map(s=>`<div class=col><h3>${s}</h3>${P.filter(p=>p.status===s).map(p=>`<div class=card><b>${esc(p.company)}</b><p><small>${esc(p.owner||'')} · Score ${p.score}</small></p><select class=full ${document.body.dataset.demo==='1'?'disabled title="Read-only demo"':'onchange="status(${p.id},this.value)"'}>${S.map(x=>`<option ${x===p.status?'selected':''}>${x}</option>`).join('')}</select></div>`).join('')}</div>`).join('')}
async function status(id,s){await api('/api/status/'+id,{method:'POST',body:JSON.stringify({status:s})});msg('Pipeline updated');load();dash();pipe()}
$('#gen').onclick=async()=>{let d=await api('/api/generate',{method:'POST',body:JSON.stringify({id:+$('#op').value,channel:$('#channel').value,angle:$('#angle').value})});draft=d.id;$('#subject').value=d.subject;$('#subject').style.display=$('#channel').value==='Email'?'block':'none';$('#body').value=d.body;$('#queue').disabled=false;outreach()}
$('#queue').onclick=async()=>{await api('/api/queue/'+draft,{method:'POST',body:'{}'});msg('Queued');$('#queue').disabled=true;load();dash();outreach()}
async function outreach(){let d=await api('/api/outreach');$('#olist').innerHTML=d.length?d.map(x=>`<p><b>${esc(x.company)}</b> · ${esc(x.channel)} · ${esc(x.status)}</p>`).join(''):'No drafts yet.'}
$('#search').oninput=load;$('#state').onchange=load;$('#signal').onchange=load;$('#pstatus').onchange=load;$('#minscore').onchange=load;$('#add').onclick=()=>$('#dlg').showModal();$('#form').onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(e.target));await api('/api/prospects',{method:'POST',body:JSON.stringify(d)});$('#dlg').close();e.target.reset();msg('Prospect added and scored');load();dash()}
$('#import').onclick=()=>$('#importDlg').showModal();
async function previewImport(){let file=$('#importFile').files[0];if(!file){msg('Choose a CSV file first');return}let f=new FormData();f.append('file',file);let r=await fetch('/api/import/preview',{method:'POST',body:f}),d=await r.json();if(!r.ok){msg(d.error||'Preview failed');return}let box=$('#importPreview');box.style.display='block';box.innerHTML='<h4>Preview</h4><p class=muted>'+d.total_rows+' rows · '+d.valid_rows+' valid · '+d.invalid_rows+' need attention</p><p><b>Detected mapping:</b> '+Object.entries(d.mapping).filter(x=>x[1]).map(x=>x[0]+' ← '+x[1]).join(' · ')+'</p><table><thead><tr><th>Row</th><th>Company</th><th>State</th><th>NMLS</th><th>Result</th></tr></thead><tbody>'+d.sample.map(x=>'<tr><td>'+x.row+'</td><td>'+esc(x.company||'')+'</td><td>'+esc(x.state||'')+'</td><td>'+esc(x.nmls||'')+'</td><td>'+(x.errors.length?'<span style="color:var(--r)">'+esc(x.errors.join('; '))+'</span>':'<span style="color:var(--g)">Ready</span>')+'</td></tr>').join('')+'</tbody></table>'}
$('#previewImport').onclick=previewImport;
$('#importForm').onsubmit=async e=>{e.preventDefault();if(!$('#importAuthorized').checked){msg('Authorization confirmation is required');return}let file=$('#importFile').files[0];if(!file){msg('Choose a CSV file first');return}let f=new FormData();f.append('file',file);f.append('authorized_use','yes');f.append('default_source_name',$('#defaultSource').value);f.append('default_source_url',$('#defaultSourceUrl').value);f.append('default_verification_status',$('#defaultVerify').value);f.append('default_license_type',$('#defaultLicense').value);let r=await fetch('/api/import',{method:'POST',body:f}),d=await r.json();if(!r.ok){msg(d.error||'Import failed');return}msg(d.imported+' new · '+d.updated+' updated · '+d.skipped+' skipped');let box=$('#importPreview');box.style.display='block';box.innerHTML='<h4>Import complete</h4><p>'+d.imported+' new prospects, '+d.updated+' updated, '+d.skipped+' skipped.</p>'+(d.report_url?'<a class="btn" href="'+d.report_url+'">Download import report</a>':'');load();dash()};

async function followups(){let d=await api('/api/followups');$('#fo').textContent=d.counts.overdue;$('#ft').textContent=d.counts.today;$('#fw').textContent=d.counts.week;$('#fu').textContent=d.counts.unscheduled;$('#followList').innerHTML=d.items.length?d.items.map(x=>`<div class=priority-card><div class=orb style="--s:${x.score||50}">${x.score||'—'}</div><div><b>${esc(x.company)}</b><div class=reason>${esc(x.note_type)} · ${esc(x.note)}</div><small class=muted>${x.follow_up_date?esc(x.bucket)+' · '+esc(x.follow_up_date):'No date assigned'}</small></div><div><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Open</button> ${document.body.dataset.demo==='1'?'':`<button class="btn smallbtn" onclick="completeFollowup(${x.id})">Complete</button>`}</div></div>`).join(''):'<div class=empty>No follow-ups are currently scheduled.</div>'}async function completeFollowup(id){await api('/api/followups/'+id+'/complete',{method:'POST'});msg('Follow-up completed');followups();dash()}
async function territory(){let d=await api('/api/territory');$('#ts').textContent=d.states.length;$('#tc').textContent=d.carolinas;$('#tm').textContent=d.metros.length?d.metros[0].name:'—';$('#th').textContent=d.high_priority_states;let max=Math.max(1,...d.states.map(x=>x.count));$('#stateMap').innerHTML=d.states.map(x=>`<div class="state-tile" style="grid-area:${x.state.toLowerCase()};--heat:${Math.max(.12,x.count/max*.72)}"><b>${esc(x.state)}</b><strong>${x.count}</strong><span>prospects · avg ${x.avg_score}</span></div>`).join('');let mm=Math.max(1,...d.metros.map(x=>x.count));$('#metros').innerHTML=d.metros.map(x=>`<div class=barrow><span>${esc(x.name)}</span><div class=bartrack><div class=barfill style="width:${x.count/mm*100}%"></div></div><b>${x.count}</b></div>`).join('');$('#gaps').innerHTML=d.gaps.map(x=>`<div><b>${esc(x)}</b><br><small>Recommended next discovery market</small></div>`).join('')}

async function boss(){let d=await api('/api/executive');$('#bt').textContent=d.total;$('#bh').textContent=d.high_priority;$('#bm').textContent=d.meetings;$('#bi').textContent=d.opportunity_index;let max=Math.max(1,...Object.values(d.pipeline));$('#bossPipeline').innerHTML=Object.entries(d.pipeline).map(([k,v])=>`<div class=barrow><span>${esc(k)}</span><div class=bartrack><div class=barfill style="width:${v/max*100}%"></div></div><b>${v}</b></div>`).join('');$('#bossProducts').innerHTML=Object.entries(d.products).map(([k,v])=>`<div class=barrow><span>${esc(k)}</span><div class=bartrack><div class=barfill style="width:${v}%"></div></div><b>${v}%</b></div>`).join('');$('#bossTop').innerHTML=d.top.map((p,i)=>`<div class=top-account><div class=rank>#${i+1}</div><div><b>${esc(p.company)}</b><div class=mini>${esc(p.city||'')}, ${esc(p.state||'')} · ${esc(p.next_best_action||'')}</div></div><div>${(p.product_fit||'').split(',').slice(0,2).map(x=>`<span class=tag>${esc(x.trim())}</span>`).join('')}</div><div class=score>${p.score}/100</div></div>`).join('')||'<div class=empty>No prospects yet.</div>'}
async function ints(){let d=await api('/api/integrations');$$('[data-key]').forEach(x=>{x.checked=d[x.dataset.key];x.onchange=()=>api('/api/integrations',{method:'POST',body:JSON.stringify({key:x.dataset.key,value:x.checked})})})}
if(document.body.dataset.demo==='1'){
  const banner=document.createElement('div');banner.className='demo-banner';banner.innerHTML='<b>Executive demo mode</b> · Explore every workflow. Data-changing actions are disabled.';document.querySelector('main').insertBefore(banner,document.querySelector('.top').nextSibling);
  const badge=document.createElement('span');badge.className='pill';badge.textContent='FULL-FEATURE READ-ONLY DEMO';document.querySelector('.top small').after(badge);
  document.querySelectorAll('#import,#add,#queue,#gen,#msave,#form button[type="submit"],#importForm button[type="submit"],[data-key]').forEach(x=>{x.disabled=true;x.classList.add('demo-lock');x.title='Disabled in executive demo mode'});
  document.querySelectorAll('#subject,#body,#mnote,#mdate,#mtype').forEach(x=>{x.disabled=true;x.classList.add('demo-lock')});
  document.querySelectorAll('.actions a').forEach(x=>x.style.display='none');
  show('dashboard');
}
load();dash();outreach();followups();ints();
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
        return jsonify(status="ok", prospects=prospect_count, version="2.1")
    except Exception as exc:
        return jsonify(status="error", detail=str(exc)), 500

def reject_demo_write():
    if request.cookies.get("bb_demo") == "1":
        return jsonify(error="This executive demo is read-only."), 403
    return None

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
