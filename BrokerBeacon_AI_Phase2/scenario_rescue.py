"""BeaconMatch scenario rescue engine.

Extracts facts from unstructured mortgage scenarios, identifies missing data,
ranks possible paths, drafts broker responses, and records outcomes. It is a
human-review aid only and never represents approval or final eligibility.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from html import escape

from flask import g, jsonify, request

OUTCOMES = {"new", "reviewed", "submitted", "approved", "denied", "withdrawn", "funded"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _money(value: str | None):
    if not value:
        return None
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return None


def extract_facts(text: str) -> dict:
    raw = " ".join((text or "").split())
    low = raw.lower()
    facts = {}
    patterns = {
        "fico": r"(?:fico|credit(?: score)?)\s*(?:of|is|:)?\s*(\d{3})",
        "purchase_price": r"(?:purchase(?: price)?|sales price|price)\s*(?:of|is|:)?\s*\$?([\d,]+)",
        "loan_amount": r"(?:loan(?: amount)?|mortgage)\s*(?:of|is|:)?\s*\$?([\d,]+)",
        "down_payment_percent": r"(\d+(?:\.\d+)?)\s*%\s*(?:down|down payment)",
        "dti": r"(?:dti|debt[- ]to[- ]income)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*%?",
        "reserves_months": r"(\d+)\s*(?:months?|mos?)\s*(?:of\s*)?reserves?",
        "employment_years": r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s*(?:self[- ]employed|in business|employment)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, low, re.I)
        if match:
            facts[key] = float(match.group(1)) if "." in match.group(1) else int(match.group(1).replace(",", ""))
    state = re.search(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b", raw)
    if state:
        facts["state"] = state.group(1)
    facts["transaction"] = "refinance" if re.search(r"\b(refi|refinance|cash[- ]out)\b", low) else "purchase" if "purchase" in low else None
    if "self-employed" in low or "self employed" in low or "business owner" in low:
        facts["income_type"] = "self_employed"
    elif any(x in low for x in ["w2", "w-2", "salary", "salaried"]):
        facts["income_type"] = "w2"
    if "primary" in low or "owner occupied" in low:
        facts["occupancy"] = "primary"
    elif "investment" in low or "rental" in low:
        facts["occupancy"] = "investment"
    elif "second home" in low:
        facts["occupancy"] = "second_home"
    if "va" in low or "veteran" in low:
        facts["va_indicator"] = True
    if "first time" in low or "first-time" in low:
        facts["first_time_buyer"] = True
    if "late" in low:
        facts["recent_late"] = True
    if "bankruptcy" in low or "chapter 7" in low or "chapter 13" in low:
        facts["bankruptcy"] = True
    if "foreclosure" in low:
        facts["foreclosure"] = True
    return {k: v for k, v in facts.items() if v is not None}


def missing_information(facts: dict) -> list[str]:
    required = {
        "fico": "Credit score or representative FICO",
        "transaction": "Purchase or refinance transaction type",
        "state": "Property state",
        "occupancy": "Primary, second-home, or investment occupancy",
        "income_type": "Income type and employment history",
    }
    missing = [label for key, label in required.items() if not facts.get(key)]
    if not facts.get("purchase_price") and not facts.get("loan_amount"):
        missing.append("Purchase price or requested loan amount")
    missing.extend([
        "AUS findings or manual-underwrite status",
        "Housing-payment history and dates of any late payments",
        "Verified monthly income, debts, assets, and reserves",
        "Property type and number of units",
    ])
    return missing[:8]


def rank_paths(facts: dict) -> list[dict]:
    fico = int(facts.get("fico") or 0)
    down = float(facts.get("down_payment_percent") or 0)
    paths = []
    def add(name, score, reason, cautions):
        paths.append({"name": name, "confidence": max(15, min(score, 92)), "reason": reason, "cautions": cautions})
    if fico and fico < 620:
        add("FHA or government-insured review", 68, "The credit profile may fit a government-insured review better than standard conventional paths.", ["AUS or manual-underwrite rules", "Recent housing history", "Lender overlays"])
    else:
        add("Conventional conforming review", 70 if fico >= 680 else 55, "The available credit information may support a conforming review once income, assets, and AUS findings are verified.", ["AUS findings", "Debt-to-income ratio", "Mortgage insurance and reserves"])
    if facts.get("va_indicator"):
        add("VA eligibility review", 82, "The scenario indicates possible veteran eligibility, which can materially change structure and required cash.", ["Certificate of Eligibility", "Residual income", "VA-specific property and occupancy rules"])
    if facts.get("income_type") == "self_employed":
        add("Self-employed documentation path", 62, "The borrower appears self-employed, so tax-return, cash-flow, and business-history analysis will drive the result.", ["Length of self-employment", "Tax-return analysis", "Business liquidity and declining income"])
    if facts.get("first_time_buyer") or (down and down <= 5):
        add("Low-down-payment or assistance review", 58, "Low cash-to-close or first-time-buyer indicators justify reviewing eligible assistance and low-down-payment options.", ["Program geography", "Income limits", "Homebuyer education", "Second-lien terms"])
    if facts.get("bankruptcy") or facts.get("foreclosure"):
        add("Seasoning and exception review", 38, "A major derogatory event may control eligibility and requires exact dates and program-specific seasoning review.", ["Discharge or completion date", "Extenuating-circumstance documentation", "Program and investor seasoning"])
    if facts.get("recent_late"):
        for path in paths:
            path["confidence"] = max(15, path["confidence"] - 12)
            path["cautions"].append("Exact date and severity of recent late payment")
    return sorted(paths, key=lambda item: item["confidence"], reverse=True)[:5]


def build_analysis(text: str) -> dict:
    facts = extract_facts(text)
    paths = rank_paths(facts)
    missing = missing_information(facts)
    top = paths[0] if paths else {"name": "Human guideline review", "confidence": 30}
    questions = [f"Please confirm: {item}." for item in missing[:5]]
    email = (
        f"This scenario may have a path through {top['name']}, but I need to verify several details before giving direction. "
        + " ".join(questions[:3])
        + " Once those items and the AUS findings are available, I can help structure the next submission."
    )
    text_reply = f"This may have a path through {top['name']}. Please send the AUS findings plus the missing items listed in BrokerBeacon so I can help structure it."
    call = f"I see a possible {top['name']} path. I would first confirm the missing facts, then review AUS findings and any lender overlays before recommending structure."
    return {
        "facts": facts,
        "missing": missing,
        "paths": paths,
        "responses": {"email": email, "text": text_reply, "call": call},
        "disclaimer": "Potential paths only. Final eligibility, pricing, approval, and underwriting decisions require current agency, investor, lender, and program guideline verification by a qualified human reviewer.",
    }


def install_scenario_rescue(app, db_path):
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.execute("""create table if not exists scenario_rescue_cases(
            id integer primary key,
            workspace_id integer not null default 0,
            user_id integer not null default 0,
            title text not null,
            scenario_text text not null,
            analysis_json text not null,
            outcome text not null default 'new',
            outcome_note text default '',
            created_at text not null,
            updated_at text not null
        )""")
        conn.execute("create index if not exists idx_scenario_rescue_workspace on scenario_rescue_cases(workspace_id,id desc)")

    @app.post("/api/scenario-rescue/analyze")
    def scenario_rescue_analyze():
        data = request.get_json(silent=True) or {}
        text = (data.get("scenario") or "").strip()
        if len(text) < 20:
            return jsonify(error="Enter a fuller loan scenario before analysis"), 400
        analysis = build_analysis(text)
        return jsonify(analysis)

    @app.post("/api/scenario-rescue/cases")
    def scenario_rescue_save():
        data = request.get_json(silent=True) or {}
        text = (data.get("scenario") or "").strip()
        title = (data.get("title") or "Untitled scenario").strip()[:160]
        if len(text) < 20:
            return jsonify(error="Scenario is required"), 400
        analysis = build_analysis(text)
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        user_id = int(getattr(g, "user_id", 0) or 0)
        now = _now()
        with connect() as conn:
            cur = conn.execute("""insert into scenario_rescue_cases
                (workspace_id,user_id,title,scenario_text,analysis_json,outcome,created_at,updated_at)
                values(?,?,?,?,?,'new',?,?)""", (workspace_id,user_id,title,text,json.dumps(analysis),now,now))
            case_id = cur.lastrowid
        return jsonify(ok=True, id=case_id, analysis=analysis), 201

    @app.get("/api/scenario-rescue/cases")
    def scenario_rescue_list():
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        with connect() as conn:
            rows = conn.execute("""select id,title,outcome,outcome_note,created_at,updated_at
                from scenario_rescue_cases where workspace_id=? order by id desc limit 100""", (workspace_id,)).fetchall()
        return jsonify(items=[dict(row) for row in rows])

    @app.post("/api/scenario-rescue/cases/<int:case_id>/outcome")
    def scenario_rescue_outcome(case_id):
        data = request.get_json(silent=True) or {}
        outcome = (data.get("outcome") or "").lower()
        note = (data.get("note") or "").strip()[:1000]
        if outcome not in OUTCOMES:
            return jsonify(error="Invalid outcome"), 400
        workspace_id = int(getattr(g, "workspace_id", 0) or 0)
        with connect() as conn:
            cur = conn.execute("""update scenario_rescue_cases set outcome=?,outcome_note=?,updated_at=?
                where id=? and workspace_id=?""", (outcome,note,_now(),case_id,workspace_id))
        if not cur.rowcount:
            return jsonify(error="Scenario not found"), 404
        return jsonify(ok=True, outcome=outcome)

    @app.get("/intelligence/scenario-rescue")
    def scenario_rescue_page():
        return SCENARIO_HTML

    return app


SCENARIO_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BeaconMatch Scenario Rescue</title><style>
body{margin:0;background:#07111f;color:#eef5ff;font:14px system-ui}.wrap{max-width:1180px;margin:auto;padding:24px}.hero{padding:24px;border:1px solid #ffffff20;border-radius:20px;background:linear-gradient(135deg,#10284d,#16213a)}h1{margin:5px 0 8px;font-size:32px}.muted{color:#aebdd1}.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;margin-top:18px}.card{background:#0d1a2d;border:1px solid #ffffff18;border-radius:16px;padding:17px}textarea,input{width:100%;box-sizing:border-box;background:#07111f;color:white;border:1px solid #ffffff25;border-radius:10px;padding:11px}textarea{min-height:210px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:10px}button{border:0;border-radius:10px;padding:10px 14px;cursor:pointer;font-weight:800}.primary{background:#6d7cff;color:white}.secondary{background:#ffffff12;color:white}.path{padding:12px;border:1px solid #ffffff18;border-radius:12px;margin:9px 0}.bar{height:6px;background:#ffffff14;border-radius:9px;overflow:hidden}.bar span{display:block;height:100%;background:#75dfbd}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#75dfbd20;color:#91f1cf;font-size:11px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}.copy{white-space:pre-wrap;background:#07111f;padding:10px;border-radius:10px;color:#c8d5e6}.warn{border-left:3px solid #f2c66d;padding-left:10px;color:#e8d7a8}.footer{text-align:center;color:#718099;padding:26px}@media(max-width:800px){.grid,.cols{grid-template-columns:1fr}}
</style></head><body><div class="wrap"><div class="hero"><div class="pill">BEACONMATCH</div><h1>Scenario Rescue Engine</h1><div class="muted">Paste the loan you cannot place. BrokerBeacon extracts the facts, shows what is missing, ranks possible paths, and drafts the next response.</div></div><div class="grid"><div><div class="card"><h2>Describe the scenario</h2><input id="title" placeholder="Scenario title"><textarea id="scenario" placeholder="Example: 612 FICO, self-employed for 3 years, recent mortgage late, $325,000 purchase, 5% down, primary residence in NC..."></textarea><div class="actions"><button id="analyze" class="primary">Analyze scenario</button><button id="save" class="secondary">Save case</button></div></div><div id="results" class="card" style="margin-top:18px;display:none"></div></div><div><div class="card"><h2>Saved cases</h2><div id="cases" class="muted">No cases loaded.</div></div><div class="card" style="margin-top:18px"><h2>Human review required</h2><div class="warn">BeaconMatch surfaces potential paths. It does not issue approvals, replace AUS, interpret every lender overlay, or guarantee eligibility.</div></div></div></div><div class="footer">For Aiden — built with persistence.</div></div><script>
let last=null;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(a){last=a;const facts=Object.entries(a.facts).map(([k,v])=>`<span class="pill">${esc(k.replaceAll('_',' '))}: ${esc(v)}</span>`).join(' ');const paths=a.paths.map(p=>`<div class="path"><b>${esc(p.name)}</b> · ${p.confidence}%<div class="bar"><span style="width:${p.confidence}%"></span></div><p>${esc(p.reason)}</p><small>${esc(p.cautions.join(' · '))}</small></div>`).join('');document.getElementById('results').innerHTML=`<h2>Extracted facts</h2>${facts||'<div class="muted">No reliable facts extracted yet.</div>'}<h2>Potential paths</h2>${paths}<div class="cols"><div><h3>Missing information</h3><ul>${a.missing.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div><h3>Broker-ready response</h3><div class="copy">${esc(a.responses.email)}</div></div></div><p class="warn">${esc(a.disclaimer)}</p>`;document.getElementById('results').style.display='block'}
async function analyze(save=false){const scenario=document.getElementById('scenario').value,title=document.getElementById('title').value;const url=save?'/api/scenario-rescue/cases':'/api/scenario-rescue/analyze';const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario,title})});const j=await r.json();if(!r.ok){alert(j.error||'Unable to analyze');return}render(j.analysis||j);if(save)loadCases()}
async function loadCases(){const r=await fetch('/api/scenario-rescue/cases'),j=await r.json();document.getElementById('cases').innerHTML=(j.items||[]).map(x=>`<div class="path"><b>${esc(x.title)}</b><div class="muted">${esc(x.outcome)} · ${esc(x.updated_at)}</div><div class="actions">${['reviewed','submitted','approved','denied','funded'].map(o=>`<button class="secondary" onclick="setOutcome(${x.id},'${o}')">${o}</button>`).join('')}</div></div>`).join('')||'<div class="muted">No saved cases yet.</div>'}
async function setOutcome(id,outcome){await fetch(`/api/scenario-rescue/cases/${id}/outcome`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({outcome})});loadCases()}
document.getElementById('analyze').onclick=()=>analyze(false);document.getElementById('save').onclick=()=>analyze(true);loadCases();
</script></body></html>'''

__all__ = ["install_scenario_rescue", "extract_facts", "missing_information", "rank_paths", "build_analysis"]
