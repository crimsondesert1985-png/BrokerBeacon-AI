#!/usr/bin/env python3
"""Minimal Intelligence website-contact fixes for app.py."""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "BrokerBeacon_AI_Phase2" / "app.py"


def main() -> int:
    text = APP.read_text()
    changed = False

    # 1) Critical bug: html_lib is undefined (module is imported as html).
    if "html_lib.unescape" in text:
        text = text.replace("html_lib.unescape", "html.unescape")
        changed = True
        print("fixed html_lib -> html")

    # 2) Expand page paths for team/contact discovery.
    old_paths = "paths=['','/team','/about','/about-us','/our-team','/loan-officers','/meet-the-team']"
    new_paths = (
        "paths=['','/team','/about','/about-us','/our-team','/loan-officers',"
        "'/meet-the-team','/contact','/contact-us','/staff','/people']"
    )
    if old_paths in text:
        text = text.replace(old_paths, new_paths, 1)
        changed = True
        print("expanded official page paths")

    # 3) After staging candidates, also promote named discoveries into contacts.
    marker = (
        "c.execute(\"insert into contact_candidates(prospect_id,name,role,email,phone,source_url,raw_context,status,created_at) "
        "values(?,?,?,?,?,?,?,'Pending',?)",(pid,x.get('name',''),x.get('role',''),x.get('email',''),x.get('phone',''),"
        "x.get('source_url',''),x.get('raw_context',''),NOW()))\n"
        "        rows=[dict(x) for x in c.execute(\"select * from contact_candidates where prospect_id=? and status='Pending' order by id desc\",(pid,))]\n"
        "    return jsonify(message=f\"Checked {len(checked)} official company page(s) and staged {len(rows)} unapproved discovery item(s).\",candidates=rows)"
    )
    promotion = (
        "c.execute(\"insert into contact_candidates(prospect_id,name,role,email,phone,source_url,raw_context,status,created_at) values(?,?,?,?,?,?,?,'Pending',?)\",(pid,x.get('name',''),x.get('role',''),x.get('email',''),x.get('phone',''),x.get('source_url',''),x.get('raw_context',''),NOW()))\n"
        "        # Auto-promote named people found on the company website into the live roster.\n"
        "        imported=0\n"
        "        for x in discoveries:\n"
        "            name=(x.get('name') or '').strip()\n"
        "            email=(x.get('email') or '').strip()\n"
        "            phone=(x.get('phone') or '').strip()\n"
        "            if not name:\n"
        "                continue\n"
        "            exists=c.execute(\n"
        "                \"select id from contacts where prospect_id=? and lower(trim(coalesce(name,'')))=lower(?) limit 1\",\n"
        "                (pid, name),\n"
        "            ).fetchone()\n"
        "            if exists:\n"
        "                continue\n"
        "            role=(x.get('role') or 'Loan Officer').strip() or 'Loan Officer'\n"
        "            is_decision=1 if re.search(r'owner|manager|broker|principal|president|founder', role, re.I) else 0\n"
        "            c.execute(\n"
        "                \"insert into contacts(prospect_id,name,role,email,phone,mobile,nmls,specialties,languages,office_location,preferred_method,linkedin_url,source_url,verified_at,roster_status,notes,is_primary,is_decision_maker,sms_consent,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\",\n"
        "                (pid,name,role,email,phone,'','','','','','','',x.get('source_url',''),datetime.now().date().isoformat(),'Publicly verified',x.get('raw_context') or 'Imported from company website',1 if imported==0 else 0,is_decision,0,NOW(),NOW()),\n"
        "            )\n"
        "            imported+=1\n"
        "        if imported:\n"
        "            primary=c.execute(\"select name,email,phone,mobile from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,id limit 1\",(pid,)).fetchone()\n"
        "            if primary and primary['name']:\n"
        "                c.execute(\"update prospects set owner=?,email=coalesce(nullif(?,''),email),phone=coalesce(nullif(?,''),phone),updated_at=? where id=?\",(primary['name'],primary['email'] or '',primary['mobile'] or primary['phone'] or '',NOW(),pid))\n"
        "        rows=[dict(x) for x in c.execute(\"select * from contact_candidates where prospect_id=? and status='Pending' order by id desc\",(pid,))]\n"
        "        contacts=[dict(x) for x in c.execute(\"select * from contacts where prospect_id=? order by is_primary desc,is_decision_maker desc,name\",(pid,))]\n"
        "    return jsonify(message=f\"Checked {len(checked)} official company page(s), imported {imported} contact(s), staged {len(rows)} item(s) for review.\",candidates=rows,contacts=contacts,imported=imported)"
    )

    if "Auto-promote named people found on the company website" not in text:
        if marker not in text:
            raise SystemExit("REFRESH_LOOP_MARKER_NOT_FOUND")
        text = text.replace(marker, promotion, 1)
        changed = True
        print("auto-promote named website contacts")

    # 4) UI: refresh roster after website review.
    old_js = (
        "try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});"
        "renderCandidates(r.candidates||[]);msg(r.message)}"
    )
    new_js = (
        "try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});"
        "if(r.contacts){current.contacts=r.contacts;renderContacts(r.contacts)}"
        "renderCandidates(r.candidates||[]);msg(r.message||'Website review complete')}"
    )
    if old_js in text and "if(r.contacts)" not in text:
        text = text.replace(old_js, new_js, 1)
        changed = True
        print("wired contacts refresh in UI")

    # 5) Auto-run website review when Intelligence opens a company with no named contacts.
    old_profile = (
        "async function profile(id){let p=await api('/api/prospects/'+id);current=p;updateAshContext();"
        "renderContacts(p.contacts||[]);clearContactForm();loadCandidates();"
    )
    new_profile = (
        "async function profile(id){let p=await api('/api/prospects/'+id);current=p;updateAshContext();"
        "renderContacts(p.contacts||[]);clearContactForm();loadCandidates();"
        "(function(){const named=(p.contacts||[]).filter(c=>c.name&&c.name!=='Company Contact Desk');"
        "if(!named.length)setTimeout(()=>{if(current&&current.id===p.id&&$('#refreshRoster'))$('#refreshRoster').click()},500)})();"
    )
    if old_profile in text and "if(!named.length)" not in text:
        text = text.replace(old_profile, new_profile, 1)
        changed = True
        print("auto website review on empty Intelligence roster")

    if not changed:
        print("no changes needed")
        return 0

    APP.write_text(text)
    print("patched", APP, "size", APP.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
