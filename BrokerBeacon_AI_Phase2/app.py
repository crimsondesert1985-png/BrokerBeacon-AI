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
BUILD_VERSION = "27.2"
BUILD_NAME = "SITEWIDE GUIDED INTERACTIONS"
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
  background:linear-gradient(135deg,var(--green-2),var(--green)) !imۍ6Ӌh�鬶��q�^wܛWۛ؛�ݞ\J�[YJN���H
�[YH܈	ɊK�ݜ�\

K�ݙ\�
B�Y�	؛۝�[�[ۘ[	Ț[��܈	؛ۙ�ܛZ[�Ɉ[�����]\��	Л۝�[�[ۘ[	Y�	ٚIȚ[�����]\��	ђIY��K�٘\�ڊ�ʗ�ʝ�J	ʉˈ�N���]\��	ՐIY�	ݜ٘IȚ[��܈	ܝ\�[	Ț[�����]\��	ՔѐIY�	ڝ[X�Ɉ[�����]\��	ҝ[X�ɂ�Y�	ڙ[؉Ț[��܈	ڛۙH\]Z]IȚ[�����]\��	ґSЉY�	ۛۋ\[IȚ[��܈	ۛۈ[IȚ[�����]\��	ӛۋTSI�]\��
�[YH܈	ӝ\�ʋ�ݜ�\

K�]J
H܈	ӝ\���Y�ܜ�ٗۛܛWܝ\�ܙJ�[YJN���H
�[YH܈	ɊK�ݜ�\

K�ݙ\�
B�Y�	ܝ\�ژ\ىȚ[�����]\��	ԝ\�ژ\ىY�	ؘ\ډȚ[��[�	۝]	Ț[�����]\��	И\ڋSݝ�Y�[�[�ىY�	ܙY�IȚ[��܈	ܙY�[�[�ىȚ[�����]\��	Ԙ]Kՙ\�H�Y�[�[�ى�]\��
�[YH܈	ӝ\�ʋ�ݜ�\

K�]J
H܈	ӝ\���Y�ܜ�ٗݘ[YJ�݋
��[Y\ʎ���ܛX[^�YHܙK�ݘ��֗�K^�NWIˈ	ɋݜ�ʋ�ݙ\�
JN���܈ˈ�[��݋�][\ʊ_B��܈�[YH[��[Y\΂�ٞHH�K�ݘ��֗�K^�NWIˈ	ɋ�[YK�ݙ\�
JB�Y�ٞH[��ܛX[^�Y[�ݜ��ܛX[^�Yڙ^WJK�ݜ�\

N���]\��ݜ��ܛX[^�Yڙ^WJK�ݜ�\

B��]\��	ɂ���Y�ܜ�ٗ۝[J�[YK[�Yٜ�Q�[يN��^H�K�ݘ��֗�NK�WIˈ	ɋݜ��[YH܈	̉ʊB��N���[X�\�H�؝
^܈
B��]\��[�
�ݛ�
�[X�\�JHY�[�Yٜ�[و�[X�\��^ٜ�[YQ\��܎���]\��Y�[�Yٜ�[و����Y�ܜ�ٗ؜ڗܝ[[X\�Jۛ\[�Y\ˈݘ[ʎ��Y��݈ۛ\[�Y\΂��]\��	ڙXY[�IΈ	ӛȚ[\ܝY�ٝXݚ[ۈ]HY]	˂�	ܝ[[X\�IΈ	қ\ܝ[�\�ݙY�ٝXݚ[ۈԕ�Ȝ�[�Șۛ\[�Y\ˈ؛�ٙ�Xٜ�ˈ�ٝX݈Z^[�]ˈ[��۝[YK�˂�	ܙXۛ[Y[�][ۜɎ�ɕ\وH�ݚYY[\]H܈X\[�\�ݙY�ݚY\�^ܝȝHݜܝY�Y[ˉ׋�B�܈Hۛ\[�Y\֌B��XȏHو�XYڝݛ܋�ٝ
	ݛܗۛ؛�ݞ\Iʈ܈	ݚHۚ[�[��ٝX݈Z^	߈ڙ[�\�ؘښ[�Ȟݛܖɘۛ\[�IןK��B�Y�[�ۛ\[�Y\ʈ�N���X˘\[�
��ۛ\\�Hݛܖɘۛ\[�IןHڝ؛ۜ[�Y\֌WVɘۛ\[�IןH�Y�ܙH[��[�ȝ\��]ܞH�]�[܈ݝ�XXڋ��B��X˘\[�
	՜و˛]�[�[�ڛ�܈ۛHڙ[�H[\ܝY۝\�و[�۝Y\ț�[YY؛�ٙ�Xٜ�ț܈�SȚY[�Y�Y\�ˉʂ��]\��	ڙXY[�IΈ��ݛܖɘۛ\[�IןHXYȝH[\ܝY�ٝXݚ[ۈ�Y]ȋ�	ܝ[[X\�IΈ
���HٛXݙY\�[وۛ�Z[�Ȟݛݘ[։ݛ�]ɗN�H�[�Y[�]
ʈ[�	ݛݘ[։ݛ۝[YI׎���H����[��۝[YHXܛܜȞݛݘ[։؛ۜ[�Y\ɗ_Hۛ\[�ɚY\ɈY�ݘ[։؛ۜ[�Y\ɗHOHH[و	މߋ�����ݛܖɘۛ\[�IןH�\�\ٛ�ȝH\�ٜ݈[\ܝYܜܝ[�]H]	ݛܖɝ�۝[YI׎���K���
K�	ܙXۛ[Y[�][ۜɎ��X˂�B���\�ٝ
	˘\Kܜ�ٝXݚ[ۋݙ[\]Iʂ�Y��ٝXݚ[ۗݙ[\]J
N���]\��ٛ�ٚ[J�]
י�[W׊K�ڝۘ[YJ	ܜ�ٝXݚ[ۗڛ\ܝݙ[\]K�ܝ�ʋ�\ט]XڛY[�U�YK�ݛ�ؙۘ[YOI؜�ڙ\��XXۛ�ܜ�ٝXݚ[ۗڛ\ܝݙ[\]K�ܝ�˂�
B���\�ܝ
	˘\Kܜ�ٝXݚ[ۋڛ\ܝ	ʂ�Y��ٝXݚ[ۗڛ\ܝ

N���ؚٙH�Z�Xݗٙ[[םܚ]J
B�Y��ؚٙ���]\���ؚٙ�\ؙYH�\]Y\݋��[\˙ٝ
	ٚ[Iʂ�Y��݈\ؙY܈�݈\ؙY��[[�[YK�ݙ\�
K�[�ݚ]
	˘ܝ�ʎ���]\���ۛ�Y�J\��܏IКۜوHԕ��[K�ʋ��N���]ȏH\ؙY��XY

K�XۙJ	ݝ�N\ڙɊB�^ٜ[�XۙQXۙQ\��܎���]\���ۛ�Y�J\��܏I՚Hԕ�]\݈\وU�N[�ۙ[�ˉʋ��ݜȏH\݊ܝ��Xݔ�XY\�[˔ݜ�[�ғʜ�]ʊJB�Y��݈�ݜ΂��]\���ۛ�Y�J\��܏I՚Hԕ�ۛ�Z[�ț�ș]H�ݜˉʋ��\�ٙ\��ܜȏH׋ׂ��܈Y�݈[�[�[Y\�]J�ݜˈ�N��ۛ\[�HHܜ�ٗݘ[YJ�݋	؛ۜ[�Iˈ	؛ۜ[�H�[YIˈ	ۙ[�\��[YIˈ	؜�ڙ\�ۛ\[�Iˈ	ڛ�ݚ]][ۈ�[YIʂ�\�[وHܜ�ٗݘ[YJ�݋	ܙ\�[ٗۛ۝	ˈ	ܙ\�[و[۝	ˈ	ۛ۝	ˈ	ؘݚ]�]HYX\�[۝	ˈ	ܙ\ܝ[�ț[۝	ʂ�Y��K��[X]ڊ�י͟KW̟KW̟Iˈ\�[يN��\�[وH\�[ٖ΍ׂ�Y��K��[X]ڊ�י͟Iˈ\�[يN��\�[وH\�[ٖ΍H
ȉˉȊȜ\�[ٖ͎�B�Y��݈ۛ\[�H܈�݈�K��[X]ڊ�י͟KW̟Iˈ\�[يN��\��ܜ˘\[�
�ԛ݈ڙN�ۛ\[�H[�\�[ٗۛ۝
VVVKSSJH\�H�\]Z\�Y�ʂ�ۛ�[�YB�[�]ȏHܜ�ٗ۝[Jܜ�ٗݘ[YJ�݋	ݛ�]ɋ	ۛ؛�۝[�	ˈ	؛ݛ�	ˈ	ٝ[�Y[�]ɋ	ۜ�Yڛ�][ۜɊK�YJB��۝[YHHܜ�ٗ۝[Jܜ�ٗݘ[YJ�݋	ݛ۝[YIˈ	ۛ؛��۝[YIˈ	ٝ[�Y�۝[YIˈ	؛[ݛ�	ˈ	ۛ؛�[[ݛ�	ʊB�Y�[�]ȏH[��۝[YH���[�]ȏHB�Y�[�]ȏH[��۝[YHH��\��ܜ˘\[�
�ԛ݈ڙN�[�]ț܈�۝[YH\Ȝ�\]Z\�Y�ʂ�ۛ�[�YB�۝\�وHܜ�ٗݘ[YJ�݋	ܛݜ�ٗۘ[YIˈ	ܛݜ�ىˈ	ܜ�ݚY\�ˈ	٘]H۝\�ىʈ܈	Ԝ�ٝXݚ[ۈԕ�[\ܝ	]W؜כوHܜ�ٗݘ[YJ�݋	٘]W؜כىˈ	٘]H\țىˈ	؜țو]Iˈ	ٜ�\ڛ�\܈]Iʈ܈]][YK��݊
K�]J
K�\ۙ�ܛX]

B�\�ٙ�\[�
	؛ۜ[�IΈۛ\[�K�	؛ۜ[�Wۛ[Ɏ�ܜ�ٗݘ[YJ�݋	؛ۜ[�Wۛ[ɋ	؛ۜ[�H�[ɋ	ڛ�ݚ]][ۈ�[ɋ	ۙZIʋ�	ۛכ�[YIΈܜ�ٗݘ[YJ�݋	ۛכ�[YIˈ	ۛ؛�ٙ�Xٜ�ˈ	ۛ؛�ٙ�Xٜ��[YIˈ	ۜ�Yڛ�]܈�[YIʋ�	ۛכ�[Ɏ�ܜ�ٗݘ[YJ�݋	ۛכ�[ɋ	ۛț�[ɋ	ۛ؛�ܚYڛ�]܈�[ɋ	ۜ�Yڛ�]܈�[ɊK�	ܙ\�[ٗۛ۝	Έ\�[ً�	ۛ؛�ݞ\IΈܜ�ٗۛܛWۛ؛�ݞ\Jܜ�ٗݘ[YJ�݋	ۛ؛�ݞ\Iˈ	ۛ؛�\Iˈ	ܜ�ٝX݉ˈ	ܜ�ٜ�[IʊK�	ܝ\�ܙIΈܜ�ٗۛܛWܝ\�ܙJܜ�ٗݘ[YJ�݋	ܝ\�ܙIˈ	ۛ؛�\�ܙIˈ	ݜ�[�ؘݚ[ۈ\IʊK�	ݛ�]Ɏ�[�]˂�	ݛ۝[YIΈ�۝[YK�	ܛݜ�ٗۘ[YIΈ۝\�ً�	٘]W؜כىΈ]W؜כً�JB�Y��݈\�ٙ���]\���ۛ�Y�J\��܏Iӛȝ�[Y�ݜȝٜ�H�ݛ��ˈ]Z[ϙ\��ܜ֎�L�JK��۝\�ٗۘ[YHH\�ٙ̗Vɜ۝\�ٗۘ[YIׂ�]W؜כوHX^
][Və]W؜כى׈�܈][H[�\�ٙ
B�ڝ�
H\Șۛ����ۙڙȏHܖ̗H�܈�[�ۛ���^XݝJ�	ܙ[X݈Y��ۈ�ٝXݚ[ۗڛ\ܝȝڙ\�H۝\�ٗۘ[YOOȘ[�]W؜כُOɋ�
۝\�ٗۘ[YK]W؜כيK�
WB�Y�ۙڙ΂�X\�܈H	ˉ˚�ڛ�	ωȊ�[�ۙڙʊB�ۛ���^XݝJ�ٙ[]H��ۈ�ٝXݚ[ۗܙXۜ�ȝڙ\�H[\ܝڙ[�
ۘ\�ܟJIˈۙڙʂ�ۛ���^XݝJ�ٙ[]H��ۈ�ٝXݚ[ۗڛ\ܝȝڙ\�HY[�
ۘ\�ܟJIˈۙڙʂ�ݜ�Hۛ���^XݝJ�	ڛ�ٜ�[�Ȝ�ٝXݚ[ۗڛ\ܝʜ۝\�ٗۘ[YK۝\�ٗݞ\K]W؜כً�[Wۘ[YK�ݜך[\ܝYܙX]Y؝
H�[Y\ʏˏˏˏˏˏʉ˂�
۝\�ٗۘ[YK	ДՉˈ]W؜כً\ؙY��[[�[YK[�\�ٙ
K�Պ
JK�
B�[\ܝڙHݜ��\ݜ�ݚY��ܜXݗۘ\H�K�ݘ��֗�K^�NWIˈ	ɋ�ɘۛ\[�I׋�ݙ\�
JN��ɚY	ׂ��܈�[�ۛ���^XݝJ	ܙ[X݈Yۛ\[�H��ۈ�ܜXݜɊB�B��܈][H[�\�ٙ���ܜXݗڙH�ܜXݗۘ\�ٝ
�K�ݘ��֗�K^�NWIˈ	ɋ][Vɘۛ\[�I׋�ݙ\�
JJB�ۛ���^XݝJ�	ڛ�ٜ�[�Ȝ�ٝXݚ[ۗܙXۜ�ʚ[\ܝڙ�ܜXݗڙۛ\[�Kۛ\[�Wۛ[˛כ�[YKכ�[˜\�[ٗۛ۝؛�ݞ\K\�ܙK[�]˝�۝[YK۝\�ٗۘ[YK]W؜כًܙX]Y؝
H�[Y\ʏˏˏˏˏˏˏˏˏˏˏˏˏˏʉ˂�
�[\ܝڙ�ܜXݗڙ][Vɘۛ\[�I׋][Vɘۛ\[�Wۛ[ɗK][Vɛכ�[YI׋][Vɛכ�[ɗK�][Vɜ\�[ٗۛ۝	׋][Vɛ؛�ݞ\I׋][Vɜ\�ܙI׋][Vɝ[�]ɗK][Vɝ�۝[YI׋�][Vɜ۝\�ٗۘ[YI׋][Və]W؜כى׋�Պ
K�
K�
B��]\���ۛ�Y�J�ڏU�YK��ݜך[\ܝY[[�\�ٙ
K��ݜלښ\Y[[��ݜʈH[�\�ٙ
K�۝\�ٗۘ[YO\۝\�ٗۘ[YK�]W؜כُY]W؜כً�\��ܜϙ\��ܜ֎�L�K�
B���\�ٝ
	˘\Kܜ�ٝXݚ[ۋܝ[[X\�Iʂ�Y��ٝXݚ[ۗܝ[[X\�J
N���N��[۝ȏHX^
Z[��[�
�\]Y\݋�\�܋�ٝ
	ۛ۝ɋ	̌�ʊJJB�^ٜ�[YQ\��܎��[۝ȏHL��٘\�ڈH
�\]Y\݋�\�܋�ٝ
	ܙX\�ډʈ܈	ɊK�ݜ�\

K�ݙ\�
B�ݝٙ�Hܜ�ٗۛ۝؝]ٙ�[۝ʂ�ڙ\�K\�[\ȏH׋ׂ�Y�ݝٙ���ڙ\�K�\[�
	ܙ\�[ٗۛ۝�OɊB�\�[\˘\[�
ݝٙ�B�Y�٘\�ڎ��ڙ\�K�\[�
	ʛݙ\�ۛ\[�JHZوț܈ݙ\�כ�[YJHZوʉʂ�\�[\˙^[�
ىɞܙX\�ڟIIˈ�ɞܙX\�ڟII׊B�ۘ]\وH	ȝڙ\�H	ȊȉȘ[�	˚�ڛ�ڙ\�JHY�ڙ\�H[و	ɂ�ڝ�
H\Șۛ����ۛ\[�Y\ȏHٚX݊�H�܈�[�ۛ���^XݝJ��ܙ[X݈ۛ\[�KݛJ[�]ʈ[�]˜ݛJ�۝[YJH�۝[YKX^
]W؜כيH]W؜כًX^
۝\�ٗۘ[YJH۝\�ٗۘX�[��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟHܛݜ�Hۛ\[�Hܙ\��H�۝[YH\؉˂�\�[\˂�
WB�ݘ[ל�݈Hۛ���^XݝJ��ܙ[X݈۝[�
\ݚ[�݈ۛ\[�JKۘ[\ؙJݛJ[�]ʋ
Kۘ[\ؙJݛJ�۝[YJK
KX^
]W؜כيH��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟI˂�\�[\˂�
K��]ڛۙJ
B��܈ۛ\[�H[�ۛ\[�Y\΂�ݘ�ݚ\�HH\݊ڙ\�JH
Ȗɘۛ\[�OOɗB�ݘ�ܘ\�[\ȏH\݊\�[\ʈ
Ȗ؛ۜ[�Vɘۛ\[�IחB�ݘ�؛]\وH	ȝڙ\�H	ȊȉȘ[�	˚�ڛ�ݘ�ݚ\�JB�܈Hۛ���^XݝJ��ܙ[X݈؛�ݞ\KݛJ�۝[YJH���ۈ�ٝXݚ[ۗܙXۜ�ޜݘ�؛]\ٟHܛݜ�H؛�ݞ\Hܙ\��H�\؈[Z]I˂�ݘ�ܘ\�[\˂�
K��]ڛۙJ
B�ۛ\[�Vɘ]�\�Yٗۛ؛�׈Hۛ\[�Vɝ�۝[YI׈Șۛ\[�Vɝ[�]ɗHY�ۛ\[�Vɝ[�]ɗH[و�ۛ\[�Vɝܗۛ؛�ݞ\I׈Hܖ̗HY�܈[و	ӝ\�ۛ\[�Vɝܗۚ^ܘ݉׈H�ݛ�

ܖ̗HȘۛ\[�Vɝ�۝[YI׈
�L
HY�܈[�ۛ\[�Vɝ�۝[YI׈[و
B�ݘ[ȏH	؛ۜ[�Y\Ɏ�[�
ݘ[ל�ݖ̗H܈
K�	ݛ�]Ɏ�[�
ݘ[ל�ݖ̗H܈
K�	ݛ۝[YIΈ�؝
ݘ[ל�ݖ̗H܈
K�B�ݘ[։؝�\�Yٗۛ؛�׈Hݘ[։ݛ۝[YI׈ȝݘ[։ݛ�]ɗHY�ݘ[։ݛ�]ɗH[و�]\݈Hۛ���^XݝJ	ܙ[X݈۝\�ٗۘ[YK]W؜כًܙX]Y؝��ۈ�ٝXݚ[ۗڛ\ܝțܙ\��HY\؈[Z]Iʋ��]ڛۙJ
B���\ڛ�\܈H	ۘX�[	Έ��\țوۘ]\ݖə]W؜כىןH0�Ȟۘ]\ݖɜ۝\�ٗۘ[YIןH�Y�]\݈[و	ӛș]H[\ܝY	˂�	٘]W؜כىΈ]\ݖə]W؜כى׈Y�]\݈[و	ɋ�	ܛݜ�ىΈ]\ݖɜ۝\�ٗۘ[YI׈Y�]\݈[و	ɋ�B��]\���ۛ�Y�J�ݘ[ϝݘ[˂�ۛ\[�Y\Ϙۛ\[�Y\˂���\ڛ�\܏Y��\ڛ�\܋�\ڏWܜ�ٗ؜ڗܝ[[X\�Jۛ\[�Y\ˈݘ[ʋ�\�[ٗۛ۝ϛ[۝˂�
B���\�ٝ
	˘\Kܜ�ٝXݚ[ۋ؛ۜ[�Iʂ�Y��ٝXݚ[ۗ؛ۜ[�J
N��ۛ\[�HH
�\]Y\݋�\�܋�ٝ
	؛ۜ[�Iʈ܈	ɊK�ݜ�\

B�Y��݈ۛ\[�N���]\���ۛ�Y�J\��܏IЛۜ[�H�\]Z\�Y	ʋ��N��[۝ȏHX^
Z[��[�
�\]Y\݋�\�܋�ٝ
	ۛ۝ɋ	̌�ʊJJB�^ٜ�[YQ\��܎��[۝ȏHL��ݝٙ�Hܜ�ٗۛ۝؝]ٙ�[۝ʂ�ڙ\�K\�[\ȏHɘۛ\[�OOɗK؛ۜ[�WB�Y�ݝٙ���ڙ\�K�\[�
	ܙ\�[ٗۛ۝�OɊB�\�[\˘\[�
ݝٙ�B�ۘ]\وH	ȝڙ\�H	ȊȉȘ[�	˚�ڛ�ڙ\�JB�ڝ�
H\Șۛ����ݘ[Hۛ���^XݝJ��ܙ[X݈ۘ[\ؙJݛJ[�]ʋ
Kۘ[\ؙJݛJ�۝[YJK
KX^
]W؜כيKX^
۝\�ٗۘ[YJH��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟI˂�\�[\˂�
K��]ڛۙJ
B�؛�ݞ\\ȏHٚX݊�H�܈�[�ۛ���^XݝJ��ܙ[X݈؛�ݞ\KݛJ[�]ʈ[�]˜ݛJ�۝[YJH�۝[YH��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟHܛݜ�H؛�ݞ\Hܙ\��H�۝[YH\؉˂�\�[\˂�
WB�[۝HHٚX݊�H�܈�[�ۛ���^XݝJ��ܙ[X݈\�[ٗۛ۝[۝ݛJ[�]ʈ[�]˜ݛJ�۝[YJH�۝[YH��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟHܛݜ�H\�[ٗۛ۝ܙ\��H\�[ٗۛ۝	˂�\�[\˂�
WB�؛�ۙ��Xٜ�ȏHٚX݊�H�܈�[�ۛ���^XݝJ���ٛX݈כ�[YKכ�[˜ݛJ[�]ʈ[�]˜ݛJ�۝[YJH�۝[YH��ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟH[��[Jכ�[YJO�Ɉܛݜ�Hכ�[YKכ�[țܙ\��H�۝[YH\؈��\�[\˂�
WB��܈Ț[�؛�ۙ��Xٜ�΂�܈Hۛ���^XݝJ���ٛX݈؛�ݞ\KݛJ�۝[YJH���ۈ�ٝXݚ[ۗܙXۜ�ޘۘ]\ٟH[�כ�[YOOȘ[�ۘ[\ؙJכ�[ˉɊOOșܛݜ�H؛�ݞ\Hܙ\��H�\؈[Z]H��\�[\ȊȖۛ։ۛכ�[YI׋։ۛכ�[ɗH܈	ɗK�
K��]ڛۙJ
B�։ݛܗۛ؛�ݞ\I׈Hܖ̗HY�܈[و	ӝ\�ݘ[ȏHɝ[�]Ɏ�[�
ݘ[̗H܈
K	ݛ۝[YIΈ�؝
ݘ[̗H܈
_B�ݘ[։؝�\�Yٗۛ؛�׈Hݘ[։ݛ۝[YI׈ȝݘ[։ݛ�]ɗHY�ݘ[։ݛ�]ɗH[و�܈H؛�ݞ\\֌HY�؛�ݞ\\ș[وɛ؛�ݞ\IΈ	ӝ\�ˈ	ݛ�]Ɏ�	ݛ۝[YIΈB�ژ\�HH
ܖɝ�۝[YI׈ȝݘ[։ݛ۝[YI׈
�L
HY�ݘ[։ݛ۝[YI׈[و�\ڈH	ڙXY[�IΈ��ݛܖɛ؛�ݞ\IןH\ȝHXY[�Ț[\ܝY�ٝX݈�܈؛ۜ[�_H��	ܝ[[X\�IΈ
���؛ۜ[�_HڛݜȞݛݘ[։ݛ�]ɗN�H[�]
ʈ[�	ݛݘ[։ݛ۝[YI׎���H[�[\ܝY�ٝXݚ[ۋ�����ݛܖɛ؛�ݞ\IןH�\�\ٛ�Ș\�ޚ[X][Hܚ\�N���IHو�۝[YH[�\ȝ�Y]ˈ��
K�	ܙXۛ[Y[�][ۜɎ���XYڝHݛܖɛ؛�ݞ\IןK\ܙXڙ�Xȝ�[YH�ܛܚ][ۋ���
���[ܚ]^�Hۛ؛�ۙ��Xٜ�֌Vɛכ�[YIןH\ȝHYڙ\݋]�۝[YH�[YYȚ[�\Ȝ۝\�ً��Y�؛�ۙ��Xٜ�ș[و	қ\ܝ[�\�ݙY˛]�[۝\�وȚY[�Y�H[�]�YX[�ٝXٜ�\�ٝˉʋ�	Лۜ\�H[\ܝYݘ[�ٝXݚ[ۈڝ[�\��[RH�[�[�܈�Y�ܙH\ݚ[X][�ȝ؛]ژ\�K�˂�K�B��]\���ۛ�Y�J�ۛ\[�OXۛ\[�K�ݘ[ϝݘ[˂�؛�ݞ\\ϛ؛�ݞ\\˂�[۝O[[۝K�؛�ۙ��Xٜ�ϛ؛�ۙ��Xٜ�˂�۝\�ٗۘX�[]ݘ[̗H܈	қ\ܝY]I˂�]W؜כُ]ݘ[̗H܈	ɋ�\�[ٗۘX�[IЛ[\ܝY]IȚY��݈[۝ș[و�՜�Z[[�Ȟۛ۝߈[۝ɋ�\ڏX\ڋ�
B���\�ٝ
�؜Kڛ�Yܘ][ۜȊB�Y�ڊ
N��ڝ�
H\ȘΙ^ܖ̗N��̗H�܈�[�˙^XݝJ�ٛX݈ٞK�[YH��ۈ[�Yܘ][ۜȊ_B��]\���ۛ�Y�Jڎ��ٝ
ʏOH��YH��܈Ț[�șۘZ[؛ۛ�XݙY��X�ܛݗ؛ۛ�XݙY���[ל۝\�ٗ؛ۙ�Yݜ�Y�_JB��\�ܝ
�؜Kڛ�Yܘ][ۜȊB�Y�ڊ
N���ؚٙH�Z�Xݗٙ[[םܚ]J
B�Y��ؚٙ��]\���ؚٙ�\�\]Y\݋��ۛ�܈߂�ڝ�
H\ȘΘ˙^XݝJ�[�ٜ�܈�\Xو[�Ț[�Yܘ][ۜʚٞK�[YJH�[Y\ʏˏʈ�
�ٝ
�ٞH�Kݜ��ۛ
�ٝ
��[YH�JJK�ݙ\�
JJB��]\���ۛ�Y�JڏU�YJB��Y�ܘ۝]؝]ܚ[ݗݛܚٜ�
N�����ؚو\�[ٚX؛Hښ[HH�[�\�ٜ��Xو\Ȝ�[��[�Έ]X�\و[Z[�Ș[��YٝȜ�[XZ[�]]ܚ]]]�K������XY[�ˑ]�[�

K�ؚ]
�
B�ښ[H�YN���N�ܝ[�ܘ۝]؝]ܚ[݊�ܘُQ�[يB�^ٜ^ٜ[ۈ\ș^Μ�[�
�Ԙ۝]]]ܚ[݈ۜ�ٜ��ݞ\J^ʋ�כ�[YWןN�ܝ�^ʖΌM�_I˙�\ڏU�YJB��XY[�ˑ]�[�

K�ؚ]
L
B��Y�܋�ٝ[��	ѓ�P�WԐӕUЕUԒS՗ՓԒє�ˉ̉ʏOỈ΂��XY[�˕�XY
\�ٝWܘ۝]؝]ܚ[ݗݛܚٜ��[YOI؜�ڙ\��XXۛ�\؛ݝX]]ܚ[݉˙Y[[ۏU�YJK�ݘ\�

B��Y�כ�[YW׏OH�כXZ[�׈���[�]

B�\��[�ܝ[܋�ٝ[���ԕ��L�ˌ��H�KܝZ[�
܋�ٝ[���ԕ��L�JKX�Yϑ�[ي��