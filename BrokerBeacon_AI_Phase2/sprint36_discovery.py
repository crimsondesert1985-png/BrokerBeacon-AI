"""Sprint 36: state-based prospect discovery, review, import, and export."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request

bp = Blueprint("sprint36_discovery", __name__)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _db():
    return current_app.config["BROKERBEACON_DB_CONNECTOR"]()


def _columns(con, table):
    return {row[1] for row in con.execute(f"pragma table_info({table})")}


def _insert_supported(con, table, values):
    columns = _columns(con, table)
    usable = {key: value for key, value in values.items() if key in columns}
    if not usable:
        raise RuntimeError(f"No supported columns found for {table}")
    names = list(usable)
    marks = ",".join("?" for _ in names)
    cur = con.execute(
        f"insert into {table}({','.join(names)}) values({marks})",
        [usable[name] for name in names],
    )
    return cur.lastrowid


def install(app, db_connector):
    """Install once after the main BrokerBeacon app has been imported."""
    if app.extensions.get("sprint36_discovery"):
        return
    app.extensions["sprint36_discovery"] = True
    app.config["BROKERBEACON_DB_CONNECTOR"] = db_connector
    with db_connector() as con:
        con.executescript(
            """
            create table if not exists saved_discovery_searches(
                id integer primary key,
                name text not null,
                state text default '', city text default '', zip_code text default '',
                radius integer default 0, company text default '', officer text default '',
                nmls text default '', active_only integer not null default 1,
                created_at text not null, updated_at text not null
            );
            create index if not exists idx_saved_discovery_state
                on saved_discovery_searches(state,name);
            """
        )
    app.register_blueprint(bp)

    @app.after_request
    def inject_discovery_center(response):
        if response.mimetype != "text/html" or response.status_code != 200:
            return response
        page = response.get_data(as_text=True)
        if 'id="discovery"' in page or '<nav>' not in page:
            return response
        page = page.replace(
            "</nav>",
            '<button data-v="discovery" title="Search public-source mortgage contacts by state">⌕ Prospect Discovery</button></nav>',
            1,
        )
        page = page.replace("</main>", DISCOVERY_UI + "</main>", 1)
        response.set_data(page)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response


def _filters(data=None):
    data = data or request.get_json(silent=True) or request.args
    return {
        "state": str(data.get("state", "")).strip().upper(),
        "city": str(data.get("city", "")).strip(),
        "zip_code": str(data.get("zip_code", "")).strip(),
        "radius": int(data.get("radius", 0) or 0),
        "company": str(data.get("company", "")).strip(),
        "officer": str(data.get("officer", "")).strip(),
        "nmls": str(data.get("nmls", "")).strip(),
        "active_only": str(data.get("active_only", "1")).lower() not in {"0", "false", "no"},
    }


def _query(filters, limit=500):
    where, params = ["1=1"], []
    for field, column in (("state", "c.state"), ("city", "c.metro"),
                          ("company", "c.company"), ("officer", "c.owner"),
                          ("nmls", "c.nmls")):
        value = filters[field]
        if value:
            if field == "state":
                where.append("upper(c.state)=?")
                params.append(value)
            else:
                where.append(f"lower(coalesce({column},'')) like ?")
                params.append(f"%{value.lower()}%")
    if filters["active_only"]:
        where.append("c.status not in ('Rejected','Inactive')")
    params.append(max(1, min(int(limit), 2000)))
    sql = f"""
        select c.id,c.company,c.owner,c.state,c.metro,c.nmls,c.email,c.phone,
               c.website,c.linkedin_url,c.source_name,c.source_url,c.status,
               c.confidence,c.signal,c.discovered_at,c.approved_prospect_id,
               c.duplicate_prospect_id,coalesce(r.stage,'') research_stage,
               coalesce(r.ash_score,0) ash_score,coalesce(r.ash_reason,'') ash_reason
        from scout_candidates c
        left join scout_research r on r.candidate_id=c.id
        where {' and '.join(where)}
        order by case when c.status='Approved' then 0 else 1 end,
                 coalesce(r.ash_score,0) desc,c.confidence desc,c.id desc
        limit ?
    """
    with _db() as con:
        rows = [dict(row) for row in con.execute(sql, params)]
    for row in rows:
        row["verification_status"] = (
            "Imported" if row["approved_prospect_id"] else
            "Possible duplicate" if row["duplicate_prospect_id"] else
            "Needs NMLS verification" if row["status"] in {"Pending review", "Research queued"} else
            row["status"]
        )
    return rows


@bp.get("/api/discovery-center")
def discovery_center():
    filters = _filters()
    with _db() as con:
        saved = [dict(row) for row in con.execute(
            "select * from saved_discovery_searches order by updated_at desc,id desc limit 100"
        )]
        history = [dict(row) for row in con.execute(
            "select * from scout_runs order by id desc limit 30"
        )]
    return jsonify(filters=filters, results=_query(filters, request.args.get("limit", 500)),
                   saved_searches=saved, history=history)


@bp.post("/api/discovery-center/saved-searches")
def save_search():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify(error="Search name is required"), 400
    filters, now = _filters(data), _now()
    with _db() as con:
        cur = con.execute(
            """insert into saved_discovery_searches
            (name,state,city,zip_code,radius,company,officer,nmls,active_only,created_at,updated_at)
            values(?,?,?,?,?,?,?,?,?,?,?)""",
            (name, filters["state"], filters["city"], filters["zip_code"], filters["radius"],
             filters["company"], filters["officer"], filters["nmls"],
             int(filters["active_only"]), now, now),
        )
    return jsonify(id=cur.lastrowid, name=name, **filters), 201


@bp.post("/api/discovery-center/import")
def import_selected():
    data = request.get_json(silent=True) or {}
    ids = [int(value) for value in data.get("candidate_ids", []) if str(value).isdigit()]
    if not ids:
        return jsonify(error="Select at least one prospect"), 400
    imported = skipped = 0
    with _db() as con:
        for candidate_id in ids[:1000]:
            candidate = con.execute("select * from scout_candidates where id=?", (candidate_id,)).fetchone()
            if not candidate or candidate["approved_prospect_id"]:
                skipped += 1
                continue
            existing = con.execute(
                "select id from prospects where lower(company)=lower(?) and upper(state)=upper(?) limit 1",
                (candidate["company"], candidate["state"]),
            ).fetchone()
            if existing:
                con.execute("""update scout_candidates set duplicate_prospect_id=?,status='Duplicate',
                    reviewed_at=? where id=?""", (existing["id"], _now(), candidate_id))
                skipped += 1
                continue
            now = _now()
            prospect_id = _insert_supported(con, "prospects", {
                "company": candidate["company"] or candidate["result_title"],
                "owner": candidate["owner"], "city": candidate["metro"],
                "metro": candidate["metro"], "state": candidate["state"],
                "nmls": candidate["nmls"], "website": candidate["website"],
                "source": candidate["source_url"], "source_name": candidate["source_name"],
                "source_url": candidate["source_url"], "signal": candidate["signal"],
                "verification_status": "Needs NMLS verification",
                "status": "New", "created_at": now, "updated_at": now,
            })
            if candidate["owner"] or candidate["email"] or candidate["phone"]:
                _insert_supported(con, "contacts", {
                    "prospect_id": prospect_id, "name": candidate["owner"],
                    "title": "Mortgage contact", "email": candidate["email"],
                    "phone": candidate["phone"], "is_primary": 1,
                    "roster_status": "Public web discovery", "source_url": candidate["source_url"],
                    "created_at": now, "updated_at": now,
                })
            con.execute("""update scout_candidates set approved_prospect_id=?,status='Approved',
                reviewed_at=? where id=?""", (prospect_id, now, candidate_id))
            imported += 1
    return jsonify(imported=imported, skipped=skipped)


@bp.get("/api/discovery-center/export.csv")
def export_csv():
    rows = _query(_filters(), 2000)
    fields = ["company", "owner", "state", "metro", "nmls", "phone", "email",
              "website", "linkedin_url", "verification_status", "confidence",
              "source_name", "source_url", "discovered_at"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(output.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=brokerbeacon-prospect-discovery.csv"
    })


DISCOVERY_UI = r'''
<style>
.discovery-shell{display:grid;gap:14px}.discovery-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.discovery-actions{display:flex;gap:8px;flex-wrap:wrap}.discovery-table-wrap{overflow:auto}.dc-check{width:18px!important;height:18px}.verify-warn,.verify-good{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800}.verify-warn{color:#8a5a00;background:#fff2c2}.verify-good{color:#076c42;background:#dff8eb}.saved-search{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}@media(max-width:900px){.discovery-filters{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.discovery-filters{grid-template-columns:1fr}}
</style>
<section id="discovery" class="view"><div class="discovery-shell">
<div class="hero"><div><div class="kicker">SPRINT 36 · PROSPECT DISCOVERY</div><h2>Find new mortgage contacts by state.</h2><p>Search public-source discoveries, review evidence, select records, and import them into BrokerBeacon.</p></div><div class="discovery-actions"><button class="btn" onclick="exportDiscovery()">Export CSV</button><button class="btn primary" onclick="runDiscovery()">Search</button></div></div>
<div class="panel"><div class="discovery-filters"><label>State<select id="dcState"></select></label><label>City / metro<input id="dcCity" placeholder="Charlotte"></label><label>ZIP code<input id="dcZip" placeholder="28202"></label><label>Radius<select id="dcRadius"><option value="0">Any radius</option><option>10</option><option>25</option><option>50</option><option>100</option></select></label><label>Company<input id="dcCompany" placeholder="Mortgage company"></label><label>Loan officer<input id="dcOfficer" placeholder="Contact name"></label><label>NMLS ID<input id="dcNmls" placeholder="NMLS ID"></label><label>License status<select id="dcActive"><option value="1">Current / reviewable</option><option value="0">Include inactive</option></select></label></div><div class="discovery-actions"><button class="btn primary" onclick="runDiscovery()">Search prospects</button><button class="btn" onclick="saveDiscoverySearch()">Save search</button><button class="btn" onclick="clearDiscovery()">Clear</button><button class="btn" onclick="selectAllDiscovery(true)">Select all</button><button class="btn" onclick="selectAllDiscovery(false)">Clear selection</button><button class="btn primary" onclick="importDiscovery()">Import selected</button></div><p class="contact-note">Public-source records require NMLS or state-regulator verification before outreach. Import does not certify an active license.</p></div>
<div class="grid"><div class="panel" style="grid-column:1/-1"><div class="profile-head"><div><h3>Search results</h3><p class="muted" id="dcSummary">Choose a state or other filters, then search.</p></div></div><div class="discovery-table-wrap"><table><thead><tr><th></th><th>Company / contact</th><th>Location</th><th>NMLS</th><th>Phone / email</th><th>Verification</th><th>Source</th></tr></thead><tbody id="dcResults"><tr><td colspan="7" class="empty">No search run yet.</td></tr></tbody></table></div></div><div class="panel"><h3>Saved searches</h3><div id="dcSaved" class="empty">No saved searches yet.</div></div><div class="panel"><h3>Discovery history</h3><div id="dcHistory" class="empty">No discovery runs yet.</div></div></div></div></section>
<script>
let discoveryData={results:[],saved_searches:[],history:[]};
const dc=id=>document.getElementById(id);
function discoveryFilters(){return {state:dc('dcState').value,city:dc('dcCity').value,zip_code:dc('dcZip').value,radius:dc('dcRadius').value,company:dc('dcCompany').value,officer:dc('dcOfficer').value,nmls:dc('dcNmls').value,active_only:dc('dcActive').value}}
function initDiscovery(){const states=['','AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'];dc('dcState').innerHTML=states.map(x=>`<option value="${x}">${x||'All states'}</option>`).join('')}
async function runDiscovery(){discoveryData=await api('/api/discovery-center?'+new URLSearchParams(discoveryFilters()));renderDiscovery()}
function renderDiscovery(){const rows=discoveryData.results||[];dc('dcSummary').textContent=`${rows.length} matching public-source records`;dc('dcResults').innerHTML=rows.length?rows.map(x=>`<tr><td><input class="dcPick dc-check" type="checkbox" value="${x.id}"></td><td><b>${esc(x.company||'Unnamed company')}</b><div class="mini">${esc(x.owner||'Contact not listed')}</div></td><td>${esc(x.metro||'')} ${esc(x.state||'')}</td><td>${esc(x.nmls||'Not listed')}</td><td>${x.phone?`<a href="tel:${esc(x.phone)}">${esc(x.phone)}</a>`:'No phone'}<div>${x.email?`<a href="mailto:${esc(x.email)}">${esc(x.email)}</a>`:'No email'}</div></td><td><span class="${x.verification_status==='Imported'?'verify-good':'verify-warn'}">${esc(x.verification_status)}</span></td><td><a class="source-link" href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_name||'Open source')}</a></td></tr>`).join(''):'<tr><td colspan="7" class="empty">No records matched these filters.</td></tr>';dc('dcSaved').innerHTML=(discoveryData.saved_searches||[]).length?discoveryData.saved_searches.map(x=>`<div class="saved-search"><div><b>${esc(x.name)}</b><div class="mini">${esc(x.state||'All states')} · ${esc(x.company||x.city||'All contacts')}</div></div><button class="btn smallbtn" onclick='loadDiscoverySearch(${JSON.stringify(x)})'>Run</button></div>`).join(''):'<div class="empty">No saved searches yet.</div>';dc('dcHistory').innerHTML=(discoveryData.history||[]).length?discoveryData.history.map(x=>`<div class="timeline-item"><b>${esc(x.state)} ${esc(x.metro||'')}</b><div class="mini">${esc(x.status)} · ${x.result_count||0} found · ${esc(x.started_at||'')}</div></div>`).join(''):'<div class="empty">No discovery runs yet.</div>'}
function selectAllDiscovery(on){document.querySelectorAll('.dcPick').forEach(x=>x.checked=on)}
async function importDiscovery(){const ids=[...document.querySelectorAll('.dcPick:checked')].map(x=>+x.value);if(!ids.length)return msg('Select at least one prospect');const d=await api('/api/discovery-center/import',{method:'POST',body:JSON.stringify({candidate_ids:ids})});msg(`${d.imported} imported · ${d.skipped} skipped`);runDiscovery()}
async function saveDiscoverySearch(){const name=prompt('Name this search');if(!name)return;await api('/api/discovery-center/saved-searches',{method:'POST',body:JSON.stringify({name,...discoveryFilters()})});msg('Search saved');runDiscovery()}
function loadDiscoverySearch(x){dc('dcState').value=x.state||'';dc('dcCity').value=x.city||'';dc('dcZip').value=x.zip_code||'';dc('dcRadius').value=x.radius||0;dc('dcCompany').value=x.company||'';dc('dcOfficer').value=x.officer||'';dc('dcNmls').value=x.nmls||'';dc('dcActive').value=x.active_only?1:0;runDiscovery()}
function clearDiscovery(){['dcCity','dcZip','dcCompany','dcOfficer','dcNmls'].forEach(id=>dc(id).value='');dc('dcState').value='';dc('dcRadius').value='0';dc('dcActive').value='1';runDiscovery()}
function exportDiscovery(){location.href='/api/discovery-center/export.csv?'+new URLSearchParams(discoveryFilters())}
document.addEventListener('DOMContentLoaded',initDiscovery);
</script>
'''
