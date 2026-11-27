import io
import os
import sqlite3
import tempfile
import unittest
import wave
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree

from flask import Flask, g
from twilio.request_validator import RequestValidator

from priority_dialer import PREFIX, install_priority_dialer, production_window

ORIGIN = "https://dialer.example"
TOKEN = "test-token"
ACCOUNT = "AC" + "1" * 32
AGENT = "CA" + "2" * 32
HEADERS = {"X-BrokerBeacon-Dialer": "1"}


class FakeCalls:
    def __init__(self, case):
        self.create = case.create

    def __call__(self, sid):
        return SimpleNamespace(fetch=lambda: SimpleNamespace(status="queued"))


class PriorityDialerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="dialer-unit-test")
        self.role = "Owner"
        self.workspace = 1
        self.user = 100
        self.calls = []
        self.sid = ""
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {
            "DIALER_ENABLED": "true", "DIALER_PUBLIC_URL": ORIGIN,
            "TWILIO_ACCOUNT_SID": ACCOUNT, "TWILIO_AUTH_TOKEN": TOKEN,
            "TWILIO_FROM_NUMBER": "+17045550100", "TWILIO_API_KEY_SID": "SK" + "1" * 32,
            "TWILIO_API_KEY_SECRET": "fake-key", "TWILIO_DIALER_APP_SID": "AP" + "1" * 32,
        }).start()
        patch("priority_dialer.client", return_value=SimpleNamespace(calls=FakeCalls(self))).start()
        self.http = app.test_client()

        @app.before_request
        def authenticate():
            g.workspace_id, g.user_id, g.membership_role = self.workspace, self.user, self.role

        def db():
            conn = sqlite3.connect(self.root / f"workspace-{g.workspace_id}.db")
            conn.row_factory = sqlite3.Row
            return conn

        install_priority_dialer(app, db, lambda: date.today().isoformat() + "T12:00:00")
        self.seed(1)
        self.seed(2)

    def seed(self, workspace):
        with sqlite3.connect(self.root / f"workspace-{workspace}.db") as conn:
            conn.executescript("""
                create table prospects(id integer primary key, company text, status text, updated_at text);
                create table contacts(id integer primary key, prospect_id integer, name text, nmls text,
                    email text,phone text,mobile text,voice_opt_out integer default 0);
                create table suppressions(channel text,destination text);
                create table memories(id integer primary key, prospect_id integer,note_type text,note text,
                    follow_up_date text,created_at text);
                create table sales_actions(id integer primary key, prospect_id integer,action_type text,outcome text,
                    notes text,follow_up_date text,created_at text,source_view text);
                create table production_records(id integer primary key, import_id integer,
                    lo_nmls text,lo_name text,company text,units integer,volume real,data_as_of text,
                    source_name text,period_month text,loan_type text,purpose text);
                insert into prospects values (1,'Carolina Mortgage','New','');
                insert into contacts(id, prospect_id, name, nmls, email, phone, mobile) values
                    (1,1,'Alpha Agent','5001','alpha@example.org','704-555-0101','704-555-0111'),
                    (2,1,'Betsy Broker','5002','betsy@example.org','(704) 555-0102',''),
                    (3,1,'Charlie Contact','5003','','704-555-0103',''),
                    (4,1,'Dana Suppressed','5004','','704-555-0104','');
                insert into suppressions values ('VOICE','(704) 555-0104');
            """)
            first, _ = production_window(date.today())
            conn.executemany("""
                insert into production_records (import_id,lo_nmls,lo_name,company,units,volume,
                    data_as_of,source_name,period_month,loan_type,purpose)
                values (?,?,?,?,?,?,?,'Unit test source',?,'Non-QM','Purchase')
            """, [
                (1,"5001","Alpha Agent","Carolina Mortgage",14,4_200_000,"2020-01-01",first),
                (2,"5001","Alpha Agent","Carolina Mortgage",15,4_500_000,"2020-02-01",first),
                (3,"5002","Betsy Broker","Carolina Mortgage",2,600_000,"2020-02-01",first),
                (4,"","Carolina Mortgage","Carolina Mortgage",99,99_000_000,"2020-02-01",first),
            ])

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.sid = "CA" + f"{len(self.calls) + 100:032d}"
        return SimpleNamespace(sid=self.sid, status="queued")

    def provider(self, path, **form):
        form = {"AccountSid": ACCOUNT, **form}
        signature = RequestValidator(TOKEN).compute_signature(ORIGIN + path, form)
        return self.http.post(path, data=form, headers={"X-Twilio-Signature": signature})

    def post(self, path, **data):
        return self.http.post(PREFIX + path, json=data, headers=HEADERS)

    def control(self, session, action):
        response = self.post(f"/session/{session['id']}/control", action=action, leg_sid=AGENT)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["session"]

    def start(self, **data):
        result = self.post("/session", **data)
        self.assertEqual(result.status_code, 201, result.json)
        session = result.json["session"]
        room = self.provider("/dialer/voice/agent", From="client:bb_1_100", CallSid=AGENT, DialerSession=session["id"])
        self.assertIn(b"<Conference", room.data)
        response = self.provider(f"/dialer/voice/1/conference/{session['id']}", CallSid=AGENT,
                                 ConferenceSid="CFTEST", StatusCallbackEvent="participant-join")
        self.assertEqual(response.status_code, 204)
        return self.control(session, "resume")

    def store_outcome(self, session, **values):
        return self.post(f"/session/{session['id']}/outcome", attempt_id=session["current"]["attempt_id"], **values)

    def event(self, kind, session, **form):
        attempt = session["current"]["attempt_id"]
        return self.provider(f"/dialer/voice/1/{kind}/{attempt}", CallSid=self.sid, **form)

    def create_clip(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as recording:
            recording.setparams((1, 2, 8000, 8000, "NONE", "not compressed"))
            recording.writeframes(bytes(16000))
        audio.seek(0)
        result = self.http.post(PREFIX + "/clips", data={"audio": (audio, "test.wav"), "name": "My voice"}, headers=HEADERS)
        self.assertEqual(result.status_code, 201, result.json)
        return result.json["id"]

    def test_ranking_filter_and_superseded_imports(self):
        result = self.http.get(PREFIX + "/contacts")
        self.assertEqual(result.status_code, 200, result.json)
        rows = result.json["items"]
        self.assertEqual(1, rows[0]["id"])
        self.assertEqual(15, rows[0]["units"])
        self.assertEqual(4_500_000, rows[0]["volume"])
        self.assertIsNone(next(row["units"] for row in rows if row["id"] == 3))
        self.assertEqual(3, result.json["eligible"])
        filtered = self.http.get(PREFIX + "/contacts?search=7045550102&min_units=1").json["items"]
        self.assertEqual([2], [row["id"] for row in filtered])
        ordered = self.http.get(PREFIX + "/contacts?sort=units&direction=asc").json["items"]
        self.assertEqual([2, 1], [row["id"] for row in ordered[:2]])
        changed = self.http.put(PREFIX + "/weights", json={"units": 100, "volume": 0, "relationship": 0, "follow_up": 0}, headers=HEADERS)
        self.assertEqual(changed.status_code, 200)

    def test_live_to_voicemail_to_no_answer_and_duplicate_events(self):
        clip = self.create_clip()
        consent = self.http.put(PREFIX + "/contacts/2/phone-policy", json={
            "number": "+17045550102", "state": "consent", "evidence": "Signed form #17",
        }, headers=HEADERS)
        self.assertEqual(consent.status_code, 200, consent.json)
        first = self.start(mode="automatic", clip_id=clip, options={"sort": "first_name", "direction": "asc"})
        self.assertEqual("+17045550101", self.calls[0]["to"])
        self.control(first, "pulse")
        self.assertEqual(1, len(self.calls))
        human = self.event("answer", first, AnsweredBy="human")
        self.assertIn(b"<Conference", human.data)
        self.event("status", first, CallStatus="completed")
        self.event("status", first, CallStatus="ringing")
        result = self.store_outcome(first, outcome="Connected", notes="Discussed NonQM", follow_up=date.today().isoformat())
        self.assertEqual(200, result.status_code, result.json)
        self.assertEqual(200, self.store_outcome(first, outcome="Connected").status_code)
        second = self.control(result.json["session"], "pulse")
        self.assertEqual("+17045550102", self.calls[-1]["to"])
        voicemail = ElementTree.fromstring(self.event("answer", second, AnsweredBy="machine_end_beep").data)
        audio = voicemail.find("Play").text.removeprefix(ORIGIN)
        self.assertEqual("audio/wav", self.http.get(audio).mimetype)
        self.assertIsNone(ElementTree.fromstring(self.event("answer", second, AnsweredBy="machine_end_beep").data).find("Play"))
        self.event("played", second)
        self.event("status", second, CallStatus="completed")
        result = self.store_outcome(second, outcome="Left voicemail")
        third = self.control(result.json["session"], "pulse")
        self.assertEqual("+17045550103", self.calls[-1]["to"])
        self.event("status", third, CallStatus="no-answer")
        result = self.store_outcome(third, outcome="No answer")
        self.assertEqual("ended", result.json["session"]["state"])
        self.assertEqual(3, len(self.calls))
        self.assertIsNone(self.http.get(PREFIX + "/session").json["session"])
        with sqlite3.connect(self.root / "workspace-1.db") as conn:
            self.assertEqual(3, conn.execute("select count(*) from sales_actions").fetchone()[0])
            self.assertEqual(1, conn.execute("select count(*) from memories").fetchone()[0])
        rows = self.http.get(PREFIX + "/contacts").json["items"]
        self.assertEqual(date.today().isoformat(), next(row["follow_up"] for row in rows if row["id"] == 1))
        self.assertEqual("", next(row["follow_up"] for row in rows if row["id"] == 2))

    def test_manual_arm_pause_and_suppression_rechecked(self):
        clip = self.create_clip()
        self.http.put(PREFIX + "/contacts/1/phone-policy", json={
            "number": "+17045550101", "state": "consent", "evidence": "Signed form #18",
        }, headers=HEADERS)
        first = self.start(mode="manual", clip_id=clip, options={"sort": "first_name", "direction": "asc"})
        self.assertTrue(self.control(first, "arm")["current"]["armed"])
        self.assertEqual("paused", self.control(first, "pause")["state"])
        self.assertIn(b"<Play>", self.event("answer", first, AnsweredBy="machine_end_beep").data)
        self.event("status", first, CallStatus="completed")
        result = self.store_outcome(first, outcome="Left voicemail")
        self.assertEqual(2, result.json["session"]["current"]["contact_id"])
        self.assertEqual(1, len(self.calls))
        self.http.put(PREFIX + "/contacts/2/phone-policy", json={
            "number": "+17045550102", "state": "suppress", "evidence": "Opted out by phone",
        }, headers=HEADERS)
        third = self.control(first, "resume")
        self.assertEqual(3, third["current"]["contact_id"])
        self.assertEqual(1, third["counts"]["skipped"])

    def test_unauthorized_requests_and_private_workspace_audio(self):
        clip = self.create_clip()
        self.assertEqual(403, self.http.post("/dialer/voice/agent", data={"AccountSid": ACCOUNT}).status_code)
        self.assertEqual(403, self.provider("/dialer/voice/agent", From="client:unknown", CallSid=AGENT).status_code)
        self.assertEqual(403, self.http.post(PREFIX + "/session", json={}).status_code)
        self.workspace = 2
        self.assertEqual(404, self.http.get(f"{PREFIX}/clips/{clip}/audio").status_code)
        self.role = "Read Only"
        self.assertEqual(403, self.http.get(PREFIX + "/contacts").status_code)


if __name__ == "__main__":
    unittest.main()
