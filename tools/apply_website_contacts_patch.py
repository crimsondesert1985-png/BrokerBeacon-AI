#!/usr/bin/env python3
"""Fix Review company website: open site + actually scrape contacts."""
from pathlib import Path

APP = Path("BrokerBeacon_AI_Phase2/app.py")

def main() -> int:
    text = APP.read_text()
    changed = False

    # 1) Fix parameter shadowing: page body was named `html`, so html.unescape failed.
    old_disc = "def _discover_contacts(html,url):\n    out=[]; plain=re.sub(r'<[^>]+>',' ',html.unescape(html)); plain=re.sub(r'\\s+',' ',plain)"
    new_disc = "def _discover_contacts(page_html,url):\n    out=[]; plain=re.sub(r'<[^>]+>',' ',html.unescape(page_html)); plain=re.sub(r'\\s+',' ',plain)"
    if old_disc in text:
        text = text.replace(old_disc, new_disc, 1)
        text = text.replace(
            "for block in re.findall(r'<script[^>]+type=[\"\\']application/ld\\+json[\"\\'][^>]*>(.*?)</script>',html,re.I|re.S):\n        try:\n            data=json.loads(html.unescape(block))",
            "for block in re.findall(r'<script[^>]+type=[\"\\']application/ld\\+json[\"\\'][^>]*>(.*?)</script>',page_html,re.I|re.S):\n        try:\n            data=json.loads(html.unescape(block))",
            1,
        )
        changed = True
        print("fixed _discover_contacts shadowing")
    elif "def _discover_contacts(page_html,url)" in text:
        print("discover already fixed")
    else:
        old2 = "def _discover_contacts(html,url):\n    out=[]; plain=re.sub(r'<[^>]+>',' ',html_lib.unescape(html)); plain=re.sub(r'\\s+',' ',plain)"
        if old2 in text:
            text = text.replace(old2, new_disc, 1)
            text = text.replace("html_lib.unescape", "html.unescape")
            changed = True
            print("fixed html_lib + shadowing")
        else:
            print("WARNING: discover signature not matched")

    # 2) Expand team/contact paths
    old_paths = "paths=['','/team','/about','/about-us','/our-team','/loan-officers','/meet-the-team']"
    new_paths = "paths=['','/team','/about','/about-us','/our-team','/loan-officers','/meet-the-team','/contact','/contact-us','/staff','/people','/our-staff']"
    if old_paths in text:
        text = text.replace(old_paths, new_paths, 1)
        changed = True
        print("expanded paths")

    # 3) Return website from refresh endpoint for UI to open
    old_return = 'return jsonify(message=f"Checked {len(checked)} official company page(s), imported {imported} contact(s), staged {len(rows)} item(s) for review.",candidates=rows,contacts=contacts,imported=imported)'
    new_return = (
        'website=(p["website"] or p["source_url"] or "")\n'
        '    if website and "://" not in website: website="https://"+website\n'
        '    return jsonify(message=f"Checked {len(checked)} official company page(s), imported {imported} contact(s), staged {len(rows)} item(s) for review.",'
        'candidates=rows,contacts=contacts,imported=imported,website=website,checked=checked)'
    )
    if old_return in text and 'website=website,checked=checked' not in text:
        text = text.replace(old_return, new_return, 1)
        changed = True
        print("return website in API")
    elif 'website=website,checked=checked' in text:
        print("API website already returned")
    else:
        old_return2 = 'return jsonify(message=f"Checked {len(checked)} official company page(s) and staged {len(rows)} unapproved discovery item(s).",candidates=rows)'
        if old_return2 in text:
            text = text.replace(old_return2, new_return, 1)
            changed = True
            print("return website (legacy message)")
        else:
            print("WARNING: return marker not found")

    # 4) JS: open company website in new window, then scrape
    new_js = (
        "$('#refreshRoster').onclick=async()=>{if(!current)return;"
        "let site=(current.website||current.source_url||'').trim();"
        "if(site){if(!/^https?:\\/\\//i.test(site))site='https://'+site;"
        "try{window.open(site,'_blank','noopener,noreferrer')}catch(e){}}"
        "$('#refreshRoster').disabled=true;$('#refreshRoster').textContent='Checking website...';"
        "try{let r=await api('/api/prospects/'+current.id+'/refresh-contacts',{method:'POST'});"
        "if(r.website){current.website=r.website;if(!site){try{window.open(r.website,'_blank','noopener,noreferrer')}catch(e){}}}"
        "if(r.contacts){current.contacts=r.contacts;renderContacts(r.contacts)}"
        "renderCandidates(r.candidates||[]);"
        "msg(r.message||'Website review complete')}"
        "catch(e){msg(e.message||'Website review failed')}"
        "finally{$('#refreshRoster').disabled=false;$('#refreshRoster').textContent='Review company website'}};
"
    )
    if "window.open(site,'_blank'" in text:
        print("window.open already present")
    else:
        key = "$('#refreshRoster').onclick=async()=>{if(!current)return;"
        idx = text.find(key)
        if idx >= 0:
            end = text.find("$('#clearContact').onclick", idx)
            if end > idx:
                text = text[:idx] + new_js + text[end:]
                changed = True
                print("wired window.open via slice replace")
            else:
                print("WARNING: could not find clearContact after refreshRoster")
        else:
            print("WARNING: refreshRoster handler not found")

    if not changed:
        print("no changes")
        return 0
    APP.write_text(text)
    print("patched", APP.stat().st_size)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
