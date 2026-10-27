import React, { useState } from 'react'
import { api } from '../api.js'
import { go } from '../App.jsx'
import { Icon, PageHead, Stamp } from '../ui.jsx'

const DEMOS = {
  KAV: { code: 'KAV', name: 'Kaveri Institute of Engineering', district: 'Salem', lat: '11.6643', lng: '78.146', intake: '120',
    category: 'Extension of Approval', programme: 'UG Engineering' },
  AMA: { code: 'AMA', name: 'Amaravathi College of Engineering', district: 'Karur', lat: '10.9601', lng: '78.0766', intake: '180',
    category: 'Extension of Approval', programme: 'UG Engineering' },
}
const EMPTY = { code: '', name: '', district: '', lat: '', lng: '', intake: '', category: 'Extension of Approval', programme: 'UG Engineering' }

function FileDrop({ label, hint, accept, multiple, picked, onChange }) {
  const names = Array.isArray(picked) ? picked.map(f => f.name) : picked ? [picked.name] : []
  return (
    <label className={`file ${names.length ? 'has' : ''}`}>
      <span className="file-ico"><Icon name={names.length ? 'check' : 'upload'} size={20} /></span>
      <span className="file-text">
        <b>{label}</b>
        <small>{names.length ? names.join(', ') : hint}</small>
      </span>
      <span className="file-btn">{names.length ? 'Change' : 'Choose file'}</span>
      <input type="file" accept={accept} multiple={multiple} onChange={onChange} />
    </label>
  )
}

function Checklist({ r }) {
  return (
    <div className="sheet checklist">
      <h2>{r.passed === r.total ? 'Ready to submit' : `${r.total - r.passed} thing${r.total - r.passed > 1 ? 's' : ''} to fix before you apply`}</h2>
      <p className="muted">{r.passed} of {r.total} checks passed. Nothing was submitted and AICTE officers do not see practice checks.</p>
      <ul>
        {r.items.map(i => (
          <li key={i.rule} className={i.ok ? 'ok' : 'bad'}>
            <span className="cl-ico"><Icon name={i.ok ? 'check' : 'cross'} size={15} /></span>
            <div><b>{i.label}</b>{i.tips.map((t, k) => <p key={k}>{t}</p>)}</div>
          </li>
        ))}
      </ul>
      <p className="hint">{r.runs_left} of {r.limit} practice checks left today for this college. Practice checks cover compliance only; document authenticity is checked when you submit.</p>
    </div>
  )
}

function CaptureCard({ c }) {
  return (
    <div className="sheet capture-card">
      <h2>Next: live photos</h2>
      <p>Open this link on a phone at the campus within {c.minutes_left} minutes and photograph each place below, holding up a card with the code.</p>
      <div className="session-code"><small>One-time code</small><b>{c.code}</b></div>
      <div className="session-link">
        <img src={api.qr(c.link)} alt="QR code of the capture link" width="112" height="112" />
        <ul className="plain">{c.shots.map(x => <li key={x}>{x}</li>)}</ul>
      </div>
      <a className="link" href={c.link} target="_blank" rel="noreferrer">{c.link}</a>
    </div>
  )
}

