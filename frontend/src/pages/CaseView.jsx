import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Check, DecisionTag, Guilloche, Icon, Loading, Microtext, Sev, Stamp, ruleFamily, useLoad, useOfficer } from '../ui.jsx'

const KIND = { fire_noc: 'Fire NOC', land_doc: 'Land document', faculty_list: 'Faculty list', lab_photo: 'Lab photo', live_photo: 'Live photo' }
const HIDE = new Set(['doc_id', 'other_doc_id', 'document', 'printed', 'issuer_signed', 'field', 'qr_data', 'read_by', 'issuer', 'preview',
  'file', 'session', 'history', 'hidden_text', 'shows'])
const LABEL = {
  qr_check: 'QR check', ref: 'Certificate', issuer_status: 'Issuer says', issuer_reply: 'Issuer says', valid_until: 'Valid until',
  academic_year_start: 'Year starts', issued_on: 'Issued on', holiday: 'That day was', signer: 'Signer', in_post: 'In post',
  signed_on: 'Signed on', uploaded: 'Uploaded says', verified: 'Verified record', verified_source: 'Verified from',
  teacher: 'Teacher', pan: 'PAN', also_at: 'Also listed at', match: 'Matched by', reply: 'Reply', replied: 'Replied at', channel: 'Answered by',
  declared: 'Declared', required: 'Needed', shared: 'Claimed elsewhere', effective: 'Counted', counted: 'Counted', other_institution: 'Other institution',
  other_application: 'Other application', distance: 'Fingerprint bits different', threshold: 'Match limit', phash_distance: 'Second fingerprint (pHash)',
  photo_gps: 'Photo GPS', campus: 'Campus', km: 'Distance (km)', software: 'Saved by', missing: 'Missing',
  saves: 'Save sessions', created_by: 'Created by', modified_with: 'Last saved with', font_used: 'Font used', font_expected: 'Font of other fields',
  what: 'What was found', hotspots: 'Hotspots', copied_patches: 'Copied patches', shot: 'Shot', outside_m: 'Outside boundary (m)',
  accuracy_m: 'GPS accuracy (m)', code: 'Expected code', late_min: 'Minutes late', plane_fit: 'Fits one flat plane',
}
const fmt = v => Array.isArray(v) ? v.join(', ') : typeof v === 'object' && v ? JSON.stringify(v) : String(v)

function Preview({ pv }) {
  const [heat, setHeat] = useState(false)
  const src = heat ? api.heatmap(pv.doc_id) : api.preview(pv.doc_id, pv.page, pv.boxes)
  return (
    <figure className="preview">
      <div className="preview-frame"><img src={src} alt={heat ? 'Error level heat-map of the scan' : 'Document with the suspicious area boxed in red'} loading="lazy" /></div>
      <figcaption>
        {pv.heatmap ? (
          <div className="seg" role="group" aria-label="Preview mode">
            <button className={!heat ? 'on' : ''} aria-pressed={!heat} onClick={() => setHeat(false)}>Document</button>
            <button className={heat ? 'on' : ''} aria-pressed={heat} onClick={() => setHeat(true)}>Heat-map</button>
          </div>
        ) : <span>Red box: the area that was changed</span>}
        {heat && <span>Bright areas re-compress unlike the rest of the page. It says where to look; it is not proof by itself.</span>}
        <a className="link" href={src} target="_blank" rel="noreferrer"><Icon name="open" size={14} />Full size</a>
      </figcaption>
    </figure>
  )
}

function Evidence({ ev }) {
  const rows = Object.entries(ev).filter(([k]) => !HIDE.has(k))
  return (
    <>
      {ev.other_doc_id && (
        <div className="compare">
          <figure><img src={api.file(ev.doc_id)} alt="uploaded" /><figcaption>This application</figcaption></figure>
          <figure><img src={api.file(ev.other_doc_id)} alt="matched" /><figcaption>{ev.other_institution}</figcaption></figure>
        </div>
      )}
      {ev.printed && (
        <div className="vs">
          <div><small>Printed on the document</small><b>{ev.printed}</b></div>
          <span className="neq" aria-label="does not match">≠</span>
          <div><small>Signed by the issuer (QR)</small><b>{ev.issuer_signed}</b></div>
        </div>
      )}
      {ev.hidden_text && (
        <div className="vs">
          <div><small>Hidden under the white box</small><b>{ev.hidden_text}</b></div>
          <span className="neq" aria-label="replaced by">→</span>
          <div className="shown"><small>Visible on top</small><b>{ev.shows}</b></div>
        </div>
      )}
      {ev.history && <p className="history"><Icon name="clock" size={15} />{ev.history}</p>}
      {ev.preview && <Preview pv={ev.preview} />}
      {rows.length > 0 && (
        <dl className="kv">
          {rows.map(([k, v]) => <React.Fragment key={k}><dt>{LABEL[k] || k}</dt><dd>{fmt(v)}</dd></React.Fragment>)}
        </dl>
      )}
      {ev.doc_id && !ev.other_doc_id && !ev.preview && <a className="link" href={api.file(ev.doc_id)} target="_blank" rel="noreferrer"><Icon name="open" size={15} />Open {ev.document}</a>}
    </>
  )
}

