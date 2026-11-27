import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Device} from '@twilio/voice-sdk';

const API = '/api/priority-dialer';
const columns = [
  ['first_name', 'First Name'], ['last_name', 'Last Name'], ['office_number', 'Office Number'],
  ['cell_number', 'Cell Number'], ['email', 'Email'], ['broker_name', 'Broker Name'],
  ['units', 'NonQM Units'], ['volume', 'NonQM Volume'],
];
const components = {units: 'NonQM units', volume: 'NonQM volume', relationship: 'Relationship', follow_up: 'Follow-up'};
const outcomes = ['Connected', 'Left voicemail', 'No answer', 'Busy', 'Failed', 'Wrong number',
  'Do not call', 'Interested', 'Meeting scheduled', 'Not interested'];
const terminal = ['completed', 'no-answer', 'busy', 'failed', 'canceled'];
const currency = new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD', maximumFractionDigits: 0});
const numberFormat = new Intl.NumberFormat('en-US');
const fullName = contact => [contact.first_name, contact.last_name].filter(Boolean).join(' ') || 'Unnamed contact';

async function api(path, method = 'GET', body) {
  const headers = {'X-BrokerBeacon-Dialer': '1'};
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  const response = await fetch(API + path, {method, headers, body, cache: 'no-store'});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(result.error || 'Request failed. Try again.'), {status: response.status});
  return result;
}

function useDialerSession(onError) {
  const [session, setSession] = useState(null);
  const [audio, setAudio] = useState(false);
  const [busy, setBusy] = useState(false);
  const device = useRef(null);
  const call = useRef(null);
  const currentSession = useRef(null);
  const pending = useRef(false);
  const ending = useRef(false);

  function apply(next) {
    currentSession.current = next;
    setSession(next);
    if (next?.state === 'ended') call.current?.disconnect();
  }

  useEffect(() => {
    let mounted = true;
    api('/session').then(data => { if (mounted) apply(data.session); }).catch(onError);
    return () => { mounted = false; device.current?.destroy(); };
  }, []);

  async function command(action, id = currentSession.current?.id) {
    if (!id) return;
    const result = await api(`/session/${id}/control`, 'POST', {action, confirmed: action === 'resolve', leg_sid: call.current?.parameters?.CallSid});
    apply(result.session);
  }

  async function withLock(task) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    try { await task(); }
    catch (error) { onError(error); }
    finally { pending.current = false; setBusy(false); }
  }

  async function connect(id, resume = true) {
    if (!device.current) {
      const {token} = await api('/token');
      device.current = new Device(token, {logLevel: 1});
      device.current.on('tokenWillExpire', async () => {
        try { device.current?.updateToken((await api('/token')).token); }
        catch (error) { onError(error); }
      });
      device.current.on('error', onError);
    }
    const outgoing = await device.current.connect({params: {DialerSession: id}});
    call.current = outgoing;
    function disconnect() {
      if (call.current !== outgoing) return;
      call.current = null;
      setAudio(false);
      if (!ending.current && currentSession.current?.state !== 'ended') {
        command('pause', id).catch(onError);
      }
    }
    outgoing.on('disconnect', disconnect);
    outgoing.on('cancel', disconnect);
    outgoing.on('error', error => { onError(error); disconnect(); });
    await new Promise((resolve, reject) => {
      if (outgoing.status() === 'open') return resolve();
      const timer = setTimeout(() => reject(new Error('Headset connection timed out')), 12000);
      outgoing.once('accept', () => { clearTimeout(timer); resolve(); });
      outgoing.once('disconnect', () => { clearTimeout(timer); reject(new Error('Headset disconnected')); });
      outgoing.once('error', error => { clearTimeout(timer); reject(error); });
    }).catch(error => { outgoing.disconnect(); throw error; });

    // The SDK can accept before the conference participant callback reaches Flask.
    for (let attempt = 0; attempt < 12; attempt += 1) {
      try {
        await command(resume ? 'resume' : 'pulse', id);
        setAudio(true);
        return;
      } catch (error) {
        if (error.status !== 409 || !call.current || attempt === 11) {
          outgoing.disconnect();
          throw error;
        }
        await new Promise(resolve => setTimeout(resolve, 400));
      }
    }
  }

  useEffect(() => {
    if (!session || session.state === 'ended') return;
    const timer = setInterval(async () => {
      if (pending.current) return;
      pending.current = true;
      try {
        if (audio && call.current && ['paused', 'running'].includes(currentSession.current?.state)) {
          await command('pulse');
        } else {
          const {session: next} = await api('/session');
          apply(next);
        }
      } catch (error) {
        if (error.status === 409 && call.current) call.current.disconnect();
        onError(error);
      } finally {
        pending.current = false;
      }
    }, 1800);
    return () => clearInterval(timer);
  }, [session?.id, session?.state, audio]);

  return {
    audio, busy, session,
    start: data => withLock(async () => {
      ending.current = false;
      const {session: created} = await api('/session', 'POST', data);
      apply(created);
      await connect(created.id);
    }),
    resume: () => withLock(async () => {
      ending.current = false;
      if (call.current) await command('resume');
      else await connect(currentSession.current.id);
    }),
    control: action => withLock(async () => {
      if (action === 'end') ending.current = true;
      try { await command(action); }
      finally { if (action === 'end') call.current?.disconnect(); }
    }),
    mute: muted => call.current?.mute(muted),
    save: (attemptId, fields) => withLock(async () => {
      const {session: updated} = await api(`/session/${currentSession.current.id}/outcome`, 'POST',
        {attempt_id: attemptId, ...fields});
      apply(updated);
      if (updated.state === 'running' && call.current) await command('pulse');
    }),
  };
}

