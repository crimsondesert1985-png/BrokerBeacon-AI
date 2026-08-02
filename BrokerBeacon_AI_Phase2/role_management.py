"""Clear, least-privilege workspace role management for BrokerBeacon."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Blueprint, g, jsonify, request

ROLE_CATALOG = {
    "Owner": {
        "label": "Workspace Admin",
        "summary": "Full workspace control, including team access and settings.",
        "permissions": ["manage_team", "manage_settings", "assign_prospects", "review_prospects", "use_ai", "view_data"],
    },
    "Manager": {
        "label": "Manager",
        "summary": "Manage workflow, assignments, reviews, and standard users.",
        "permissions": ["manage_standard_users", "assign_prospects", "review_prospects", "use_ai", "view_data"],
    },
    "AE": {
        "label": "User",
        "summary": "Work assigned prospects, use approved AI tools, and update records.",
        "permissions": ["work_assigned_prospects", "use_ai", "view_data"],
    },
    "Read Only": {
        "label": "Viewer",
        "summary": "View workspace information without making changes.",
        "permissions": ["view_data"],
    },
}
ROLE_ORDER = ["Owner", "Manager", "AE", "Read Only"]


def install_role_management(app, db_path):
    bp = Blueprint("role_management", __name__)

    def connect():
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=30000")
        return conn

    def is_platform_owner():
        return bool(getattr(g, "is_platform_owner", False))

    def can_manage_team():
        return is_platform_owner() or getattr(g, "membership_role", None) in {"Owner", "Manager"}

    def can_assign_role(role):
        current = getattr(g, "membership_role", None)
        if is_platform_owner() or current == "Owner":
            return role in ROLE_CATALOG
        return current == "Manager" and role in {"AE", "Read Only"}

    def team_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not can_manage_team():
                return jsonify(error="Team management access required"), 403
            return fn(*args, **kwargs)
        return wrapped

    def audit(conn, action, target_id, detail):
        conn.execute(
            """insert into saas_audit_log(workspace_id,user_id,action,target_type,target_id,detail_json,ip_address,created_at)
               values(?,?,?,?,?,?,?,?)""",
            (
                getattr(g, "workspace_id", None), getattr(g, "user_id", None), action,
                "membership", str(target_id), json.dumps(detail),
                request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",", 1)[0][:120],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    @bp.get("/api/workspace/roles")
    def role_catalog():
        items = []
        if is_platform_owner():
            items.append({
                "key": "Platform Owner", "label": "Platform Owner",
                "summary": "Founder-level control across BrokerBeacon and all workspaces.",
                "permissions": ["platform_control", "manage_all_workspaces", "manage_team", "manage_settings", "view_audit"],
                "assignable": False,
            })
        for key in ROLE_ORDER:
            item = dict(ROLE_CATALOG[key])
            item.update(key=key, assignable=can_assign_role(key))
            items.append(item)
        return jsonify(items=items, current_role=getattr(g, "membership_role", ""), platform_owner=is_platform_owner())

    @bp.get("/api/workspace/members")
    @team_required
    def members():
        with connect() as conn:
            rows = conn.execute(
                """select m.id membership_id,m.role,u.id user_id,u.full_name,u.email,u.is_active,
                          u.is_platform_owner,u.last_login_at,m.created_at
                   from saas_memberships m join saas_users u on u.id=m.user_id
                   where m.workspace_id=?
                   order by case m.role when 'Owner' then 1 when 'Manager' then 2 when 'AE' then 3 else 4 end,
                            lower(u.full_name),lower(u.email)""",
                (g.workspace_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["role_label"] = "Platform Owner" if item["is_platform_owner"] else ROLE_CATALOG[item["role"]]["label"]
            item["can_edit"] = not item["is_platform_owner"] and can_assign_role(item["role"])
            items.append(item)
        return jsonify(items=items, count=len(items))

    @bp.patch("/api/workspace/members/<int:membership_id>/role")
    @team_required
    def update_role(membership_id):
        data = request.get_json(silent=True) or {}
        role = str(data.get("role") or "").strip()
        if role not in ROLE_CATALOG or not can_assign_role(role):
            return jsonify(error="You cannot assign that role"), 403
        with connect() as conn:
            member = conn.execute(
                """select m.*,u.email,u.full_name,u.is_platform_owner from saas_memberships m
                   join saas_users u on u.id=m.user_id where m.id=? and m.workspace_id=?""",
                (membership_id, g.workspace_id),
            ).fetchone()
            if not member:
                return jsonify(error="Workspace member not found"), 404
            if member["is_platform_owner"]:
                return jsonify(error="Platform Owner access cannot be changed here"), 403
            if getattr(g, "membership_role", None) == "Manager" and member["role"] in {"Owner", "Manager"}:
                return jsonify(error="Managers cannot change admin or manager access"), 403
            if member["role"] == "Owner" and role != "Owner":
                owners = conn.execute(
                    "select count(*) from saas_memberships where workspace_id=? and role='Owner'",
                    (g.workspace_id,),
                ).fetchone()[0]
                if int(owners) <= 1:
                    return jsonify(error="Assign another Workspace Admin before changing the last admin"), 409
            previous = member["role"]
            conn.execute("update saas_memberships set role=? where id=?", (role, membership_id))
            audit(conn, "membership.role_changed", membership_id, {
                "user_id": member["user_id"], "email": member["email"],
                "previous_role": previous, "new_role": role,
            })
            conn.commit()
        return jsonify(
            membership_id=membership_id, role=role, role_label=ROLE_CATALOG[role]["label"],
            message=f"{member['full_name'] or member['email']} is now {ROLE_CATALOG[role]['label']}.",
        )

    @bp.get("/workspace/team")
    @team_required
    def team_page():
        return '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Team & Access · BrokerBeacon</title><style>
body{margin:0;background:#07162e;color:#eaf2ff;font:14px Inter,Segoe UI,Arial}.wrap{max-width:1100px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.back{color:#80d8ff;text-decoration:none}.hero{margin:22px 0;padding:24px;border:1px solid #ffffff17;border-radius:20px;background:linear-gradient(145deg,#0d2547,#081a34);box-shadow:0 22px 60px #0006}.hero h1{margin:0 0 8px;font-size:28px}.hero p{margin:0;color:#9eb3d1}.roles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}.role,.member{border:1px solid #ffffff14;border-radius:16px;background:#ffffff08;padding:16px}.role b{display:block;margin-bottom:7px}.role span{color:#91a9c9;font-size:12px;line-height:1.45}.members{display:grid;gap:9px}.member{display:grid;grid-template-columns:1fr 190px 110px;gap:12px;align-items:center}.name b,.name small{display:block}.name small{color:#89a2c4;margin-top:3px}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#55d9a617;color:#65ebb8;font-size:11px;font-weight:800}select,button{width:100%;padding:10px;border-radius:10px;border:1px solid #ffffff1d;background:#0b2242;color:white}button{cursor:pointer;background:linear-gradient(135deg,#ff7a45,#ffb347);color:#271103;font-weight:900;border:0}.muted{color:#8199ba}.toast{position:fixed;right:20px;bottom:20px;padding:12px 16px;border-radius:12px;background:#12345c;opacity:0;transition:.2s}.toast.show{opacity:1}@media(max-width:800px){.roles{grid-template-columns:1fr 1fr}.member{grid-template-columns:1fr}.wrap{padding:16px}}@media(max-width:480px){.roles{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><div class="top"><a class="back" href="/platform/control-tower">← Control Tower</a><span class="badge">Least-privilege access</span></div><section class="hero"><h1>Team & Access</h1><p>Choose a clear role for each person. BrokerBeacon automatically limits what they can see and change.</p></section><section class="roles" id="roles"></section><section class="members" id="members"><div class="member muted">Loading team…</div></section></main><div class="toast" id="toast"></div><script>
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));let catalog=[];function toast(s){$('toast').textContent=s;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2400)}async function api(url,opt){const r=await fetch(url,opt),d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}async function load(){const [r,m]=await Promise.all([api('/api/workspace/roles'),api('/api/workspace/members')]);catalog=r.items.filter(x=>x.key!=='Platform Owner');$('roles').innerHTML=r.items.map(x=>`<article class="role"><b>${esc(x.label)}</b><span>${esc(x.summary)}</span></article>`).join('');$('members').innerHTML=m.items.map(x=>{const opts=catalog.filter(y=>y.assignable).map(y=>`<option value="${esc(y.key)}" ${y.key===x.role?'selected':''}>${esc(y.label)}</option>`).join('');return `<article class="member"><div class="name"><b>${esc(x.full_name||x.email)}</b><small>${esc(x.email)}</small></div>${x.is_platform_owner?'<span class="badge">Platform Owner</span>':x.can_edit?`<select id="role-${x.membership_id}">${opts}</select>`:`<span class="badge">${esc(x.role_label)}</span>`}${x.can_edit?`<button onclick="save(${x.membership_id})">Save role</button>`:'<span></span>'}</article>`}).join('')}async function save(id){try{const role=$('role-'+id).value,d=await api('/api/workspace/members/'+id+'/role',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});toast(d.message);await load()}catch(e){toast(e.message)}}load().catch(e=>{$('members').innerHTML=`<div class="member muted">${esc(e.message)}</div>`})
</script></body></html>'''

    app.register_blueprint(bp)
    return bp
