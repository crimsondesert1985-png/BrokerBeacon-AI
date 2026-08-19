"""Safe prospect routing for the main BrokerBeacon Prospects workspace.

This module intentionally scopes all dynamic behavior to the #rows prospect table.
It restores a visible Intelligence action on every prospect, makes a normal row
click open the existing full prospect profile, and defaults that profile to the
Contacts tab so users land on the loan-officer directory immediately.
"""
from flask import g


PROSPECT_CLICK_ROUTER = r'''<style id="brokerbeacon-prospect-intelligence-style">
#rows .bb-intelligence-btn{display:inline-flex;align-items:center;justify-content:center;margin-left:6px;padding:7px 10px;border:1px solid #6f93d8;border-radius:9px;background:#315fe3;color:#fff!important;font:inherit;font-size:11px;font-weight:850;line-height:1;text-decoration:none;cursor:pointer;white-space:nowrap;box-shadow:0 2px 7px #315fe326}
#rows .bb-intelligence-btn:hover{filter:brightness(.96);transform:translateY(-1px)}
#rows tr.bb-prospect-row{cursor:pointer}
#rows tr.bb-prospect-row:hover{background:#315fe308}
</style><script id="brokerbeacon-prospect-click-router">(function(){
if(location.pathname!=='/')return;

function contactsTab(){
  const profile=document.getElementById('profile');
  if(!profile||!profile.open)return;
  const tab=profile.querySelector('[data-tab="contacts"]');
  if(tab)tab.click();
}

async function openProspect(id){
  id=Number(id||0);
  if(!id||typeof window.profile!=='function')return;
  try{
    await window.profile(id);
    setTimeout(contactsTab,0);
  }catch(e){
    console.warn('Prospect profile open failed',e);
  }
}

function prospectIdForRow(row,index){
  const direct=row&&row.getAttribute('data-prospect-id');
  if(direct)return Number(direct);
  const btn=row&&row.querySelector('[onclick*="profile("]');
  if(btn){
    const m=String(btn.getAttribute('onclick')||'').match(/profile\((\d+)\)/i);
    if(m)return Number(m[1]);
  }
  if(Array.isArray(window.P)&&window.P[index]&&window.P[index].id)return Number(window.P[index].id);
  return 0;
}

function decorateRows(){
  const body=document.getElementById('rows');
  if(!body)return;
  const rows=Array.from(body.querySelectorAll(':scope > tr'));
  rows.forEach(function(row,index){
    const id=prospectIdForRow(row,index);
    if(!id)return;
    row.classList.add('bb-prospect-row');
    row.dataset.prospectId=String(id);
    row.title='Open prospect contacts and intelligence';

    if(row.querySelector('.bb-intelligence-btn'))return;
    const contactActions=row.querySelector('.contact-actions');
    const target=contactActions||row.lastElementChild;
    if(!target)return;
    const button=document.createElement('button');
    button.type='button';
    button.className='bb-intelligence-btn';
    button.textContent='Intelligence';
    button.setAttribute('aria-label','Open prospect intelligence and contacts');
    button.addEventListener('click',function(ev){
      ev.preventDefault();
      ev.stopPropagation();
      openProspect(id);
    });
    target.appendChild(button);
  });
}

function installProspectTable(){
  const body=document.getElementById('rows');
  if(!body)return false;
  decorateRows();

  body.addEventListener('click',function(ev){
    if(ev.target.closest('a,button,input,select,textarea,[contenteditable="true"]'))return;
    const row=ev.target.closest('tr[data-prospect-id]');
    if(!row||!body.contains(row))return;
    openProspect(row.dataset.prospectId);
  });

  // Observe only the prospect tbody. load() replaces these rows after filters/search.
  // This is deliberately not a document-wide observer, which previously caused freezes.
  const observer=new MutationObserver(function(records){
    if(records.some(function(r){return r.type==='childList'}))decorateRows();
  });
  observer.observe(body,{childList:true});
  return true;
}

function openDeepLink(){
  const id=new URLSearchParams(location.search).get('prospect');
  if(!id)return;
  let tries=0;
  const timer=setInterval(function(){
    tries++;
    if(typeof window.profile==='function'){
      clearInterval(timer);
      openProspect(id);
      history.replaceState(null,'','/');
    }else if(tries>=30){
      clearInterval(timer);
    }
  },100);
}

function boot(){
  openDeepLink();
  let tries=0;
  const timer=setInterval(function(){
    tries++;
    if(installProspectTable()||tries>=30)clearInterval(timer);
  },100);
}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
else boot();
})();</script>'''


def install_prospect_click_router(app):
    @app.after_request
    def add_safe_prospect_navigation(response):
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

    app.logger.warning("PROSPECT_CLICK_ROUTER installed safe prospect Intelligence actions")
    return app


__all__ = ["install_prospect_click_router"]