function ContactTable({items, options, sort, select, current, selected}) {
  return <div className="table-scroll"><table>
    <thead><tr>{columns.map(([key, label]) => <th key={key} aria-sort={
      options.sort === key ? (options.direction === 'desc' ? 'descending' : 'ascending') : 'none'}>
      <button onClick={() => sort(key)}>{label}{options.sort === key ? (options.direction === 'desc' ? ' ↓' : ' ↑') : ''}</button>
    </th>)}</tr></thead>
    <tbody>{items.map(contact => <tr key={contact.id} className={current === contact.id ? 'current' : selected === contact.id ? 'selected' : ''}>
      {columns.map(([key]) => <td key={key}>
        {key === 'first_name'
          ? <button className="table-name" onClick={() => select(contact)} aria-label={`Show ${fullName(contact)}, priority ${contact.score}`}>
              {contact[key] || '—'}<small>{current === contact.id ? 'Current · ' : ''}{contact.score}/100</small>
            </button>
          : key === 'volume' ? (contact[key] == null ? '—' : currency.format(contact[key]))
          : key === 'units' ? (contact[key] == null ? '—' : numberFormat.format(contact[key]))
          : contact[key] || '—'}
      </td>)}
    </tr>)}</tbody>
  </table>{items.length === 0 && <p className="empty">No contacts match this view.</p>}</div>;
}

