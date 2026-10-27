import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Icon } from '../ui.jsx'
import { Seal } from '../App.jsx'

/* Opened from the QR code on a report: confirms Pramaan issued it and nothing was changed. */
export default function Verify({ id }) {
  const [r, setR] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.reportVerify(id).then(setR).catch(e => setErr(e.message)) }, [id])
  const check = async e => {
    const f = e.target.files[0]
    if (!f) return
    setBusy(true)
    try { setR(await api.reportVerifyFile(id, f)) } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  const p = r?.payload || {}
  const kind = { internal: 'Scrutiny report', college: 'Query letter', teacher: 'Employment claims statement' }[r?.kind] || 'Report'
  return (
    <div className="cap verify">
      <header className="cap-brand"><span className="seal"><Seal size={28} /></span><b>Pramaan report check</b></header>
      {!r && !err && <div className="cap-card"><p>Checking…</p></div>}
      {err && <div className="cap-card"><p className="error">{err}</p></div>}
      {r && (
        <>
          <div className={`verdict ${r.genuine ? 'good' : 'bad'}`} role="status">
            <span className="banner-ico"><Icon name={r.genuine ? 'check' : 'cross'} size={30} /></span>
            <div>
              <b>{r.genuine ? 'Report genuine' : r.found ? 'Do not trust this report' : 'Report not found'}</b>
              <p>{r.message}</p>
            </div>
          </div>
          {r.found && (
            <div className="cap-card">
              <h2>{kind} {r.id}</h2>
              <dl className="kv">
                {p.application && <><dt>Application</dt><dd>{p.application}</dd></>}
                {p.institution && <><dt>Institution</dt><dd>{p.institution}</dd></>}
                {p.teacher && <><dt>Teacher</dt><dd>{p.teacher} ({p.pan})</dd></>}
                <dt>Issued</dt><dd>{p.created}{p.officer ? ` by ${p.officer}` : ''}</dd>
                {p.risk != null && <><dt>Risk and lane</dt><dd>{p.risk} of 100, {p.lane}</dd></>}
                {p.decision && <><dt>Decision then</dt><dd>{p.decision}</dd></>}
                {p.rule_version && <><dt>Rulebook</dt><dd>{p.rule_version}</dd></>}
              </dl>
              {p.summary && <p className="verify-sum">{p.summary}</p>}
              {p.claims && <ul className="plain">{p.claims.map((c, i) => <li key={i}>{c.year}: {c.institution} — {c.answer}</li>)}</ul>}
              {p.documents && (
                <>
                  <h3>Documents it covers</h3>
                  <ul className="plain">{p.documents.map((d, i) => <li key={i}>{d.file}<code>{d.sha256.slice(0, 24)}…</code></li>)}</ul>
                </>
              )}
              <label className="filecheck">
                <b>{busy ? 'Checking the file…' : 'Have the PDF? Check that exact file'}</b>
                <small>Its SHA-256 fingerprint is compared with the one recorded when the report was issued.</small>
                <input type="file" accept="application/pdf" onChange={check} />
              </label>
              {r.file_sha256 && <p className={r.file_matches ? 'okmsg' : 'error'}>File fingerprint {r.file_sha256.slice(0, 24)}… {r.file_matches ? 'matches.' : 'does not match.'}</p>}
              <p className="hint">Signature: Ed25519, Pramaan public key <code>{r.public_key.slice(0, 20)}…</code></p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
