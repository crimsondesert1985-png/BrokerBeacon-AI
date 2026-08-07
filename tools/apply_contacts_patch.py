#!/usr/bin/env python3
"""Apply contacts enrichment to /api/prospects so the light Ash shell shows real loan-officer names."""
from pathlib import Path

path = Path("BrokerBeacon_AI_Phase2/app.py")
text = path.read_text()

if "contact_map={}" in text and "primary_contact_name" in text and "Prefer a named primary" in text:
    print("ALREADY_PATCHED")
    raise SystemExit(0)

new_block = '''@app.get("/api/prospects")
def prospects():
    q=request.args.get("search","").lower(); st=request.args.get("state","All"); sg=request.args.get("signal","All"); ps=request.args.get("status","All statuses")
    try: min_score=int(request.args.get("min_score",0))
    except ValueError: min_score=0
    with db() as c:
        rows=c.execute("select * from prospects order by score desc, company").fetchall()
        # Prefer a named primary/decision-maker contact so the directory never shows a blank owner when roster data exists.
        contact_map={}
        for r in c.execute("""
            select prospect_id, name, role, email, phone, mobile, is_primary, is_decision_maker
            from contacts
            where trim(coalesce(name,''))<>'' and lower(trim(name)) not in ('company contact desk','company contact')
            order by is_decision_maker desc, is_primary desc, id
        """):
            pid=int(r["prospect_id"])
            if pid not in contact_map:
                contact_map[pid]=dict(r)
        out=[]
        for x in rows:
            if not ((st=="All" or x["state"]==st) and (sg=="All" or x["signal"]==sg) and (ps=="All statuses" or x["status"]==ps) and int(x["score"] or 0)>=min_score and (not q or q in (x["company"]+" "+(x["owner"]or"")+" "+(x["city"]or"")).lower())):
                continue
            d=dict(x)
            primary=contact_map.get(int(d["id"]))
            if primary:
                d["primary_contact_name"]=primary["name"]
                d["primary_contact_role"]=primary.get("role") or ""
                if not (d.get("owner") or "").strip():
                    d["owner"]=primary["name"]
                if not (d.get("email") or "").strip() and primary.get("email"):
                    d["email"]=primary["email"]
                if not (d.get("phone") or "").strip():
                    d["phone"]=primary.get("mobile") or primary.get("phone") or d.get("phone") or ""
            else:
                d["primary_contact_name"]=d.get("owner") or ""
                d["primary_contact_role"]=""
            out.append(d)
    return jsonify(out)'''

# Marker-based replace: locate the prospects function by known start/end
lines = text.splitlines(keepends=True)
start = None
end = None
for i, line in enumerate(lines):
    if '@app.get("/api/prospects")' in line and start is None:
        start = i
    if start is not None and end is None and line.startswith("def _index_domain"):
        end = i
        break

if start is None or end is None:
    raise SystemExit("OLD_BLOCK_NOT_FOUND_MARKERS")

text = "".join(lines[:start]) + new_block + "\n\n" + "".join(lines[end:])

js_old = "esc(p.owner||(p.phone||p.email?(p.company||'Company')+' main office':'Contact research pending'))"
js_new = "esc(p.primary_contact_name||p.owner||(p.phone||p.email?(p.company||'Company')+' main office':'Contact research pending'))"
if js_old in text and "p.primary_contact_name||p.owner" not in text:
    text = text.replace(js_old, js_new, 1)

path.write_text(text)
print("PATCHED_OK")
