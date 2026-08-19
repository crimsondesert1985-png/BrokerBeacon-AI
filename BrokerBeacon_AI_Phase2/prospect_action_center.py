"""Prospect action center: make every outreach tool one click away."""
from __future__ import annotations

import base64
import os
import urllib.parse
import urllib.request

from flask import g, jsonify, request


def _required_twilio_config():
    return {
        "account_sid": os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        "auth_token": os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
        "from_number": os.getenv("TWILIO_FROM_NUMBER", "").strip(),
        "agent_number": os.getenv("TWILIO_AGENT_NUMBER", "").strip(),
    }


def install_prospect_action_center(app):
    @app.get("/api/contact-center/provider-status")
    def contact_center_provider_status():
        if not getattr(g, "user_id", None):
            return jsonify(error="Authentication required"), 401
        cfg = _required_twilio_config()
        ready = all(cfg.values())
        return jsonify(
            call_provider="twilio",
            call_ready=ready,
            required_env=[
                "TWILIO_ACCOUNT_SID",
                "TWILIO_AUTH_TOKEN",
                "TWILIO_FROM_NUMBER",
                "TWILIO_AGENT_NUMBER",
            ],
        )

    @app.post("/api/contact-center/call")
    def contact_center_call():
        """User-triggered click-to-call framework.

        Once Twilio env vars are present, BrokerBeacon first calls the configured
        sales rep/agent number and then bridges that call to the selected loan
        officer. No background or automatic dialing is performed.
        """
        if not getattr(g, "user_id", None):
            return jsonify(error="Authentication required"), 401

        data = request.get_json(silent=True) or {}
        target = "".join(ch for ch in str(data.get("phone") or "") if ch.isdigit() or ch == "+")
        contact_name = str(data.get("contact_name") or "Loan officer").strip()[:160]
        if not target:
            return jsonify(error="A phone number is required"), 400

        cfg = _required_twilio_config()
        missing = [key for key, value in cfg.items() if not value]
        if missing:
            return jsonify(
                ok=False,
                configured=False,
                provider="twilio",
                message="Twilio calling is ready for credentials but is not configured yet.",
                missing=[
                    {
                        "account_sid": "TWILIO_ACCOUNT_SID",
                        "auth_token": "TWILIO_AUTH_TOKEN",
                        "from_number": "TWILIO_FROM_NUMBER",
                        "agent_number": "TWILIO_AGENT_NUMBER",
                    }[item]
                    for item in missing
                ],
            ), 503

        # Call the salesperson first; after they answer, Twilio dials the prospect.
        safe_target = target.replace("&", "").replace("<", "").replace(">", "")
        twiml = (
            '<Response><Dial callerId="{}">{}</Dial></Response>'.format(
                cfg["from_number"], safe_target
            )
        )
        form = urllib.parse.urlencode(
            {
                "To": cfg["agent_number"],
                "From": cfg["from_number"],
                "Twiml": twiml,
            }
        ).encode("utf-8")
        endpoint = "https://api.twilio.com/2010-04-01/Accounts/{}/Calls.json".format(cfg["account_sid"])
        req = urllib.request.Request(endpoint, data=form, method="POST")
        token = base64.b64encode((cfg["account_sid"] + ":" + cfg["auth_token"]).encode("utf-8")).decode("ascii")
        req.add_header("Authorization", "Basic " + token)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            app.logger.exception("CONTACT_CENTER Twilio call failed")
            return jsonify(error="Twilio call request failed", detail=str(exc)[:240]), 502

        app.logger.warning("CONTACT_CENTER user=%s initiated call to %s", getattr(g, "user_id", 0), contact_name)
        return jsonify(ok=True, configured=True, provider="twilio", contact_name=contact_name, provider_response=payload), 201

    @app.after_request
    def inject_prospect_action_center(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-prospect-action-center" in body or "</body>" not in body.lower():
            return response
        enhancement = ACTION_CENTER_SCRIPT
        pos = body.lower().rfind("</body>")
        body = body[:pos] + enhancement + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("PROSPECT_ACTION_CENTER installed contact-first tool access")
    return app


ACTION_CENTER_SCRIPT = r'''<style id="brokerbeacon-prospect-action-center-style">
#bb-action-center{margin:0 0 16px;padding:14px;border:1px solid #d8e4f2;border-radius:15px;background:#fff;box-shadow:0 8px 24px #17365f0c}.bbac-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}.bbac-title h2{margin:0;font-size:17px}.bbac-title small{color:#718197}.bbac-tools,.bbac-contact-tools{display:flex;flex-wrap:wrap;gap:7px}.bbac-tools button,.bbac-tools a,.bbac-contact-tools button,.bbac-contact-tools a{display:inline-flex;align-items:center;gap:5px;border:1px solid #d8e4f2;border-radius:9px;padding:8px 10px;background:#f8fbff;color:#1b3553;text-decoration:none;font:inherit;font-size:11px;font-weight:800;cursor:pointer}.bbac-tools .primary,.bbac-contact-tools .primary{background:#225be6;border-color:#225be6;color:#fff}.bbac-contact-tools{grid-column:1/-1;padding-top:9px;border-top:1px solid #edf1f6}.bbac-contact-tools button:hover,.bbac-tools button:hover,.bbac-tools a:hover,.bbac-contact-tools a:hover{filter:brightness(.98);border-color:#8eb4e5}.bbac-modal{position:fixed;inset:0;z-index:900;background:#06101fcc;display:none;align-items:center;justify-content:center;padding:20px}.bbac-modal.open{display:flex}.bbac-panel{width:min(720px,100%);max-height:88vh;overflow:auto;background:#fff;color:#17283d;border-radius:16px;padding:18px;box-shadow:0 30px 90px #0008}.bbac-panel h2{margin:0 0 6px}.bbac-panel textarea{width:100%;min-height:170px;border:1px solid #cfdcea;border-radius:10px;padding:12px;font:13px/1.5 Inter,Arial,sans-serif}.bbac-panel .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.bbac-panel button{border:1px solid #d8e4f2;background:#f7faff;border-radius:9px;padding:8px 10px;font-weight:800;cursor:pointer}.bbac-sequence{display:grid;gap:9px}.bbac-step{border:1px solid #dfe8f2;border-radius:11px;padding:10px;background:#f9fbfe}.bbac-step b{display:block;margin-bottom:5px}.bbac-status{margin-top:8px;font-size:11px;color:#65758b}@media(max-width:720px){#bb-action-center{margin-top:4px}.bbac-tools a,.bbac-tools button,.bbac-contact-tools a,.bbac-contact-tools button{flex:1 1 42%;justify-content:center}}
</style><div id="bbac-modal" class="bbac-modal"><div class="bbac-panel"><button id="bbac-close" style="float:right">Close</button><div id="bbac-content"></div></div></div><script id="brokerbeacon-prospect-action-center">(function(){
const path=location.pathname;const detail=/^\/prospects\/(\d+)\/intelligence-report\/?$/i.exec(path);if(!detail)return;const prospectId=detail[1];const company=(document.querySelector('h1')||{}).textContent?.trim()||'Prospect';
function tool(name){sessionStorage.setItem('bb-contact-prep-open-tool',name);location.href='/'}
function modal(title,html){const m=document.getElementById('bbac-modal'),c=document.getElementById('bbac-content');c.innerHTML='<h2>'+title+'</h2>'+html;m.classList.add('open')}document.getElementById('bbac-close').onclick=()=>document.getElementById('bbac-modal').classList.remove('open');
function selected(card){const name=(card.querySelector('.identity h2,.contact-head h2,h2')||{}).textContent?.trim()||'Loan officer';const phone=(card.querySelector('a[href^="tel:"]')||{}).getAttribute?.('href')?.replace(/^tel:/,'')||'';const email=(card.querySelector('a[href^="mailto:"]')||{}).getAttribute?.('href')?.replace(/^mailto:/,'')||'';return{name,phone,email}}
async function systemCall(p,btn){btn.disabled=true;const old=btn.textContent;btn.textContent='Starting call…';try{const r=await fetch('/api/contact-center/call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contact_name:p.name,phone:p.phone,prospect_id:prospectId})});const j=await r.json();if(!r.ok){modal('Call through BrokerBeacon','<p>'+((j&&j.message)||j.error||'Calling is not configured yet.')+'</p><div class="bbac-status">Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, and TWILIO_AGENT_NUMBER in Render. The framework will then call your agent number first and bridge to the loan officer.</div>');return}modal('Call started','<p>BrokerBeacon started a Twilio bridge call for <strong>'+p.name+'</strong>.</p>')}catch(e){modal('Call unavailable','<p>Unable to start the call right now.</p>')}finally{btn.disabled=false;btn.textContent=old}}
function draftEmail(p){const subject='Quick support for '+company;const body='Hi '+p.name+',\n\nI wanted to introduce myself and offer to be a resource for '+company+'. If you have a wholesale mortgage scenario that needs a second look, onboarding questions, or a file you are trying to place, I am happy to help work through the next step.\n\nIf useful, send over the basics of what you are working on and I will help think through the options.\n\nBest,\n[Your Name]';modal('Draft email · '+p.name,'<p><b>Subject:</b> '+subject+'</p><textarea id="bbac-draft">'+body.replace(/</g,'&lt;')+'</textarea><div class="row"><button id="bbac-copy">Copy draft</button>'+(p.email?'<a style="padding:8px 10px" href="mailto:'+encodeURIComponent(p.email)+'?subject='+encodeURIComponent(subject)+'&body='+encodeURIComponent(body)+'">Open email</a>':'')+'</div>');setTimeout(()=>{const b=document.getElementById('bbac-copy');if(b)b.onclick=async()=>{await navigator.clipboard.writeText(document.getElementById('bbac-draft').value);b.textContent='Copied'}},0)}
function drip(p){const steps=[['Day 0 · Email','Quick introduction and offer to help with a current wholesale scenario.'],['Day 3 · Email','Short follow-up with a specific offer to review a scenario or onboarding question.'],['Day 7 · SMS','Brief value-forward check-in, only if SMS consent is recorded.'],['Day 14 · Email','Final helpful touch with an invitation to send the next difficult file.']];sessionStorage.setItem('bb-drip-contact',JSON.stringify({prospect_id:prospectId,company,name:p.name,email:p.email,phone:p.phone}));modal('Draft drip · '+p.name,'<p>This is a draft framework only; sending still uses BrokerBeacon\'s approval and consent controls.</p><div class="bbac-sequence">'+steps.map(s=>'<div class="bbac-step"><b>'+s[0]+'</b>'+s[1]+'</div>').join('')+'</div><div class="row"><button id="bbac-open-drip">Open Drip Campaigns</button></div>');setTimeout(()=>{const b=document.getElementById('bbac-open-drip');if(b)b.onclick=()=>location.href='/outreach/campaigns'},0)}
function addTop(){const host=document.querySelector('.page,.wrap,main');if(!host||document.getElementById('bb-action-center'))return;const box=document.createElement('section');box.id='bb-action-center';box.innerHTML='<div class="bbac-title"><div><h2>Prospect Action Center</h2><small>Contact first. Every BrokerBeacon tool one click away.</small></div></div><div class="bbac-tools"><a class="primary" href="/prospects/'+prospectId+'/contact-prep">Contact Prep</a><a href="/outreach/campaigns">Drip Campaigns</a><button data-bbac-tool="notes">Notes</button><button data-bbac-tool="marketing">Marketing</button><button data-bbac-tool="sales coach">Sales Coach</button><button data-bbac-tool="opportunity">Opportunities</button><a href="/intelligence/scenario-rescue">BeaconMatch</a></div>';const anchor=host.querySelector('.account,.account-header,.hero')||host.firstElementChild;if(anchor&&anchor.nextSibling)host.insertBefore(box,anchor.nextSibling);else host.prepend(box);box.querySelectorAll('[data-bbac-tool]').forEach(b=>b.onclick=()=>tool(b.dataset.bbacTool))}
function addContacts(){document.querySelectorAll('.loan-officer,.contact-card').forEach(card=>{if(card.querySelector('.bbac-contact-tools'))return;const p=selected(card);const bar=document.createElement('div');bar.className='bbac-contact-tools';bar.innerHTML='<button class="primary" data-a="call">Call in BrokerBeacon</button>'+(p.email?'<a href="mailto:'+p.email+'">Email</a>':'')+'<button data-a="draft">Draft Email</button><button data-a="drip">Draft Drip</button><button data-a="text">Text Prep</button><button data-a="notes">Notes</button>';bar.querySelector('[data-a="call"]').onclick=e=>systemCall(p,e.currentTarget);bar.querySelector('[data-a="draft"]').onclick=()=>draftEmail(p);bar.querySelector('[data-a="drip"]').onclick=()=>drip(p);bar.querySelector('[data-a="text"]').onclick=()=>{const text='Hi '+p.name+', this is [Your Name] with [Lender]. Wanted to offer help with any wholesale mortgage scenarios or onboarding questions for '+company+'. Happy to be a resource.';modal('Text prep · '+p.name,'<textarea id="bbac-draft">'+text+'</textarea><div class="row"><button id="bbac-copy">Copy text</button></div>');setTimeout(()=>document.getElementById('bbac-copy').onclick=async()=>{await navigator.clipboard.writeText(text);document.getElementById('bbac-copy').textContent='Copied'},0)};bar.querySelector('[data-a="notes"]').onclick=()=>tool('notes');card.appendChild(bar)})}
function run(){addTop();addContacts()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();new MutationObserver(run).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''


__all__ = ["install_prospect_action_center"]