function Finding({ f, appId, onChange }) {
  const { officer } = useOfficer()
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const act = async restore => {
    setBusy(true); setErr(null)
    try { await api.dismiss(appId, f, note, officer, restore); setOpen(false); setNote(''); await onChange() } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const [fi, fl] = ruleFamily(f.rule)
  return (
    <article className={`finding sev-${f.severity} ${f.dismissed ? 'dismissed' : ''}`}>
      <div className="fhead">
        <span className="fam" title={fl}><Icon name={fi} size={16} /></span>
        <Sev s={f.severity} />
        <span className="rule">{f.rule}</span>
        {f.dismissed ? <span className="weight zero">dismissed, not counted</span>
          : f.weight > 0 ? <span className="weight" title="Added to the risk score">+{f.weight}</span> : <span className="weight zero">no score</span>}
      </div>
      <h3>{f.title}</h3>
      <p>{f.detail}</p>
      {f.dismissed && <p className="note">Dismissed by the officer: “{f.dismiss_note}”</p>}
      {!f.dismissed && <Evidence ev={f.evidence} />}
      {f.weight > 0 && (
        <div className="fact-actions">
          {f.dismissed ? (
            <button className="btn quiet small" disabled={busy} onClick={() => act(true)}>Restore this flag</button>
          ) : open ? (
            <div className="dismiss-box">
              <label>Why is this flag wrong? This goes into the record.
                <textarea value={note} onChange={e => setNote(e.target.value)} placeholder="For example: second campus, address confirmed by phone" />
              </label>
              <div className="btns">
                <button className="btn primary small" disabled={busy || !note.trim()} onClick={() => act(false)}>Dismiss flag</button>
                <button className="btn quiet small" onClick={() => setOpen(false)}>Cancel</button>
              </div>
              {err && <p className="error">{err}</p>}
            </div>
          ) : (
            <button className="btn quiet small" onClick={() => setOpen(true)}>This flag is wrong</button>
          )}
        </div>
      )}
    </article>
  )
}

function Doc({ d }) {
  const f = Object.entries(d.fields || {}).filter(([, v]) => v !== null && v !== '')
  const m = d.meta || {}
  const fx = d.forensics
  const photo = d.kind === 'lab_photo' || d.kind === 'live_photo'
  return (
    <div className="doc">
      <div className="dochead">
        <b><Icon name="file" size={16} />{KIND[d.kind] || d.kind}</b>
        <a href={api.file(d.id)} target="_blank" rel="noreferrer" title={`Open ${d.filename}`}>{d.filename}<Icon name="open" size={14} /></a>
      </div>
      {photo ? (
        <div className="photo">
          <img src={api.file(d.id)} alt={d.filename} loading="lazy" />
          <dl className="kv small">
            {d.kind === 'live_photo' ? <><dt>Taken</dt><dd>Live, in the Pramaan capture page</dd></> : <>
              <dt>GPS</dt><dd>{m.lat != null ? `${m.lat}, ${m.lng}` : 'none'}</dd>
              <dt>Taken</dt><dd>{m.taken || 'unknown'}</dd>
              <dt>Camera</dt><dd>{m.camera || 'unknown'}</dd>
              <dt>Saved by</dt><dd>{m.software || '—'}</dd></>}
            <dt>Fingerprint</dt><dd className="mono">{m.dhash ? parseInt(m.dhash, 2).toString(16).padStart(16, '0') : ''}</dd>
          </dl>
        </div>
      ) : (
        <>
          <div className="readby">Read from {m.read_method}{d.kind === 'fire_noc' && (m.qr ? <span className="tag green">Issuer QR found</span> : <span className="tag grey">No QR</span>)}</div>
          {fx?.type === 'pdf' && (
            <p className={`history ${fx.edited ? 'warn' : ''}`}><Icon name="clock" size={15} />
              <span><b>Edit history</b> {fx.history}</span></p>
          )}
          {fx?.type === 'image' && (
            <p className={`history ${fx.hotspots || fx.copies ? 'warn' : ''}`}><Icon name="shield" size={15} />
              <span><b>Scan check</b> {fx.hotspots || fx.copies ? `${fx.hotspots} hotspot${fx.hotspots === 1 ? '' : 's'}, ${fx.copies} copied patch${fx.copies === 1 ? '' : 'es'}` : 'no editing traces found'}</span></p>
          )}
          {f.length > 0 && <dl className="kv small">{f.map(([k, v]) => <React.Fragment key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{String(v)}</dd></React.Fragment>)}</dl>}
        </>
      )}
    </div>
  )
}

/* ---------------- live capture: map of the campus with each photo pinned ---------------- */
const Z = 16
const world = (lat, lng) => {
  const s = Math.sin(lat * Math.PI / 180)
  return [256 * 2 ** Z * (lng + 180) / 360, 256 * 2 ** Z * (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI))]
}

