"""Route prospect clicks into BrokerBeacon's existing full prospect profile UI."""
from flask import g


PROSPECT_CLICK_ROUTER = r'''<style id="brokerbeacon-prospect-intelligence-button-style">.bb-intelligence-btn{display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:7px 10px;border:1px solid #a9bfe2;border-radius:9px;background:#315fe3!important;color:#fff!important;font:inherit;font-size:11px;font-weight:850;text-decoration:none;cursor:pointer;white-space:nowrap}.bb-intelligence-btn:hover{filter:brightness(.96)}td .bb-intelligence-btn{margin-left:5px}.bb-intelligence-card-action{margin-top:9px}</style><script id="brokerbeacon-prospect-click-router">(function(){
function openExistingProfileFromQuery(){if(location.pathname!='/')return false;const id=new URLSearchParams(location.search).get('prospect');if(!id)return false;let tries=0;const timer=setInterval(function(){tries++;if(typeof window.profile==='function'){clearInterval(timer);window.profile(Number(id));history.replaceState(null,'','/');return}if(tries>60)clearInterval(timer)},100);return true}
openExistingProfileFromQuery();
function route(id){if(!id)return;location.href='/?prospect='+encodeURIComponent(id)}
function idFromHref(href){const value=String(href||'');let m=value.match(/^\/prospects?\/(\d+)(?:\/(?:intelligence-report|contact-prep))?\/?(?:[?#].*)?$/i);if(m)return m[1];m=value.match(/^\/?\?prospect=(\d+)(?:&.*)?$/i);return m&&m[1]}
function idFromInline(el){if(!el)return'';const own=el.getAttribute&&el.getAttribute('onclick');let m=String(own||'').match(/profile\((\d+)\)/i);if(m)return m[1];const child=el.querySelector&&el.querySelector('[onclick*="profile("]');if(child){m=String(child.getAttribute('onclick')||'').match(/profile\((\d+)\)/i);if(m)return m[1]}return''}
function idFor(el){if(!el)return'';const marked=el.closest&&el.closest('[data-prospect-id]');if(marked&&marked.getAttribute('data-prospect-id'))return marked.getAttribute('data-prospect-id');const anchor=(el.closest&&el.closest('a[href]'))||(el.querySelector&&el.querySelector('a[href*="/prospect"]'));if(anchor){const id=idFromHref(anchor.getAttribute('href'));if(id)return id}const container=el.closest&&el.closest('tr,.card,.priority-card,.production-company');if(container){const id=idFromInline(container);if(id)return id;const a=container.querySelector('a[href]');if(a)return idFromHref(a.getAttribute('href'))}return idFromInline(el)}
function addIntelligenceButton(container,id){if(!container||!id||container.querySelector('.bb-intelligence-btn'))return;const b=document.createElement('button');b.type='button';b.className='bb-intelligence-btn';b.textContent='Intelligence';b.title='Open full prospect intelligence and contacts';b.dataset.prospectId=id;b.addEventListener('click',function(ev){ev.preventDefault();ev.stopPropagation();ev.stopImmediatePropagation();route(id)},true);if(container.matches('tr')){let cell=container.lastElementChild;if(!cell||cell.tagName!=='TD'){cell=document.createElement('td');container.appendChild(cell)}cell.appendChild(b)}else{b.classList.add('bb-intelligence-card-action');container.appendChild(b)}}
function prospectContainers(){const set=new Set;document.querySelectorAll('[data-prospect-id]').forEach(el=>set.add(el.closest('tr,.card,.priority-card')||el));document.querySelectorAll('[onclick*="profile("]').forEach(el=>set.add(el.closest('tr,.card,.priority-card')||el));document.querySelectorAll('a[href*="/prospect"]').forEach(a=>{const id=idFromHref(a.getAttribute('href'));if(id)set.add(a.closest('tr,.card,.priority-card')||a)});return [...set].filter(Boolean)}
function wire(){document.querySelectorAll('[data-prospect-id]').forEach(el=>{const id=el.getAttribute('data-prospect-id');if(!id)return;el.style.cursor='pointer';el.title='Open full prospect profile'});document.querySelectorAll('a[href]').forEach(a=>{const id=idFromHref(a.getAttribute('href'));if(id){a.setAttribute('href','/?prospect='+encodeURIComponent(id));a.title='Open full prospect profile'}});prospectContainers().forEach(el=>{if(el.closest('#profile,#bb-prospect-drawer,#bbac-modal'))return;const id=idFor(el);if(id)addIntelligenceButton(el,id)})}
document.addEventListener('click',function(ev){if(ev.button!==0||ev.metaKey||ev.ctrlKey||ev.shiftKey||ev.altKey)return;const target=ev.target;if(target.closest('.bb-intelligence-btn,input,select,textarea,[contenteditable="true"]'))return;const id=idFor(target);if(!id)return;const link=target.closest('a[href]');if(link){const href=link.getAttribute('href')||'';if(/^mailto:|^tel:|^https?:\/\//i.test(href))return}ev.preventDefault();ev.stopPropagation();ev.stopImmediatePropagation();route(id)},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire);else wire();new MutationObserver(wire).observe(document.documentElement,{childList:true,subtree:true});
})();</script>'''


def install_prospect_click_router(app):
    @app.after_request
    def force_existing_profile_navigation(response):
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

    app.logger.warning("PROSPECT_CLICK_ROUTER installed intelligence buttons and existing profile navigation")
    return app


__all__ = ["install_prospect_click_router"]
