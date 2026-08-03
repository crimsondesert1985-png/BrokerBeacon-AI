"""Customer-ready language and interaction polish for BrokerBeacon.

This layer keeps customer-facing pages conversational, simple, and useful
without exposing implementation details. Advanced controls remain role-aware.
"""
from __future__ import annotations

from flask import g, jsonify


COPY_RULES = {
    "Run cycle": "Find new opportunities",
    "Execute cycle": "Find new opportunities",
    "Launch hunt": "Start prospect search",
    "Submit command": "Send",
    "Execute": "Continue",
    "Payload": "Details",
    "Parameters": "Options",
    "Configuration": "Settings",
    "Autonomy policy": "Automation settings",
    "Agent status": "AI team status",
    "Pending review": "Ready for your review",
    "No data": "Nothing here yet",
    "Invalid request": "I couldn't complete that yet",
    "Internal server error": "Something went wrong on our side",
}

HUMAN_MESSAGES = {
    "loading": "I'm working on that now…",
    "success": "Done — you're ready for the next step.",
    "empty": "Nothing needs your attention here yet.",
    "retry": "That didn't work this time. Try again, or come back in a moment.",
    "offline": "I can't reach BrokerBeacon right now. Your work is still safe.",
}


def install_customer_ready_ux(app):
    @app.get("/api/customer-ready/experience")
    def customer_ready_experience():
        return jsonify(
            principles=[
                "Use plain English",
                "Show one obvious next step",
                "Hide technical details unless they are needed",
                "Respond like a capable person",
                "Celebrate meaningful progress",
            ],
            messages=HUMAN_MESSAGES,
        )

    @app.after_request
    def apply_customer_ready_experience(response):
        if response.status_code != 200:
            return response
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-customer-ready" in body or "</body>" not in body.lower():
            return response

        is_owner = bool(getattr(g, "is_platform_owner", False))
        replacements = repr(COPY_RULES)
        messages = repr(HUMAN_MESSAGES)
        script = f'''<style id="brokerbeacon-customer-ready">
        :root{{--bb-focus:#5f7cff;--bb-success:#20c997}}
        button,input,textarea,select{{font:inherit}}
        button{{transition:transform .15s ease,box-shadow .15s ease,opacity .15s ease}}
        button:hover{{transform:translateY(-1px)}}
        button:active{{transform:translateY(0)}}
        button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{{outline:3px solid color-mix(in srgb,var(--bb-focus) 45%,transparent);outline-offset:2px}}
        [data-bb-primary="true"]{{box-shadow:0 8px 24px rgba(95,124,255,.22)}}
        .bb-human-status{{font-size:13px;line-height:1.4;opacity:.82;margin-top:8px}}
        .bb-success-pulse{{animation:bbPulse .45s ease}}
        @keyframes bbPulse{{0%{{transform:scale(.98);opacity:.6}}100%{{transform:scale(1);opacity:1}}}}
        @media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
        </style><script>(function(){{
        const rules={replacements};const messages={messages};
        const normalize=s=>(s||'').replace(/\s+/g,' ').trim();
        function humanizeText(node){{
          if(!node||node.nodeType!==3)return;
          const original=node.nodeValue;let next=original;
          for(const [from,to] of Object.entries(rules)){{
            if(normalize(original).toLowerCase()===from.toLowerCase()){{next=original.replace(normalize(original),to);break}}
          }}
          if(next!==original)node.nodeValue=next;
        }}
        function improveControls(){{
          document.querySelectorAll('button,a,label,h1,h2,h3,h4,th,option').forEach(el=>{{
            [...el.childNodes].forEach(humanizeText);
          }});
          document.querySelectorAll('textarea').forEach(el=>{{
            if(!el.placeholder||/command|payload|json|input/i.test(el.placeholder))el.placeholder='Tell BrokerBeacon what you need in your own words…';
            if(!el.getAttribute('aria-label'))el.setAttribute('aria-label','Tell BrokerBeacon what you need');
          }});
          document.querySelectorAll('input[type="text"],input:not([type])').forEach(el=>{{
            if(!el.placeholder&&/search|prompt|query/i.test((el.name||'')+' '+(el.id||'')))el.placeholder='What are you looking for?';
          }});
          const visibleButtons=[...document.querySelectorAll('main button,section button,form button')].filter(b=>b.offsetParent!==null&&!b.disabled);
          if(visibleButtons.length)visibleButtons[0].dataset.bbPrimary='true';
          document.querySelectorAll('[data-loading-text]').forEach(el=>{{el.dataset.loadingText=messages.loading}});
          document.querySelectorAll('pre,code').forEach(el=>{{
            if(!{str(is_owner).lower()} && el.closest('main,section')){{
              const text=el.textContent||'';
              if(/^\s*[{{[]/.test(text)&&text.length>80)el.style.display='none';
            }}
          }});
        }}
        function watchForms(){{
          document.addEventListener('submit',e=>{{
            const form=e.target;if(!(form instanceof HTMLFormElement))return;
            let status=form.querySelector('.bb-human-status');
            if(!status){{status=document.createElement('div');status.className='bb-human-status';status.setAttribute('role','status');form.appendChild(status)}}
            status.textContent=messages.loading;
          }},true);
          document.addEventListener('bb:success',e=>{{
            const target=e.target instanceof Element?e.target:document.body;
            let status=target.querySelector?.('.bb-human-status');
            if(status){{status.textContent=messages.success;status.classList.add('bb-success-pulse')}}
          }});
        }}
        function run(){{improveControls();watchForms();}}
        if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();
        new MutationObserver(improveControls).observe(document.documentElement,{{childList:true,subtree:true}});
        }})();</script>'''
        pos = body.lower().rfind("</body>")
        body = body[:pos] + script + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app


__all__ = ["install_customer_ready_ux", "COPY_RULES", "HUMAN_MESSAGES"]