function CampusMap({ boundary, shots, campus }) {
  const [tilesOk, setTilesOk] = useState(true)
  const pts = [...(boundary || []), ...shots.filter(s => s.lat != null).map(s => [s.lat, s.lng])]
  if (!pts.length) return null
  const xy = pts.map(([a, b]) => world(a, b))
  const pad = 60
  let x0 = Math.min(...xy.map(p => p[0])) - pad, x1 = Math.max(...xy.map(p => p[0])) + pad
  let y0 = Math.min(...xy.map(p => p[1])) - pad, y1 = Math.max(...xy.map(p => p[1])) + pad
  const w = Math.max(x1 - x0, 360), h = Math.max(y1 - y0, 240)
  x0 = (x0 + x1) / 2 - w / 2; y0 = (y0 + y1) / 2 - h / 2
  const tiles = []
  for (let tx = Math.floor(x0 / 256); tx <= Math.floor((x0 + w) / 256); tx++)
    for (let ty = Math.floor(y0 / 256); ty <= Math.floor((y0 + h) / 256); ty++) tiles.push([tx, ty])
  const poly = (boundary || []).map(([a, b]) => world(a, b).map((v, i) => v - (i ? y0 : x0)).join(',')).join(' ')
  const mPerPx = 156543.03 * Math.cos((campus?.[0] || 11) * Math.PI / 180) / 2 ** Z
  const bar = 200 / mPerPx
  return (
    <figure className="campusmap">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Campus boundary with the location of each live photo">
        <rect width={w} height={h} fill="var(--map-bg)" />
        {tilesOk && tiles.map(([tx, ty]) => (
          <image key={`${tx}-${ty}`} href={`https://tile.openstreetmap.org/${Z}/${tx}/${ty}.png`} x={tx * 256 - x0} y={ty * 256 - y0}
            width="256" height="256" opacity="0.55" onError={() => setTilesOk(false)} />
        ))}
        {poly && <polygon points={poly} fill="rgba(43,47,148,0.10)" stroke="var(--ink)" strokeWidth="2" strokeDasharray="6 4" />}
        {shots.filter(s => s.lat != null).map((s, i) => {
          const [px, py] = world(s.lat, s.lng)
          const bad = Object.values(s.checks).some(v => v === false || v === 'missing' || v === 'flat')
          return (
            <g key={s.id} transform={`translate(${px - x0},${py - y0})`}>
              <title>{`${s.shot}: ${s.checks.inside === false ? `${s.outside_m} m outside the boundary` : 'inside the boundary'}`}</title>
              <circle r={Math.max(6, Math.min(40, s.accuracy / mPerPx))} fill={bad ? 'rgba(190,58,43,.15)' : 'rgba(29,122,76,.15)'} />
              <circle r="11" fill={bad ? 'var(--red)' : 'var(--green)'} stroke="#fff" strokeWidth="2.5" />
              <text y="4.5" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{i + 1}</text>
            </g>
          )
        })}
        <g transform={`translate(14,${h - 18})`}>
          <rect x="-6" y="-16" width={bar + 52} height="26" rx="4" fill="rgba(255,255,255,.85)" />
          <line x1="0" x2={bar} y1="0" y2="0" stroke="var(--text)" strokeWidth="2" />
          <text x={bar + 6} y="4" fontSize="11" fill="var(--text)">200 m</text>
        </g>
      </svg>
      <figcaption>Dashed line: surveyed campus boundary. Pins: where each live photo was taken.{tilesOk ? ' Map © OpenStreetMap contributors.' : ''}</figcaption>
    </figure>
  )
}

