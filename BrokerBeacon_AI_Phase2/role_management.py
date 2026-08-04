"""Clear, least-privilege workspace role and invitation management for BrokerBeacon."""
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
        return '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Invite & Manage Users · BrokerBeacon</title><style>
:root{--bg:#07101f;--panel:#101d35;--line:#ffffff18;--text:#f6fbff;--muted:#9eb0ca;--cyan:#25d5ff;--violet:#8568ff;--green:#48e0a4;--orange:#ff9d5c;--red:#ff6b7d}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#8568ff40,transparent 30%),radial-gradient(circle at 100% 0,#25d5ff20,transparent 28%),var(--bg);color:var(--text);font:14px Inter,Segoe UI,Arial}.wrap{max-width:1120px;margin:auto;padding:30px 18px}.top{display:flex;justify-content:space-between;align-items:center;gap:14px}.back{color:#9cecff;text-decoration:none}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#48e0a417;color:#8af1c8;font-size:11px;font-weight:800}.hero,.panel{border:1px solid var(--line);border-radius:20px;background:#101d35dd;box-shadow:0 22px 60px #0005}.hero{padding:24px;margin:20px 0}.hero h1{font-size:clamp(30px,5vw,50px);margin:5px 0 8px}.eyebrow{color:var(--cyan);font-size:11px;font-weight:900;letter-spacing:.14em;text-transform:uppercase}.muted{color:var(--muted);line-height:1.55}.grid{display:grid;grid-template-columns:.9fr 1.1fr;gap:14px}.panel{padding:19px}.panel h2{margin:0 0 8px}.form{display:grid;gap:10px;margin-top:15px}label{font-size:11px;color:var(--muted);font-weight:800}input,select,button{width:100%;padding:11px;border-radius:10px;border:1px solid var(--line);background:#0a172c;color:white}button{cursor:pointer;font-weight:850}.primary{border:0;background:linear-gradient(135deg,var(--violet),#4fa8ff)}.danger{color:#ffb3bd}.roles{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:14px 0}.role{padding:13px;border:1px solid var(--line);border-radius:13px;background:#ffffff07}.role b{display:block;margin-bottom:5px}.role span{font-size:11px;color:var(--muted);line-height:1.45}.list{display:grid;gap:9px;margin-top:12px}.member,.invite{display:grid;grid-template-columns:1fr 180px 110px;gap:10px;align-items:center;padding:13px;border:1px solid var(--line);border-radius:14px;background:#ffffff07}.person b,.person small{display:block}.person small{color:var(--muted);margin-top:3px}.actions{display:flex;gap:7px}.actions button{padding:8px}.pending{margin-top:16px}.empty{padding:22px;text-align:center;color:var(--muted)}.status{font-size:11px;color:var(--muted)}.toast{position:fixed;right:20px;bottom:20px;max-width:360px;padding:13px 16px;border-radius:12px;background:#163d65;opacity:0;transform:translateY(8px);transition:.2s;pointer-events:none}.toast.show{opacity:1;transform:none}.rule{margin-top:12px;padding:12px;border-left:3px solid var(--green);background:#48e0a40d;border-radius:0 10px 10px 0}.hint{font-size:11px;color:var(--muted)}@media(max-width:850px){.grid{grid-template-columns:1fr}.roles{grid-template-columns:1fr 1fr}.member,.invite{grid-template-columns:1fr}}@media(max-width:500px){.roles{grid-template-columns:1fr}.wrap{padding:16px}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><main class="wrap"><div class="top"><a class="back" href="/platform/control-tower">← Control Tower</a><span class="badge">Secure individual access</span></div><section class="hero"><div class="eyebrow">Team & Access</div><h1>Invite people. Keep control.</h1><div class="muted">Each person gets their own email login and creates their own password. You choose what they can see and change.</div></section><section class="roles" id="roles"></section><div class="grid"><section class="panel"><h2>Invite a new user</h2><div class="muted">Enter their email, choose the least access they need, and send a seven-day invitation.</div><div class="form"><div><label>Email address</label><input id="invite-email" type="email" autocomplete="email" placeholder="name@company.com"></div><div><label>Role</label><select id="invite-role"></select></div><button class="primary" onclick="sendInvite()">Send secure invitation</button></div><div id="invite-result" class="rule" hidden></div><div class="rule"><b>Passwords stay private.</b><div class="hint">You never choose, view, or store another person’s password. They create it through the secure invitation.</div></div><div class="pending"><h2>Pending invitations</h2><div class="list" id="pending"><div class="empty">Loading invitations…</div></div></div></section><section class="panel"><h2>Current users</h2><div class="muted">Change a role when responsibilities change. Workspace Admins can remove access completely.</div><div class="list" id="members"><div class="empty">Loading users…</div></div></section></div></main><div class="toast" id="toast"></div><script>
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));let catalog=[],context={};function toast(s){$('toast').textContent=s;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2800)}async function api(url,opt){const r=await fetch(url,opt),d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}function roleOptions(selected){return catalog.filter(x=>x.assignable).map(x=>`<option value="${esc(x.key)}" ${x.key===selected?'selected':''}>${esc(x.label)}</option>`).join('')}async function load(){const [r,m,s]=await Promise.all([api('/api/workspace/roles'),api('/api/workspace/members'),api('/api/saas/members')]);context=r;catalog=r.items.filter(x=>x.key!=='Platform Owner');$('roles').innerHTML=r.items.map(x=>`<article class="role"><b>${esc(x.label)}</b><span>${esc(x.summary)}</span></article>`).join('');$('invite-role').innerHTML=roleOptions('AE');$('members').innerHTML=m.items.length?m.items.map(x=>`<article class="member"><div class="person"><b>${esc(x.full_name||x.email)}</b><small>${esc(x.email)} · ${x.last_login_at?'Last login '+esc(x.last_login_at):'Has not signed in yet'}</small></div>${x.is_platform_owner?'<span class="badge">Platform Owner</span>':x.can_edit?`<select id="role-${x.membership_id}">${roleOptions(x.role)}</select>`:`<span class="badge">${esc(x.role_label)}</span>`}<div class="actions">${x.can_edit?`<button onclick="saveRole(${x.membership_id})">Save</button>`:''}${!x.is_platform_owner&&context.current_role==='Owner'&&x.user_id!==context.user_id?`<button class="danger" onclick="removeUser(${x.user_id},'${esc(x.email)}')">Remove</button>`:''}</div></article>`).join(''):'<div class="empty">No users found.</div>';$('pending').innerHTML=s.pending_invitations.length?s.pending_invitations.map(x=>`<article class="invite"><div class="person"><b>${esc(x.email)}</b><small>${esc(x.role)} · expires ${esc(x.expires_at)}</small></div><span class="status">Waiting for acceptance</span><div class="actions"><button onclick="resend('${esc(x.email)}','${esc(x.role)}')">Resend</button></div></article>`).join(''):'<div class="empty">No pending invitations.</div>'}async function sendInvite(){const email=$('invite-email').value.trim(),role=$('invite-role').value;if(!email)return toast('Enter an email address.');try{const d=await api('/api/saas/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,role})});toast(d.email_delivered?'Invitation sent.':'Invitation created, but email delivery is not configured.');$('invite-email').value='';await load()}catch(e){toast(e.message)}}async function resend(email,role){try{const d=await api('/api/saas/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,role})});toast(d.email_delivered?'A fresh invitation was sent.':'A fresh invitation was created, but email delivery is not configured.');await load()}catch(e){toast(e.message)}}async function saveRole(id){try{const role=$('role-'+id).value,d=await api('/api/workspace/members/'+id+'/role',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});toast(d.message);await load()}catch(e){toast(e.message)}}async function removeUser(id,email){if(!confirm('Remove '+email+' from this workspace?'))return;try{await api('/api/saas/members/'+id,{method:'DELETE'});toast('Access removed.');await load()}catch(e){toast(e.message)}}load().catch(e=>toast(e.message));
</script><script>
function showInviteOutcome(d){const box=$('invite-result');box.hidden=false;box.replaceChildren();const message=document.createElement('div');message.textContent=d.message||(d.email_delivered?'Invitation sent by email.':'Invitation created.');box.appendChild(message);if(!d.email_delivered&&d.accept_url){const hint=document.createElement('div');hint.className='hint';hint.textContent='Email delivery is unavailable. Share this seven-day link directly with the invited person.';const actions=document.createElement('div');actions.className='actions';actions.style.marginTop='9px';const open=document.createElement('a');open.href=d.accept_url;open.target='_blank';open.rel='noopener noreferrer';open.textContent='Open secure link';open.style.color='#9cecff';const copy=document.createElement('button');copy.type='button';copy.textContent='Copy link';copy.onclick=async()=>{try{await navigator.clipboard.writeText(d.accept_url);toast('Secure invitation link copied.')}catch(e){toast('Open the secure link and copy it from your browser.')}};actions.append(open,copy);box.append(hint,actions)}}
sendInvite=async function(){const email=$('invite-email').value.trim(),role=$('invite-role').value;if(!email)return toast('Enter an email address.');try{const d=await api('/api/saas/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,role})});showInviteOutcome(d);toast(d.email_delivered?'Invitation sent.':'Invitation created. Copy the secure link below.');$('invite-email').value='';await load()}catch(e){toast(e.message)}};
resend=async function(email,role){try{const d=await api('/api/saas/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,role})});showInviteOutcome(d);toast(d.email_delivered?'A fresh invitation was sent.':'A fresh invitation was created. Copy the secure link below.');await load()}catch(e){toast(e.message)}};
</script></body></html>'''

    app.register_blueprint(bp)
    return bp