async function toWav(blob) {
  const context = new AudioContext();
  try {
    const source = await context.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.min(480000, Math.floor(source.duration * 8000));
    if (frames < 8000) throw new Error('Record at least one second of audio.');
    const offline = new OfflineAudioContext(1, frames, 8000);
    const node = offline.createBufferSource();
    node.buffer = source;
    node.connect(offline.destination);
    node.start();
    const samples = (await offline.startRendering()).getChannelData(0);
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    function text(offset, value) {
      [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
    }
    text(0, 'RIFF'); view.setUint32(4, view.byteLength - 8, true); text(8, 'WAVE');
    text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, 8000, true); view.setUint32(28, 16000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    text(36, 'data'); view.setUint32(40, samples.length * 2, true);
    samples.forEach((sample, index) => view.setInt16(44 + index * 2, Math.max(-1, Math.min(1, sample)) * 32767, true));
    return new Blob([view], {type: 'audio/wav'});
  } finally { await context.close(); }
}

function VoicemailLibrary({clips, refresh, onError}) {
  const [recording, setRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const [clip, setClip] = useState(null);
  const [preview, setPreview] = useState('');
  const [name, setName] = useState('');
  const recorder = useRef(null);

  useEffect(() => {
    if (!clip) { setPreview(''); return; }
    const url = URL.createObjectURL(clip);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [clip]);

  useEffect(() => () => { if (recorder.current?.state === 'recording') recorder.current.stop(); }, []);

  async function record() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const input = new MediaRecorder(stream);
      recorder.current = input;
      const chunks = [];
      const timeout = setTimeout(() => { if (input.state === 'recording') input.stop(); }, 59000);
      input.ondataavailable = event => chunks.push(event.data);
      input.onstop = async () => {
        clearTimeout(timeout);
        stream.getTracks().forEach(track => track.stop());
        try { setClip(await toWav(new Blob(chunks, {type: input.mimeType}))); }
        catch (error) { onError(error); }
        finally { setRecording(false); }
      };
      input.onerror = event => { onError(event.error); if (input.state === 'recording') input.stop(); };
      setClip(null);
      input.start();
      setRecording(true);
    } catch (error) {
      stream?.getTracks().forEach(track => track.stop());
      onError(error);
    }
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    try {
      const data = new FormData();
      data.set('audio', clip, 'voicemail.wav');
      data.set('name', name.trim());
      await api('/clips', 'POST', data);
      setClip(null);
      setName('');
      await refresh();
    } catch (error) { onError(error); }
    finally { setSaving(false); }
  }

  return <details><summary>Voicemail library</summary>
    <form className="settings-form" onSubmit={save}>
      <button type="button" onClick={recording ? () => recorder.current.stop() : record} disabled={saving}>
        {recording ? 'Stop recording' : 'Record my voice'}
      </button>
      {preview && <>
        <audio controls src={preview} />
        <label>Clip name<input value={name} onChange={event => setName(event.target.value)} maxLength={80} required /></label>
        <button className="primary" disabled={!name.trim() || saving}>Approve & save</button>
      </>}
    </form>
    {clips.map(item => <div className="saved-clip" key={item.id}><span>{item.name} · {Math.round(item.seconds)}s</span>
      <audio controls preload="none" src={`${API}/clips/${item.id}/audio`} /></div>)}
  </details>;
}

function WeightsForm({weights, refresh, onError}) {
  const [draft, setDraft] = useState(weights);
  return <details><summary>Priority weights</summary>
    <form className="settings-form" onSubmit={async event => {
      event.preventDefault();
      try { await api('/weights', 'PUT', draft); refresh(); }
      catch (error) { onError(error); }
    }}>
      {Object.entries(components).map(([key, label]) => <label key={key}>{label}
        <input type="number" min="0" max="100" value={draft[key]} required
          onChange={event => setDraft({...draft, [key]: Number(event.target.value)})} />
      </label>)}
      <button className="primary" disabled={Object.values(draft).reduce((sum, value) => sum + value, 0) !== 100}>Save weights</button>
    </form>
  </details>;
}

function PhonePolicy({contact, canManage, refresh, onError}) {
  const [number, setNumber] = useState(contact.numbers[0]?.number || '');
  const [evidence, setEvidence] = useState('');
  const [state, setState] = useState('revoke');
  if (!contact.numbers.length) return null;
  return <details><summary>Phone permissions</summary>
    <ul className="phone-details">{contact.numbers.map(item => <li key={item.number}>{item.number} · {
      item.suppressed ? 'Do not call' : item.consent ? 'Voicemail consent on file' : 'Live calls only'}</li>)}</ul>
    <form className="settings-form" onSubmit={async event => {
      event.preventDefault();
      try { await api(`/contacts/${contact.id}/phone-policy`, 'PUT', {number, state, evidence}); setEvidence(''); refresh(); }
      catch (error) { onError(error); }
    }}>
      <label>Number<select value={number} onChange={event => setNumber(event.target.value)}>
        {contact.numbers.map(item => <option key={item.number}>{item.number}</option>)}
      </select></label>
      <label>Permission<select value={state} onChange={event => setState(event.target.value)}>
        {canManage && <option value="consent">Record written voicemail consent</option>}
        <option value="revoke">Revoke voicemail consent</option><option value="suppress">Do not call</option>
        {canManage && <option value="clear">Clear dialer suppression</option>}
      </select></label>
      <label>Consent evidence or reason<input value={evidence} onChange={event => setEvidence(event.target.value)} required maxLength={2000} /></label>
      <button>Save permission</button>
    </form>
  </details>;
}

function OutcomeForm({attempt, save, busy}) {
  const suggested = attempt.playback_complete ? 'Left voicemail'
    : ({busy: 'Busy', 'no-answer': 'No answer', failed: 'Failed', canceled: 'No answer'})[attempt.status]
      || (attempt.detected === 'human' ? 'Connected' : 'No answer');
  const [outcome, setOutcome] = useState('');
  const [notes, setNotes] = useState('');
  const [followUp, setFollowUp] = useState('');
  function addDays(days) {
    const day = new Date();
    day.setDate(day.getDate() + days);
    const pad = value => String(value).padStart(2, '0');
    setFollowUp(`${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`);
  }
  return <form className="wrap-up" onSubmit={event => {
    event.preventDefault();
    save(attempt.attempt_id, {outcome: outcome || suggested, notes, follow_up: followUp});
  }}>
    <h3>Log outcome</h3>
    <label>Outcome<select value={outcome || suggested} onChange={event => setOutcome(event.target.value)}>
      {outcomes.map(value => <option key={value}>{value}</option>)}
    </select></label>
    <label>Notes<textarea value={notes} onChange={event => setNotes(event.target.value)} maxLength={5000} /></label>
    <label>Next follow-up<input type="date" value={followUp} onChange={event => setFollowUp(event.target.value)} /></label>
    <div className="row-controls">{[1, 3, 7].map(days => <button key={days} type="button" onClick={() => addDays(days)}>+{days}d</button>)}</div>
    <button className="primary" disabled={busy}>Save & continue</button>
  </form>;
}

function CallPanel({contact, dialer, canManage, refresh, onError}) {
  const [muted, setMuted] = useState(false);
  const {session, busy, audio} = dialer;
  const item = session?.current;
  const active = session && session.state !== 'ended';
  const live = item?.attempt_id && !terminal.includes(item.status);
  useEffect(() => setMuted(false), [audio]);
  return <aside className="call-panel" aria-label="Dialer controls">
    <h2>{active ? 'Dialer session' : 'Contact details'}</h2>
    {active && <>
      <div className="status" aria-live="polite">
        {session.state === 'closing' ? 'Finishing session' : session.state === 'paused' ? 'Paused'
          : item?.status === 'starting' ? 'Starting call' : live ? item.status : 'Ready'}
        <span>{session.counts.done || 0} logged · {session.counts.pending || 0} waiting · {session.counts.skipped || 0} skipped</span>
      </div>
      {item && <p>{live ? 'Calling' : 'Selected number'} <strong>{item.number}</strong></p>}
      {item?.status === 'unconfirmed' && <p role="status">The provider has not confirmed this call. Verify it in the Twilio call log before clearing this attempt.</p>}
      {session.next && <p className="next-contact">Next · {fullName(session.next)} · {session.next.broker_name}</p>}
      <div className="row-controls">
        {audio && <button onClick={() => { dialer.mute(!muted); setMuted(!muted); }}>{muted ? 'Unmute' : 'Mute'}</button>}
        {live && item?.status !== 'unconfirmed' && <button onClick={() => dialer.control('hangup')} disabled={busy}>Hang up</button>}
        {item?.status === 'unconfirmed' && <button disabled={busy} onClick={() => {
          if (window.confirm('Have you checked the Twilio call log and confirmed there is no active call?')) dialer.control('resolve');
        }}>Clear unconfirmed call</button>}
        {session.state === 'running' && <button onClick={() => dialer.control('pause')} disabled={busy}>Pause</button>}
        {session.state === 'paused' && <button className="primary" onClick={dialer.resume} disabled={busy}>
          {audio ? 'Resume' : 'Connect headset & resume'}</button>}
        {session.state !== 'closing' && <button onClick={() => dialer.control('end')} disabled={busy}>End session</button>}
      </div>
      {live && session.mode === 'manual' && !item.detected && item.status !== 'unconfirmed' &&
        <button onClick={() => dialer.control('arm')} disabled={busy || !!item.armed || !audio || !item.contact.numbers.some(phone => phone.number === item.number && phone.consent)}>
          {item.armed ? 'Voicemail armed' : 'Drop voicemail on beep'}
        </button>}
      {item?.attempt_id && !live && <OutcomeForm key={item.attempt_id} attempt={item} save={dialer.save} busy={busy} />}
    </>}
    {contact ? <>
      <h3>{fullName(contact)} <span className="score">{contact.score}/100</span></h3>
      <p>{contact.broker_name}</p>
      <dl>{Object.entries(components).map(([key,label]) => <React.Fragment key={key}>
        <dt>{label}</dt><dd>{contact.components[key]}/100</dd>
      </React.Fragment>)}</dl>
      <p>{contact.source ? `${contact.source} · ${contact.period}` : 'No NonQM production data'}</p>
      <p>Follow-up · {contact.follow_up || 'Unscheduled'}</p>
      {contact.recent.length > 0 && <details><summary>Recent activity</summary>
        <ul>{contact.recent.map((item, index) => <li key={index}>{item.created_at.slice(0, 10)} · {item.outcome}{item.notes ? ` — ${item.notes}` : ''}</li>)}</ul>
      </details>}
      {!active && <PhonePolicy key={contact.id} contact={contact} canManage={canManage} refresh={refresh} onError={onError} />}
    </> : <p>Select a contact to see their priority breakdown and phone permissions.</p>}
  </aside>;
}

function App() {
  const [options, setOptions] = useState({phone: 'office', sort: 'priority', direction: 'desc', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone});
  const [page, setPage] = useState(1);
  const [list, setList] = useState(null);
  const [selected, setSelected] = useState(null);
  const [clips, setClips] = useState([]);
  const [clipId, setClipId] = useState('');
  const [mode, setMode] = useState('off');
  const [notice, setNotice] = useState('');
  const [revision, reload] = useState(0);
  const [loading, setLoading] = useState(true);
  const onError = error => setNotice(error.message || String(error));
  const refresh = () => reload(value => value + 1);
  const dialer = useDialerSession(onError);
  const session = dialer.session;
  const active = session && session.state !== 'ended';

  useEffect(() => {
    let current = true;
    setLoading(true);
    const timer = setTimeout(() => {
      api('/contacts?' + new URLSearchParams({...options, page})).then(result => {
        if (current) setList(result);
      }).catch(error => { if (current) onError(error); }).finally(() => { if (current) setLoading(false); });
    }, 180);
    return () => { clearTimeout(timer); current = false; };
  }, [options, page, revision]);
  const loadClips = () => api('/clips').then(result => setClips(result.items)).catch(onError);
  useEffect(() => { loadClips(); }, []);
  useEffect(() => { if (session?.state === 'ended') refresh(); }, [session?.state]);
  useEffect(() => {
    document.querySelector('.table-scroll tr.current')?.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }, [session?.current?.contact_id]);

  function update(key, value) {
    setPage(1);
    setOptions(previous => ({...previous, [key]: value}));
  }

  function sort(key) {
    setPage(1);
    setOptions(previous => ({...previous, sort: key, direction: previous.sort === key && previous.direction === 'asc' ? 'desc' : 'asc'}));
  }

  const focus = active ? session.current?.contact : list?.items.find(item => item.id === selected);
  const items = list?.items || [];
  const current = session?.current?.contact;
  const displayed = active && current && !items.some(item => item.id === current.id) ? [current, ...items] : items;

  return <main>
    <header><div><a href="/">BrokerBeacon</a><h1>Priority Auto-Dialer</h1></div>
      <button className="primary start" disabled={loading || dialer.busy || !!active || !list?.configured ||
        !list?.eligible || (mode !== 'off' && !clipId)}
        onClick={() => { setNotice(''); dialer.start({options, mode, clip_id: clipId}); }}>Start auto-dialing</button>
    </header>
    {notice && <div className="notice" role="alert">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
    {list && !list.configured && <p className="notice">Live dialing is unavailable until a workspace phone connection is configured.</p>}
    <div className="workspace">
      <section className="queue" aria-label="Contact queue">
        <div className="filters">
          <label>Search<input placeholder="Name, broker, email or number" value={options.search || ''} onChange={event => update('search', event.target.value)} /></label>
          <label>Broker<input value={options.broker || ''} onChange={event => update('broker', event.target.value)} /></label>
          <label>Follow-up<select value={options.follow_up || ''} onChange={event => update('follow_up', event.target.value)}>
            <option value="">Any date</option><option value="overdue">Overdue</option><option value="today">Due today</option>
            <option value="week">Next 7 days</option><option value="later">Later</option><option value="unscheduled">Unscheduled</option>
          </select></label>
          <label>Relationship<select value={options.relationship || ''} onChange={event => update('relationship', event.target.value)}>
            <option value="">All contacts</option><option value="warm">Recent activity</option><option value="cold">No recent activity</option>
          </select></label>
          <label>Phone availability<select value={options.callable || ''} onChange={event => update('callable', event.target.value)}>
            <option value="">All contacts</option><option value="yes">Callable</option><option value="no">Unavailable</option>
          </select></label>
        </div>
        <details><summary>Production filters</summary><div className="filters">
          {[['min_units', 'Min. units'], ['max_units', 'Max. units'], ['min_volume', 'Min. volume'], ['max_volume', 'Max. volume']]
            .map(([key, label]) => <label key={key}>{label}<input type="number" min="0" value={options[key] || ''}
              onChange={event => update(key, event.target.value)} /></label>)}
        </div></details>
        <div className="queue-meta">
          <span aria-live="polite">{list ? `${list.total} contacts · ${list.eligible} unique callable numbers` : 'Loading contacts'}</span>
          <button onClick={() => update('sort', 'priority')} disabled={options.sort === 'priority'}>Reset to priority order</button>
          <label>Call first<select value={options.phone} onChange={event => update('phone', event.target.value)} disabled={!!active}>
            <option value="office">Office</option><option value="cell">Cell</option>
          </select></label>
        </div>
        <ContactTable items={displayed} options={options} sort={sort} select={contact => setSelected(contact.id)}
          current={active ? current?.id : undefined} selected={selected} />
        {list?.total > 75 && <div className="pager">
          <button disabled={page === 1 || loading} onClick={() => setPage(page - 1)}>Previous page</button>
          <span>Page {page} of {Math.ceil(list.total / 75)}</span>
          <button disabled={page * 75 >= list.total || loading} onClick={() => setPage(page + 1)}>Next page</button>
        </div>}
        <div className="voicemail-settings">
          <label>Voicemail<select value={mode} onChange={event => setMode(event.target.value)} disabled={!!active}>
            <option value="off">Off</option><option value="manual">One-click drop</option><option value="automatic">Automatic on beep</option>
          </select></label>
          {mode !== 'off' && <label>Approved recording<select value={clipId} onChange={event => setClipId(event.target.value)} disabled={!!active}>
            <option value="">Select a clip</option>{clips.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></label>}
        </div>
        {!active && <VoicemailLibrary clips={clips} refresh={loadClips} onError={onError} />}
        {list?.can_manage && !active && <WeightsForm weights={list.weights} refresh={refresh} onError={onError} />}
      </section>
      <CallPanel contact={focus} dialer={dialer} canManage={list?.can_manage} refresh={refresh} onError={onError} />
    </div>
  </main>;
}

createRoot(document.getElementById('dialer-root')).render(<App />);