function LiveCapture({ id, onNewShot }) {
  const { officer } = useOfficer()
  const [info, reload] = useLoad(() => api.captureInfo(id), [id])
  const [busy, setBusy] = useState(false)
  const count = useRef(null)
  useEffect(() => {
    const open = info?.sessions?.some(s => s.open)
    if (!open) return
    const t = setInterval(reload, 4000)  // pins appear while the college is taking photos
    return () => clearInterval(t)
  }, [info, reload])
  useEffect(() => {
    if (!info) return
    if (count.current !== null && info.shots.length !== count.current) onNewShot()
    count.current = info.shots.length
  }, [info]) // eslint-disable-line
  if (!info) return null
  const start = async () => { setBusy(true); await api.captureStart(id, officer); await reload(); setBusy(false) }
  const cur = info.sessions[0]
  return (
    <section className="sheet capture">
      <div className="capture-head">
        <div>
          <h2><span className="h-ico"><Icon name="camera" size={16} /></span>Live photo capture</h2>
          <p className="muted">Photos taken through Pramaan's camera page, with GPS, time and a one-time code in every shot.</p>
        </div>
        <button className="btn quiet" disabled={busy} onClick={start}><Icon name="camera" size={16} />Start a surprise session</button>
      </div>
      {cur && (
        <div className="session">
          <div className="session-code">
            <small>One-time code</small>
            <b>{cur.code}</b>
            <span className={`tag ${cur.open ? 'green' : 'grey'}`}>{cur.open ? `Open, ${cur.minutes_left} min left` : `Closed ${cur.expires}`}</span>
            {cur.surprise && <span className="tag purple">Surprise</span>}
          </div>
          {cur.open && (
            <div className="session-link">
              <img src={api.qr(cur.link)} alt="QR code of the capture link" width="104" height="104" />
              <div>
                <p>College staff open this link on a phone, then photograph each place holding up a card with the code.</p>
                <a className="link" href={cur.link} target="_blank" rel="noreferrer">{cur.link}</a>
                {info.loopback_only && <p className="hint">Phones cannot reach this computer yet. Start Pramaan with the phone option (HTTPS) and open it from the address shown there.</p>}
              </div>
            </div>
          )}
        </div>
      )}
      {info.shots.length > 0 ? (
        <div className="capture-body">
          <CampusMap boundary={info.boundary} shots={info.shots} campus={info.campus} />
          <ol className="shots">
            {info.shots.map((s, i) => (
              <li key={s.id}>
                <img src={api.file(s.doc_id)} alt={s.shot} loading="lazy" />
                <div>
                  <b><span className="num-pin">{i + 1}</span>{s.shot}</b>
                  <small>{s.taken} · GPS ±{s.accuracy} m</small>
                  <div className="checks">
                    <Check state={s.checks.inside} label="Inside campus" detail={s.checks.inside === false ? `${s.outside_m} m outside` : ''} />
                    <Check state={s.checks.time} label="On time" detail={s.late_min ? `${s.late_min} min late` : ''} />
                    <Check state={s.checks.code === 'unchecked' ? null : s.checks.code} label="Code" detail={s.checks.code === 'unchecked' ? 'OCR not installed' : s.code_read} />
                    <Check state={s.checks.unique} label="Unique" />
                    <Check state={s.checks.live === 'unclear' ? null : s.checks.live} label="Real room" detail={s.live_detail} />
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : <p className="empty">No live photos yet. They appear here, pinned on the campus map, as soon as the college takes them.</p>}
      {info.boundary_source && <p className="hint">Boundary: {info.boundary_source}</p>}
    </section>
  )
}

/* ---------------- reports ---------------- */
function Reports({ a, onMade }) {
  const { officer } = useOfficer()
  const [busy, setBusy] = useState(null)
  const make = async kind => {
    setBusy(kind)
    try { const r = await api.report(a.id, kind, officer); window.open(api.reportPdf(r.id), '_blank'); await onMade() } finally { setBusy(null) }
  }
  return (
    <div className="sheet">
      <h2><span className="h-ico"><Icon name="doc" size={16} /></span>Reports</h2>
      <p className="muted">Signed PDFs. The QR code on each one opens a page that confirms it has not been changed.</p>
      <div className="btns">
        <button className="btn primary" disabled={!!busy} onClick={() => make('internal')}><Icon name="doc" size={16} />{busy === 'internal' ? 'Building…' : 'Scrutiny report'}</button>
        <button className="btn quiet" disabled={!!busy} onClick={() => make('college')}>{busy === 'college' ? 'Building…' : 'Query letter to college'}</button>
      </div>
      {a.reports.length > 0 && (
        <ul className="reports">
          {a.reports.map(r => (
            <li key={r.id}>
              <a href={api.reportPdf(r.id)} target="_blank" rel="noreferrer">{r.kind === 'college' ? 'Query letter' : 'Scrutiny report'} {r.id}</a>
              <span>{r.created}, {r.officer} · <a href={`#verify/${r.id}`}>check</a></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function CaseView({ id }) {
  const { officer } = useOfficer()
  const [a, reload, err] = useLoad(() => api.app(id), [id])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  if (!a) return <Loading error={err} />
  const decide = async d => { setBusy(true); await api.decide(a.id, d, note, officer); setNote(''); await reload(); setBusy(false) }
  const outcome = async o => { setBusy(true); await api.inspection(a.id, o, officer); await reload(); setBusy(false) }
  const rerun = async () => { setBusy(true); await api.reprocess(a.id); await reload(); setBusy(false) }
  const scored = a.findings.filter(f => f.weight > 0 && !f.dismissed)
  const info = a.findings.filter(f => f.weight === 0)
  const dismissed = a.findings.filter(f => f.dismissed)
  const shared = a.faculty.filter(f => f.elsewhere > 0 || f.sms === 'no')
  const sm = a.summary
  return (
    <>
      <a className="back" href="#queue"><Icon name="back" size={16} />Application queue</a>
      <header className={`cover lane-${a.lane === 'Inspect' ? 'red' : a.lane === 'Review' ? 'amber' : 'green'}`}>
        <Microtext text={`FILE ${a.id} · ${a.institution.toUpperCase()} · AICTE · PRAMAAN · `} />
        <Guilloche kind="rosette" w={600} className="cover-rosette" />
        <div className="cover-main">
          <div className="filecode">File {a.id}<span>Institution code {a.code}</span><span>Assigned to {a.officer || '—'}</span></div>
          <h1>{a.institution}</h1>
          <dl className="facts-row">
            <div><dt>Category</dt><dd>{a.category}</dd></div>
            <div><dt>Programme</dt><dd>{a.programme}</dd></div>
            <div><dt>Intake</dt><dd>{a.intake}</dd></div>
            <div><dt>District</dt><dd>{a.district}</dd></div>
            <div><dt>Academic year</dt><dd>{a.academic_year}</dd></div>
          </dl>
          <p className="checked-with">Checked with rulebook {a.rule_version}. {scored.length} flagged{info.length ? `, ${info.length} for information` : ''}{dismissed.length ? `, ${dismissed.length} dismissed` : ''}.</p>
        </div>
        <Stamp lane={a.lane} risk={a.risk} animate />
      </header>

      <section className="summary" aria-label="Summary in plain language">
        <Guilloche h={300} lines={16} seed={3} />
        <h2>In plain words</h2>
        <p className="summary-head">{sm.headline}</p>
        {sm.items.length > 0 && (
          <ol>{sm.items.map((it, i) => <li key={i} className={it.serious ? 'serious' : ''}>{it.text}</li>)}</ol>
        )}
        {sm.next_step && <p className="summary-next">{sm.next_step}</p>}
        <p className="hint">Written from fixed sentence templates in the rulebook, so the same findings always read the same way.</p>
      </section>

      <div className="cols">
        <section>
          <h2 className="section-title">Findings</h2>
          {a.findings.length === 0 && <div className="sheet allclear"><Icon name="check" size={22} />No problems found. This application is eligible for fast track.</div>}
          {[...scored, ...info, ...dismissed].map((f, i) => <Finding key={`${f.rule}-${i}`} f={f} appId={a.id} onChange={reload} />)}
          <LiveCapture id={a.id} onNewShot={reload} />
        </section>

        <aside className="rail">
          <div className="sheet decide">
            <h2><span className="h-ico"><Icon name="gavel" size={16} /></span>Your decision</h2>
            <p className="muted">Pramaan only advises. The decision is yours, and it is written to the activity log as {officer || 'you'}.</p>
            <div className="row">Current status <DecisionTag d={a.decision} /></div>
            {a.decided_by && <p className="muted small">by {a.decided_by}, {a.decided_at}</p>}
            {a.decision_note && <p className="note">“{a.decision_note}”</p>}
            {a.decision === 'inspect' && (
              <div className="outcome">
                <b>Inspection result</b>
                {a.inspection_outcome ? (
                  <p>{a.inspection_outcome === 'confirmed' ? 'Problem confirmed on site.' : 'No problem found on site.'}</p>
                ) : <p className="muted small">Record what the inspection found. This feeds the accuracy figures on the region dashboard.</p>}
                <div className="btns">
                  <button className={`btn small ${a.inspection_outcome === 'confirmed' ? 'red' : 'quiet'}`} disabled={busy} onClick={() => outcome('confirmed')}>Problem confirmed</button>
                  <button className={`btn small ${a.inspection_outcome === 'no_problem' ? 'green' : 'quiet'}`} disabled={busy} onClick={() => outcome('no_problem')}>No problem found</button>
                </div>
              </div>
            )}
            <textarea placeholder="Note for the record (optional)" value={note} onChange={e => setNote(e.target.value)} />
            <div className="btns">
              <button className="btn green" disabled={busy} onClick={() => decide('approve')}>Approve</button>
              <button className="btn amber" disabled={busy} onClick={() => decide('query')}>Send query</button>
              <button className="btn red" disabled={busy} onClick={() => decide('inspect')}>Order inspection</button>
            </div>
            <button className="btn quiet" disabled={busy} onClick={rerun}>{busy ? 'Working…' : 'Re-run all checks'}</button>
          </div>

          <Reports a={a} onMade={reload} />

          <div className="sheet">
            <h2><span className="h-ico"><Icon name="folder" size={16} /></span>Documents</h2>
            {a.documents.map(d => <Doc key={d.id} d={d} />)}
          </div>

          <div className="sheet">
            <h2><span className="h-ico"><Icon name="users" size={16} /></span>Faculty <span className="muted">({a.faculty.length} declared)</span></h2>
            {shared.length === 0 ? <p className="muted">No teacher is listed by another institution.</p> : (
              <div className="table-wrap"><table className="grid compact">
                <thead><tr><th>Teacher</th><th>PAN</th><th>Other colleges</th><th>Answer</th></tr></thead>
                <tbody>
                  {shared.map((f, i) => (
                    <tr key={i}>
                      <td>{f.name}<div className="muted">{f.designation}</div></td>
                      <td className="mono">{f.pan}</td>
                      <td className="num">{f.elsewhere}</td>
                      <td><span className={`tag ${f.sms === 'no' ? 'red' : f.sms === 'yes' ? 'green' : 'grey'}`}>{f.sms === 'no' ? (f.channel === 'portal-misuse' ? 'Misuse reported' : 'Denied') : f.sms === 'yes' ? 'Confirmed' : 'Waiting'}</span>
                        {f.channel?.startsWith('portal') && <div className="muted small">via portal</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            )}
          </div>

          <div className="sheet">
            <h2><span className="h-ico"><Icon name="shield" size={16} /></span>Verified facts</h2>
            <p className="muted">Checked once, reused every year. A change is flagged.</p>
            <dl className="kv small">
              {a.facts.map((f, i) => <React.Fragment key={i}><dt>{f.key}</dt><dd><b>{f.value}</b><div className="muted">{f.source} · {f.verified_on}</div></dd></React.Fragment>)}
            </dl>
          </div>

          <div className="sheet">
            <h2><span className="h-ico"><Icon name="history" size={16} /></span>History</h2>
            <ol className="trail">
              {a.trail.slice(-12).map((t, i) => <li key={i}><b>{t.action}</b><span>{t.actor}, {t.ts}</span></li>)}
            </ol>
            <a className="link" href="#audit">Open the full activity log</a>
          </div>
        </aside>
      </div>
    </>
  )
}
