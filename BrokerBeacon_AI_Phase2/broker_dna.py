"""Broker DNA Sprint 1.

Adds a database-grounded Broker DNA API and injects the Broker DNA workspace into
BrokerBeacon's existing single-file UI without requiring a risky full rewrite of app.py.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import jsonify, request


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"pragma table_info({table})")}
    except sqlite3.Error:
        return set()


def _row_dict(row: sqlite3.Row | tuple, columns: list[str]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(zip(columns, row))


def _first(record: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return default


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            parsed = parser(text)
            return parsed.replace(tzinfo=None)
        except (TypeError, ValueError):
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            pass
    return None


def _days_since(value: Any) -> int | None:
    parsed = _parse_date(value)
    if not parsed:
        return None
    return max(0, (datetime.now() - parsed).days)


def _prospect_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cols = _columns(conn, "prospects")
    if not cols:
        return []
    selected = [
        name for name in (
            "id", "company", "owner", "city", "state", "signal", "team", "team_size",
            "email", "phone", "specialties", "status", "score", "verification_status",
            "verified_at", "created_at", "updated_at", "last_contact", "last_contact_at",
            "next_followup", "follow_up_date", "notes"
        ) if name in cols
    ]
    if "id" not in selected:
        return []
    sql = "select " + ",".join(selected) + " from prospects"
    cur = conn.execute(sql)
    return [_row_dict(row, selected) for row in cur.fetchall()]


def _activity_summary(conn: sqlite3.Connection, prospect_id: int) -> dict[str, Any]:
    summary = {"count": 0, "last_at": None, "positive": 0, "meetings": 0}
    for table in ("activities", "activity", "sales_activities", "notes"):
        cols = _columns(conn, table)
        if not cols:
            continue
        prospect_col = next((c for c in ("prospect_id", "broker_id", "account_id") if c in cols), None)
        if not prospect_col:
            continue
        date_col = next((c for c in ("created_at", "activity_at", "date", "updated_at") if c in cols), None)
        outcome_col = next((c for c in ("outcome", "type", "activity_type", "note_type") if c in cols), None)
        select = ["count(*)"]
        if date_col:
            select.append(f"max({date_col})")
        sql = f"select {','.join(select)} from {table} where {prospect_col}=?"
        try:
            row = conn.execute(sql, (prospect_id,)).fetchone()
            summary["count"] += int(row[0] or 0)
            if date_col and row[1]:
                if not summary["last_at"] or str(row[1]) > str(summary["last_at"]):
                    summary["last_at"] = row[1]
            if outcome_col:
                outcomes = [str(r[0] or "").lower() for r in conn.execute(
                    f"select {outcome_col} from {table} where {prospect_col}=?", (prospect_id,)
                ).fetchall()]
                summary["positive"] += sum(any(k in x for k in ("positive", "connected", "replied", "interested")) for x in outcomes)
                summary["meetings"] += sum("meeting" in x for x in outcomes)
        except sqlite3.Error:
            continue
    return summary


def _dna_for(record: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    prospect_id = int(record.get("id") or 0)
    company = str(_first(record, "company", default="Unnamed account"))
    status = str(_first(record, "status", default="New"))
    specialties = str(_first(record, "specialties", default=""))
    verification = str(_first(record, "verification_status", default="Needs verification"))
    team_size = int(_first(record, "team", "team_size", default=0) or 0)
    base_score = int(_first(record, "score", default=0) or 0)
    last_touch = activity.get("last_at") or _first(record, "last_contact_at", "last_contact", "updated_at", "created_at")
    stale_days = _days_since(last_touch)

    relationship = 20
    relationship += min(25, activity["count"] * 3)
    relationship += min(20, activity["positive"] * 8)
    relationship += min(20, activity["meetings"] * 10)
    if stale_days is not None:
        relationship += 15 if stale_days <= 7 else 8 if stale_days <= 21 else 0
    relationship = max(0, min(100, relationship))

    opportunity = base_score if base_score else 35
    if "verified" in verification.lower():
        opportunity += 10
    opportunity += min(15, team_size * 3)
    if specialties:
        opportunity += 8
    if status.lower() in {"replied", "meeting", "approved"}:
        opportunity += 12
    opportunity = max(0, min(100, opportunity))

    engagement = min(100, activity["count"] * 8 + activity["positive"] * 15 + activity["meetings"] * 20)
    fit = 40 + (15 if specialties else 0) + min(20, team_size * 4)
    fit = max(0, min(100, fit))

    dna_score = round(relationship * 0.35 + opportunity * 0.35 + engagement * 0.15 + fit * 0.15)
    if dna_score >= 80:
        tier = "Priority"
    elif dna_score >= 65:
        tier = "Growth"
    elif dna_score >= 45:
        tier = "Develop"
    else:
        tier = "Research"

    reasons: list[str] = []
    if "verified" in verification.lower():
        reasons.append("Verified account data")
    if team_size:
        reasons.append(f"Team size signal: {team_size}")
    if specialties:
        reasons.append("Product-fit specialties are recorded")
    if activity["count"]:
        reasons.append(f"{activity['count']} stored relationship interactions")
    if stale_days is not None and stale_days > 30:
        reasons.append(f"Relationship has been quiet for {stale_days} days")
    if not reasons:
        reasons.append("Limited stored relationship data; research is the next step")

    if stale_days is None or stale_days > 30:
        next_action = "Verify the primary contact and start a value-led introduction."
    elif activity["positive"] or status.lower() in {"replied", "meeting"}:
        next_action = "Follow up on the active conversation with a product-specific scenario offer."
    elif opportunity >= 70:
        next_action = "Call this account today and lead with the strongest recorded product fit."
    else:
        next_action = "Add one useful relationship touch and capture the broker's current priorities."

    return {
        "prospect_id": prospect_id,
        "company": company,
        "owner": _first(record, "owner", default=""),
        "city": _first(record, "city", default=""),
        "state": _first(record, "state", default=""),
        "status": status,
        "specialties": specialties,
        "verification_status": verification,
        "dna_score": dna_score,
        "tier": tier,
        "relationship_health": relationship,
        "opportunity_strength": opportunity,
        "engagement": engagement,
        "product_fit": fit,
        "last_touch": last_touch,
        "days_since_touch": stale_days,
        "next_best_action": next_action,
        "reasons": reasons,
    }


def _persist_snapshot(conn: sqlite3.Connection, dna: dict[str, Any]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """insert into broker_dna(prospect_id,dna_score,tier,relationship_health,opportunity_strength,
        engagement,product_fit,next_best_action,reasons_json,calculated_at,updated_at)
        values(?,?,?,?,?,?,?,?,?,?,?)
        on conflict(prospect_id) do update set dna_score=excluded.dna_score,tier=excluded.tier,
        relationship_health=excluded.relationship_health,opportunity_strength=excluded.opportunity_strength,
        engagement=excluded.engagement,product_fit=excluded.product_fit,
        next_best_action=excluded.next_best_action,reasons_json=excluded.reasons_json,
        calculated_at=excluded.calculated_at,updated_at=excluded.updated_at""",
        (
            dna["prospect_id"], dna["dna_score"], dna["tier"], dna["relationship_health"],
            dna["opportunity_strength"], dna["engagement"], dna["product_fit"],
            dna["next_best_action"], json.dumps(dna["reasons"]), now, now,
        ),
    )


def _load_dna(db_path: Path, search: str = "", tier: str = "") -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        results = []
        for record in _prospect_rows(conn):
            dna = _dna_for(record, _activity_summary(conn, int(record["id"])))
            _persist_snapshot(conn, dna)
            results.append(dna)
        conn.commit()
    if search:
        q = search.lower()
        results = [r for r in results if q in " ".join(str(r.get(k, "")) for k in ("company", "owner", "city", "state", "specialties")).lower()]
    if tier and tier.lower() != "all":
        results = [r for r in results if r["tier"].lower() == tier.lower()]
    return sorted(results, key=lambda item: (-item["dna_score"], item["company"].lower()))


DNA_CSS = """
.dna-toolbar{display:grid;grid-template-columns:1fr 180px auto;gap:10px;margin:14px 0}.dna-toolbar input,.dna-toolbar select{width:100%}
.dna-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.dna-kpi{padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}.dna-kpi span{display:block;color:var(--muted);font-size:11px}.dna-kpi strong{display:block;font-size:28px;margin-top:7px}.dna-layout{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}.dna-card{border:1px solid var(--line);border-radius:14px;padding:14px;background:var(--panel);margin-bottom:10px;cursor:pointer}.dna-card:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(20,58,105,.08)}.dna-card-top{display:flex;justify-content:space-between;gap:12px}.dna-score{font-size:24px;font-weight:900;color:#174ea6}.dna-bars{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:11px}.dna-mini{background:var(--panel-2);border-radius:9px;padding:8px}.dna-mini small{display:block;color:var(--muted)}.dna-detail-empty{padding:32px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:14px}.dna-reason{padding:8px 0;border-bottom:1px solid var(--line)}@media(max-width:950px){.dna-layout{grid-template-columns:1fr}.dna-kpis,.dna-bars{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.dna-toolbar,.dna-kpis,.dna-bars{grid-template-columns:1fr}}
"""

DNA_SECTION = """
<section id="brokerdna" class="view"><div class="hero"><div><div class="kicker">BROKER DNA · SPRINT 1</div><h2>Relationship intelligence for every broker account.</h2><p>Broker DNA combines stored relationship activity, opportunity strength, engagement, product fit, and recency. Every score is explainable and based only on data already present in BrokerBeacon.</p></div><span class="pill">Database-grounded</span></div><div class="dna-toolbar"><input id="dnaSearch" placeholder="Search company, owner, city, state, or specialty"><select id="dnaTier"><option>All</option><option>Priority</option><option>Growth</option><option>Develop</option><option>Research</option></select><button class="btn primary" id="dnaRefresh">Recalculate DNA</button></div><div class="dna-kpis"><div class="dna-kpi"><span>Accounts scored</span><strong id="dnaAccounts">0</strong></div><div class="dna-kpi"><span>Priority accounts</span><strong id="dnaPriority">0</strong></div><div class="dna-kpi"><span>At-risk relationships</span><strong id="dnaRisk">0</strong></div><div class="dna-kpi"><span>Average DNA score</span><strong id="dnaAverage">0</strong></div></div><div class="dna-layout"><div class="panel"><div class="profile-head"><div><h3>Broker DNA roster</h3><p class="muted">Ranked by explainable relationship and opportunity signals.</p></div></div><div id="dnaList"><div class="empty">Loading Broker DNA…</div></div></div><div class="panel"><div id="dnaDetail" class="dna-detail-empty">Select an account to see its DNA breakdown and next best action.</div></div></div></section>
"""

DNA_JS = r"""
let brokerDnaRows=[];
async function brokerDna(){
  const search=document.querySelector('#dnaSearch')?.value||'';
  const tier=document.querySelector('#dnaTier')?.value||'All';
  const data=await api('/api/broker-dna?search='+encodeURIComponent(search)+'&tier='+encodeURIComponent(tier));
  brokerDnaRows=data.accounts||[];
  document.querySelector('#dnaAccounts').textContent=data.summary?.accounts||0;
  document.querySelector('#dnaPriority').textContent=data.summary?.priority||0;
  document.querySelector('#dnaRisk').textContent=data.summary?.at_risk||0;
  document.querySelector('#dnaAverage').textContent=data.summary?.average||0;
  const list=document.querySelector('#dnaList');
  if(!brokerDnaRows.length){list.innerHTML='<div class="empty">No accounts match these filters.</div>';return}
  list.innerHTML=brokerDnaRows.map((r,i)=>`<div class="dna-card" onclick="showBrokerDnaDetail(${i})"><div class="dna-card-top"><div><b>${esc(r.company)}</b><div class="muted">${esc([r.owner,r.city,r.state].filter(Boolean).join(' · '))}</div><span class="pill">${esc(r.tier)}</span></div><div class="dna-score">${r.dna_score}</div></div><div class="dna-bars"><div class="dna-mini"><small>Relationship</small><b>${r.relationship_health}</b></div><div class="dna-mini"><small>Opportunity</small><b>${r.opportunity_strength}</b></div><div class="dna-mini"><small>Engagement</small><b>${r.engagement}</b></div><div class="dna-mini"><small>Product fit</small><b>${r.product_fit}</b></div></div></div>`).join('');
  showBrokerDnaDetail(0);
}
function showBrokerDnaDetail(i){
  const r=brokerDnaRows[i],detail=document.querySelector('#dnaDetail');if(!r||!detail)return;
  detail.className='';detail.innerHTML=`<div class="kicker">${esc(r.tier)} ACCOUNT</div><h2>${esc(r.company)}</h2><p class="muted">${esc(r.specialties||'No specialties recorded')}</p><div class="scoregrid"><div class="scorebox"><span>DNA score</span><strong>${r.dna_score}</strong></div><div class="scorebox"><span>Relationship</span><strong>${r.relationship_health}</strong></div><div class="scorebox"><span>Opportunity</span><strong>${r.opportunity_strength}</strong></div><div class="scorebox"><span>Engagement</span><strong>${r.engagement}</strong></div></div><h3>Why this score</h3>${(r.reasons||[]).map(x=>`<div class="dna-reason">✓ ${esc(x)}</div>`).join('')}<h3>Next best action</h3><div class="nextaction">${esc(r.next_best_action)}</div><p class="muted">Last stored touch: ${esc(r.last_touch||'Not recorded')}</p>`;
}
function initBrokerDna(){
  document.querySelector('#dnaRefresh')?.addEventListener('click',brokerDna);
  document.querySelector('#dnaSearch')?.addEventListener('input',()=>{clearTimeout(window.__dnaTimer);window.__dnaTimer=setTimeout(brokerDna,250)});
  document.querySelector('#dnaTier')?.addEventListener('change',brokerDna);
  const oldShow=window.show;
  if(typeof oldShow==='function'){window.show=function(v){oldShow(v);if(v==='brokerdna')brokerDna()}}
}
setTimeout(initBrokerDna,0);
"""


def register_broker_dna(app, db_path: str | Path) -> None:
    """Register API and UI injection exactly once."""
    if app.config.get("BROKER_DNA_REGISTERED"):
        return
    app.config["BROKER_DNA_REGISTERED"] = True
    db_path = Path(db_path)

    def broker_dna_api():
        accounts = _load_dna(db_path, request.args.get("search", ""), request.args.get("tier", ""))
        average = round(sum(a["dna_score"] for a in accounts) / len(accounts)) if accounts else 0
        summary = {
            "accounts": len(accounts),
            "priority": sum(a["tier"] == "Priority" for a in accounts),
            "at_risk": sum((a["days_since_touch"] or 0) > 30 for a in accounts),
            "average": average,
        }
        return jsonify({"accounts": accounts, "summary": summary, "generated_at": datetime.now().isoformat(timespec="seconds")})

    app.add_url_rule("/api/broker-dna", "broker_dna_api", broker_dna_api, methods=["GET"])

    @app.after_request
    def inject_broker_dna(response):
        if request.path != "/" or not response.content_type.startswith("text/html"):
            return response
        try:
            html = response.get_data(as_text=True)
            if 'data-v="brokerdna"' in html:
                return response
            html = html.replace("</style></head>", DNA_CSS + "</style></head>", 1)
            html = html.replace("</nav>", '<button data-v="brokerdna">🧬 Broker DNA</button></nav>', 1)
            html = html.replace("</main></div><input type=", DNA_SECTION + "</main></div><input type=", 1)
            html = html.replace("</script>", DNA_JS + "\n</script>", 1)
            response.set_data(html)
            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            return response
        return response
