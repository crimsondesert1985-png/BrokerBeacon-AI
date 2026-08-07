#!/usr/bin/env python3
from pathlib import Path
import re
APP = Path("BrokerBeacon_AI_Phase2/app.py")

def main():
    t = APP.read_text()
    if "toggleAshMic" in t and 'id="ashMic"' in t:
        print("voice UI already present")
        # still try intents
    else:
        old_css = ".ash-compose-row{display:grid;grid-template-columns:1fr auto;gap:8px}"
        new_css = old_css.replace("1fr auto", "1fr auto auto") + ".ash-mic{min-width:44px!important;height:44px!important;padding:0 12px!important;border-radius:12px!important}.ash-mic.listening{background:linear-gradient(135deg,#c62828,#8e0000)!important;color:#fff!important;border-color:transparent!important;animation:ashPulse 1.2s ease infinite}.ash-mic.speaking{background:linear-gradient(135deg,#1565c0,#0d47a1)!important;color:#fff!important}.ash-voice-status{font-size:11px;color:#5b6f8c;margin-top:6px;min-height:16px}.ash-voice-status.live{color:#c62828;font-weight:700}@keyframes ashPulse{0%,100%{box-shadow:0 0 0 0 rgba(198,40,40,.45)}50%{box-shadow:0 0 0 8px rgba(198,40,40,0)}}"
        if old_css in t and "ash-mic.listening" not in t:
            t = t.replace(old_css, new_css, 1)
            print("css ok")
        if 'id="ashMic"' not in t:
            m = re.search(r'(<textarea id="ashInput"[^>]*>.*?</textarea>)\s*(<button class="btn primary" id="ashSend")', t, re.S)
            if m:
                insert = m.group(1) + '<button class="btn ash-mic" id="ashMic" type="button" title="Talk to Ash" aria-label="Talk to Ash">🎤</button>' + m.group(2)
                t = t[:m.start()] + insert + t[m.end():]
                if 'id="ashVoiceStatus"' not in t:
                    t = t.replace('<div class="ash-footnote">Ash uses stored', '<div class="ash-voice-status" id="ashVoiceStatus"></div><div class="ash-footnote">Ash uses stored', 1)
                print("html ok")
        # Inject voice helpers before sendGlobalAsh if missing
        if "function toggleAshMic" not in t:
            marker = "async function sendGlobalAsh("
            idx = t.find(marker)
            if idx < 0:
                marker = "function sendGlobalAsh("
                idx = t.find(marker)
            if idx >= 0:
                helpers = (
                    "const ashVoice={rec:null,listening:false,speakReplies:true,continuous:false};"
                    "function ashSetVoiceStatus(txt,live){const el=$('#ashVoiceStatus');if(!el)return;el.textContent=txt||'';el.className='ash-voice-status'+(live?' live':'');}"
                    "function ashSpeak(text){if(!text||!('speechSynthesis' in window))return;try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(String(text).replace(/<[^>]+>/g,' ').slice(0,600));u.rate=1.02;u.pitch=1.05;const voices=speechSynthesis.getVoices()||[];const prefer=voices.find(v=>/female|samantha|joanna|karen|moira|zira|google us english/i.test(v.name))||voices.find(v=>/^en(-|_)/i.test(v.lang))||null;if(prefer)u.voice=prefer;const mic=$('#ashMic');u.onstart=()=>{if(mic)mic.classList.add('speaking');ashSetVoiceStatus('Ash is speaking…');};u.onend=()=>{if(mic)mic.classList.remove('speaking');ashSetVoiceStatus(ashVoice.listening?'Listening…':'');};speechSynthesis.speak(u);}catch(e){}}"
                    "function ashStopListening(){ashVoice.listening=false;try{if(ashVoice.rec)ashVoice.rec.stop()}catch(e){}const mic=$('#ashMic');if(mic){mic.classList.remove('listening');mic.textContent='🎤'}ashSetVoiceStatus('');}"
                    "function ashStartListening(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){msg('Voice needs Chrome, Edge, or Safari');return}if(ashVoice.listening){ashStopListening();return}try{speechSynthesis.cancel()}catch(e){}const rec=new SR();ashVoice.rec=rec;rec.lang='en-US';rec.interimResults=true;rec.maxAlternatives=1;let finalText='';rec.onstart=()=>{ashVoice.listening=true;const mic=$('#ashMic');if(mic){mic.classList.add('listening');mic.textContent='⏹'};ashSetVoiceStatus('Listening… speak now',true)};rec.onerror=e=>{ashStopListening()};rec.onend=()=>{const was=ashVoice.listening;ashVoice.listening=false;const mic=$('#ashMic');if(mic){mic.classList.remove('listening');mic.textContent='🎤'}if(was&&finalText.trim()){ashSetVoiceStatus('Got it — working…');$('#ashInput').value=finalText.trim();sendGlobalAsh();setTimeout(()=>{const ans=document.querySelectorAll('#ashChat .ash-msg.assistant');if(ans.length){const last=ans[ans.length-1];ashSpeak(last.innerText||'')}},1200)}else ashSetVoiceStatus('');};rec.onresult=ev=>{let interim='';for(let i=ev.resultIndex;i<ev.results.length;i++){const r=ev.results[i];if(r.isFinal)finalText+=(finalText?' ':'')+r[0].transcript;else interim+=r[0].transcript;}const shown=(finalText+' '+interim).trim();if(shown){$('#ashInput').value=shown;ashSetVoiceStatus('Hearing: '+shown,true)}};try{rec.start()}catch(e){ashStopListening();msg(String(e.message||e))}}"
                    "function toggleAshMic(){if(ashVoice.listening)ashStopListening();else{openGlobalAsh();setTimeout(ashStartListening,120)}}"
                )
                t = t[:idx] + helpers + t[idx:]
                print("helpers ok")
        if "$('#ashMic').onclick" not in t:
            t = t.replace("$('#ashSend').onclick=sendGlobalAsh;", "$('#ashSend').onclick=sendGlobalAsh;$('#ashMic').onclick=toggleAshMic;", 1)
            print("wire ok")
        if "Ctrl+Shift+A" not in t and "toggleAshMic" in t:
            t = t.replace(
                "if(e.key==='Escape'&&$('#ashDrawer').classList.contains('open'))closeGlobalAsh()});",
                "if(e.key==='Escape'&&$('#ashDrawer').classList.contains('open')){if(typeof ashStopListening==='function')ashStopListening();closeGlobalAsh()}if((e.ctrlKey||e.metaKey)&&e.shiftKey&&e.key.toLowerCase()==='a'){e.preventDefault();toggleAshMic()}});",
                1,
            )
            print("hotkey ok")
    # Backend intents (optional enhancement)
    if "wants_contacts" not in t and "def global_ash_ask" in t:
        anchor2 = "    actions=[];results=[];bullets=[];scope=f\"Context: {context.get('title') or view.replace('_',' ').title()} · BrokerBeacon database\"\n    if selected and any(w in q for w in ['this broker','this account','them','their','current account','what should i do']):"
        for a in (anchor2,):
            if a in t:
                print("intents anchor found - skipping heavy insert in minimal patcher")
                break
        else:
            print("no intent anchor (ok)")
    APP.write_text(t)
    print("final", APP.stat().st_size)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
