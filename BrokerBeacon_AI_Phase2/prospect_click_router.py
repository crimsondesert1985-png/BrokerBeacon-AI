"""Lightweight prospect profile deep-link support.

Keep this intentionally small: the native Prospects table already renders its own
Intelligence button. Avoid global MutationObservers or document-wide click
interception because BrokerBeacon has several dynamic views that update the DOM
frequently.
"""
from flask import g


PROSPECT_CLICK_ROUTER = r'''<script id="brokerbeacon-prospect-click-router">(function(){
if(location.pathname!=='/')return;
const id=new URLSearchParams(location.search).get('prospect');
if(!id)return;
let tries=0;
const timer=setInterval(function(){
  tries++;
  if(typeof window.profile==='function'){
    clearInterval(timer);
    try{window.profile(Number(id));}catch(e){console.warn('Prospect profile open failed',e)}
    history.replaceState(null,'','/');
    return;
  }
  if(tries>=30)clearInterval(timer);
},100);
})();</script>'''


def install_prospect_click_router(app):
    @app.after_request
    def add_profile_deep_link_support(response):
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

    app.logger.warning("PROSPECT_CLICK_ROUTER installed lightweight profile deep links")
    return app


__all__ = ["install_prospect_click_router"]