export default function Submit({ mode = 'submit' }) {
  const practice = mode === 'practice'
  const [v, setV] = useState(EMPTY)
  const [files, setFiles] = useState({ fire_noc: null, land_doc: null, faculty_list: null, lab_photos: [] })
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const set = k => e => setV({ ...v, [k]: e.target.value })
  const pick = k => e => setFiles({ ...files, [k]: k === 'lab_photos' ? [...e.target.files] : e.target.files[0] })

  const send = async e => {
    e.preventDefault()
    setBusy(true); setErr(null); setRes(null)
    const fd = new FormData()
    Object.entries(v).forEach(([k, val]) => val !== '' && fd.append(k, val))
    ;['fire_noc', 'land_doc', 'faculty_list'].forEach(k => files[k] && fd.append(k, files[k]))
    files.lab_photos.forEach(f => fd.append('lab_photos', f))
    try { setRes(await (practice ? api.practice(fd) : api.submit(fd))) } catch (x) { setErr(x.message) }
    setBusy(false)
  }

  return (
    <>
      <PageHead title={practice ? 'Practice check' : 'Submit an application'} icon={practice ? 'check' : 'upload'} aside={
        <div className="btns">
          <button className="btn quiet" onClick={() => setV(DEMOS.KAV)}>Fill Kaveri details</button>
          {!practice && <button className="btn quiet" onClick={() => setV(DEMOS.AMA)}>Fill Amaravathi details</button>}
        </div>}>
        {practice
          ? 'Check your documents before you apply. The same engine runs, but nothing is submitted and officers do not see it. You get a checklist with what to fix.'
          : 'This is what a college sees. Upload the documents and Pramaan checks them within seconds, before any officer opens the file.'}
      </PageHead>
      <div className="cols wide-left">
        <form className="sheet form" onSubmit={send}>
          <h2>Institution</h2>
          <div className="formgrid">
            <label>AICTE code<input required value={v.code} onChange={set('code')} placeholder="e.g. KAV" /></label>
            <label className="span2">Institution name<input required value={v.name} onChange={set('name')} /></label>
            <label>District<input value={v.district} onChange={set('district')} /></label>
            <label>Campus latitude<input value={v.lat} onChange={set('lat')} placeholder="11.6643" /></label>
            <label>Campus longitude<input value={v.lng} onChange={set('lng')} placeholder="78.146" /></label>
            <label>Category
              <select value={v.category} onChange={set('category')}>
                <option>Extension of Approval</option><option>New institution</option><option>Change in intake</option>
              </select>
            </label>
            <label>Programme<input value={v.programme} onChange={set('programme')} /></label>
            <label>Total student intake<input required type="number" min="1" value={v.intake} onChange={set('intake')} /></label>
          </div>
          <h2>Documents</h2>
          <div className="formgrid">
            <FileDrop label="Fire NOC" hint="PDF or image" accept=".pdf,image/*" picked={files.fire_noc} onChange={pick('fire_noc')} />
            <FileDrop label="Land document" hint="PDF or scan" accept=".pdf,image/*" picked={files.land_doc} onChange={pick('land_doc')} />
            <FileDrop label="Faculty list" hint="CSV with name, designation, pan, phone" accept=".csv,.txt" picked={files.faculty_list} onChange={pick('faculty_list')} />
            <FileDrop label="Lab and building photos" hint="Original camera photos, several allowed" accept="image/*" multiple picked={files.lab_photos} onChange={pick('lab_photos')} />
          </div>
          <button className="btn primary big" disabled={busy}>{busy ? 'Checking documents…' : practice ? 'Run practice check' : 'Submit and check'}</button>
          {err && <p className="error">{err}</p>}
        </form>
        <aside>
          {res && practice ? <Checklist r={res} /> : res ? (
            <>
              <div className="sheet result">
                <h2>Checked</h2>
                <p>Application <b>{res.id}</b> has been read and scored.</p>
                <Stamp lane={res.lane} risk={res.risk} animate />
                <button className="btn primary" onClick={() => go(`case/${res.id}`)}>See every finding</button>
              </div>
              {res.capture && <CaptureCard c={res.capture} />}
            </>
          ) : practice ? (
            <div className="sheet guide">
              <h2>What a practice check covers</h2>
              <ul className="steps">
                <li>Every required document is there and readable</li>
                <li>The Fire NOC is valid for the coming academic year</li>
                <li>Enough faculty for your intake</li>
                <li>Teachers not listed by another institution</li>
                <li>Photos are original camera photos</li>
              </ul>
              <p className="hint">Authenticity checks (signatures, edit detection, photo fingerprints) only run on a real submission, so a forged document cannot be tried again and again. Up to 5 practice checks a day.</p>
            </div>
          ) : (
            <div className="sheet guide">
              <h2>Try it live</h2>
              <ol className="steps">
                <li>Click <b>Fill demo college details</b>.</li>
                <li>Pick the files from the folder <code>sample_documents/Kaveri_Institute_upload_demo</code>.</li>
                <li>Submit. Pramaan reads the NOC, checks its QR with the issuer, compares teachers and photos with all other colleges, and gives a lane.</li>
              </ol>
              <p className="hint">This sample hides three problems: a NOC dated on a Sunday, a teacher already listed by two other colleges, and a lab photo copied from another college.</p>
              <h2>Edit detection</h2>
              <p>Click <b>Fill Amaravathi details</b> and upload the files in <code>sample_documents/Amaravathi_tampered_upload_demo</code>. Its NOC QR is stained, so the issuer cannot be asked; the file itself shows the expiry date was changed.</p>
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
