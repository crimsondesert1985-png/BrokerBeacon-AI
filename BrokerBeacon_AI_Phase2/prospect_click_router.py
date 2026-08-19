"""Force prospect clicks to open the contact-first Prospect Detail page."""
from flask import g


PROSPECT_CLICK_ROUTER = r'''<script id="brokerbeacon-prospect-click-router">(function(){
if(/^\/prospects\/\d+\/(?:intelligence-report|contact-prep)\/?$/i.test(location.pathname))return;
function route(id){if(!id)return;location.href='/prospects/'+id+'/intelligence-report'}
function idFromHref(href){const m=String(href||'').match(/^\/prospects?\/(\d+)(?:\/(?:intelligence-report|contact-prep))?\/?(?:[?#].*)?$/i);return m&&m[1]}
function idFor(el){if(!el)return'';const marked=el.closest&&el.closest('[data-prospect-id]');if(marked&&marked.getAttribute('data-prospect-id'))return marked.getAttribute('data-prospect-id');const anchor=(el.closest&&el.closest('a[href]'))||(el.querySelector&&el.querySelector('a[href*="/prospect"]'));if(anchor)return idFromHref(anchor.getAttribute('href'));const container=el.closest&&el.closest('tr,.card,.priority-card,.production-company,.person-card');if(container){const a=container.querySelector('a[href]');if(a)return idFromHref(a.getAttribute('href'))}return''}
function wire(){document.querySelectorAll('[data-prospect-id]').forEach(el=>{const id=el.getAttribute('data-prospect-id');if(!id)return;el.style.cursor='pointer';el.title='Open loan officer contact details'});document.querySelectorAll('a[href]').forEach(a=>{const id=idFromHref(a.getAttribute('href'));if(id){a.setAttribute('href','/prospects/'+id+'/intelligence-report');a.title='Open loan officer contact details'}})}
document.addEventListener('click',function(ev){if(ev.button!==0||ev.metaKey||ev.ctrlKey||ev.shiftKey||ev.altKey)return;const target=ev.target;if(target.closest('input,select,textarea,[contenteditable="true"]'))return;const id=idFor(target);if(!id)return;const link=target.closest('a[href]');if(link){const href=link.getAttribute('href')||'';if(/^mailto:|^tel:|^https?:\/\//i.test(href))return}ev.preventDefault();ev.stopPropagation();ev.stopImmediatePropagation();route(id)},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''


def install_prospect_click_router(app):
    @app.after_request
    def force_contact_first_prospect_navigation(response):
        if not getattr(g, "user_id", None):
            return response
        if response.status_code != 200 or "text/html" not in response.headers.get("Content-Type", "").lower():
            return response
        try:
            body = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "brokerbeacon-prospect-click-router" in body or "</body>" not in body.lower():
            return response
        pos = body.lower().rfind("</body>")
        body = body[:pos] + PROSPECT_CLICK_ROUTER + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    app.logger.warning("PROSPECT_CLICK_ROUTER installed direct contact-first prospect navigation")
    return app


__all__ = ["install_prospect_click_router"]
