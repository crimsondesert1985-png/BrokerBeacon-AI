#!/usr/bin/env python3
from pathlib import Path
APP = Path("BrokerBeacon_AI_Phase2/app.py")

def main():
    t = APP.read_text()
    c = False
    a = "def _discover_contacts(html,url):\n    out=[]; plain=re.sub(r'<[^>]+>',' ',html.unescape(html)); plain=re.sub(r'\\s+',' ',plain)"
    b = "def _discover_contacts(page_html,url):\n    out=[]; plain=re.sub(r'<[^>]+>',' ',html.unescape(page_html)); plain=re.sub(r'\\s+',' ',plain)"
    if a in t:
        t = t.replace(a, b, 1)
        t = t.replace(",html,re.I|re.S):\n        try:\n            data=json.loads(html.unescape(block))", ",page_html,re.I|re.S):\n        try:\n            data=json.loads(html.unescape(block))", 1)
        c = True
        print("fixed shadow")
    old = "$('#refreshRoster').onclick=async()=>{if(!current)return;"
    if "window.open(site" not in t and old in t:
        i = t.find(old)
        j = t.find("$('#clearContact').onclick", i)
        js = (
            "$('#refreshRoster').onclick=async()=>{if(!current)return;"
            "let site=(current.website||current.source_url||'').trim();"
            "if(site){if(site.indexOf('://')<0)site='https://'+site;try{window.open(site,'_blank','noopener')}catch(e){}}"
            "$('#refreshRoster').disabled=true;$('#refreshRoster').textContent='Checking website...';"
            "try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});"
            "if(r.website&&!site){try{window.open(r.website,'_blank','noopener')}catch(e){}}"
            "if(r.contacts){current.contacts=r.contacts;renderContacts(r.contacts)}"
            "renderCandidates(r.candidates||[]);msg(r.message||'Website review complete')}"
            "catch(e){msg(e.message||'Website review failed')}"
            "finally{$('#refreshRoster').disabled=false;$('#refreshRoster').textContent='Review company website'}};"
        )
        t = t[:i] + js + t[j:]
        c = True
        print("wired open")
    ret = 'return jsonify(message=f"Checked {len(checked)} official company page(s), imported {imported} contact(s), staged {len(rows)} item(s) for review.",candidates=rows,contacts=contacts,imported=imported)'
    if ret in t and "website=website" not in t:
        t = t.replace(ret, 'website=(p["website"] or p["source_url"] or "")\n    if website and "://" not in str(website): website="https://"+str(website)\n    return jsonify(message=f"Checked {len(checked)} official company page(s), imported {imported} contact(s), staged {len(rows)} item(s) for review.",candidates=rows,contacts=contacts,imported=imported,website=website)', 1)
        c = True
        print("api website")
    if not c:
        print("no changes")
        return 0
    APP.write_text(t)
    print("ok", APP.stat().st_size)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
