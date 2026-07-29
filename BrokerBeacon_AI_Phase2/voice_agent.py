"""Consent-first outbound voice automation for BrokerBeacon.

Twilio handles PSTN calls, speech capture, AMD and female TTS. OpenAI is optional
for concise conversational replies. The workflow never calls a contact unless
voice_consent=1 and voice_opt_out=0.
"""
import os, json, urllib.parse, urllib.request, base64
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

VOICE = os.getenv('TWILIO_VOICE', 'Polly.Joanna')
LANGUAGE = os.getenv('TWILIO_VOICE_LANGUAGE', 'en-US')


def configured():
    return bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN') and os.getenv('TWILIO_FROM_NUMBER'))


def create_twilio_call(to_number, callback_url, status_url):
    sid=os.environ['TWILIO_ACCOUNT_SID']; token=os.environ['TWILIO_AUTH_TOKEN']
    payload=urllib.parse.urlencode({
        'To':to_number,'From':os.environ['TWILIO_FROM_NUMBER'],'Url':callback_url,
        'Method':'POST','StatusCallback':status_url,'StatusCallbackMethod':'POST',
        'StatusCallbackEvent':['initiated','ringing','answered','completed'],
        'MachineDetection':'DetectMessageEnd','MachineDetectionTimeout':'30'
    }, doseq=True).encode()
    req=urllib.request.Request(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json',data=payload,method='POST')
    req.add_header('Authorization','Basic '+base64.b64encode(f'{sid}:{token}'.encode()).decode())
    req.add_header('Content-Type','application/x-www-form-urlencoded')
    with urllib.request.urlopen(req,timeout=25) as r:
        return json.loads(r.read().decode())


def say(text):
    return f'<Say voice="{escape(VOICE)}" language="{escape(LANGUAGE)}">{escape(text)}</Say>'


def twiml(body):
    return '<?xml version="1.0" encoding="UTF-8"?><Response>'+body+'</Response>'


def human_greeting(first_name, company, call_id):
    intro=(f'Hi {first_name}. This is Ash, an automated AI assistant calling on behalf of Clay at Union Home Mortgage. '
           f'I am calling about lending support for {company}. This call may be recorded or transcribed for follow-up. '
           'Is now a good time for a brief conversation? You can also say stop at any time.')
    return twiml(f'<Gather input="speech dtmf" action="/voice/respond/{call_id}" method="POST" speechTimeout="auto" timeout="6">{say(intro)}</Gather>{say("I did not hear a response. I will send this back to Clay for personal follow-up. Goodbye.")}')


def voicemail(first_name, company):
    text=(f'Hi {first_name}, this is Ash, an automated assistant calling for Clay at Union Home Mortgage. '
          f'Clay would like to connect regarding lending support for {company}. Please return his call when convenient. '
          'Thank you, and have a great day.')
    return twiml(say(text))


def appointment_slots(now=None):
    now=now or datetime.now(); slots=[]; d=now+timedelta(days=1)
    while len(slots)<3:
        if d.weekday()<5:
            for hour in (10,14):
                slots.append(d.replace(hour=hour,minute=0,second=0,microsecond=0))
                if len(slots)==3: break
        d+=timedelta(days=1)
    return slots


def ai_reply(user_text, context):
    key=os.getenv('OPENAI_API_KEY')
    if not key:
        return None
    prompt=("You are Ash, a disclosed automated female-voice sales assistant for a wholesale mortgage account executive. "
            "Be warm, concise, truthful, and never claim rates, approvals, savings, or production facts not in context. "
            "Do not pressure. If asked to stop, confirm opt-out. If interested, offer a short appointment. "
            "Keep the response under 45 words.\nContext: "+context+"\nProspect said: "+user_text)
    data=json.dumps({'model':os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini'),'input':prompt,'max_output_tokens':120}).encode()
    req=urllib.request.Request('https://api.openai.com/v1/responses',data=data,method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            obj=json.loads(r.read().decode())
        return (obj.get('output_text') or '').strip() or None
    except Exception:
        return None
