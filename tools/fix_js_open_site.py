#!/usr/bin/env python3
from pathlib import Path
APP = Path("BrokerBeacon_AI_Phase2/app.py")
def main():
    t = APP.read_text()
    c = False
    old_start = "$('#refreshRoster').onclick=async()=>{if(!current)return;"
    if old_start in t:
        i = t.find(old_start)
        j = t.find("$('#clearContact')", i)
        if j > i:
            js = """$('#refreshRoster').onclick=async()=>{if(!current)return;const openSite=u=>{if(!u)return;let s=String(u).trim();if(!s)return;if(s.indexOf('://')<0)s='https://'+s;try{const a=document.createElement('a');a.href=s;a.target='_blank';a.rel='noopener noreferrer';document.body.appendChild(a);a.click();a.remove();return true}catch(e){try{window.open(s,'_blank','noopener');return true}catch(e2){return false}}};let site=(current.website||current.source_url||'').trim();if(site)openSite(site);$('#refreshRoster').disabled=true;$('#refreshRoster').textContent='Checking website...';try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});const resolved=(r.website||'').trim()||site;if(r.website)current.website=r.website;if(resolved)openSite(resolved);if(r.contacts){current.contacts=r.contacts;renderContacts(r.contacts)}renderCandidates(r.candidates||[]);let note=r.message||'Website review complete';if(resolved)note+=' <a href="'+resolved.replace(/"/g,'')+'" target="_blank" rel="noopener">Open website</a>';msg(note)}catch(e){msg(e.message||'Website review failed')}finally{$('#refreshRoster').disabled=false;$('#refreshRoster').textContent='Review company website'}};"""
            t = t[:i] + js + t[j:]
            # Ensure clearContact is correct
            t = t.replace("$('#clearContact')('#clearContact')", "$('#clearContact')")
            c = True
            print("replaced refreshRoster handler with reliable openSite")
    if not c:
        print("no changes")
        return 0
    APP.write_text(t)
    print("ok", APP.stat().st_size)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
