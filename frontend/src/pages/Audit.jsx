import React, { useState } from 'react'
import { api } from '../api.js'
import { Icon, Loading, PageHead, useLoad } from '../ui.jsx'

export default function Audit() {
  const [rows, reload, err] = useLoad(api.audit)
  const [check, setCheck] = useState(null)
  const [busy, setBusy] = useState(false)
  if (!rows) return <Loading error={err} />
  const verify = async () => setCheck(await api.verify())
  const tamper = async () => { await api.tamper(); await reload(); setCheck(await api.verify()) }
  const reset = async () => {
    if (!window.confirm('Rebuild the demo data? Your test submissions and decisions will be cleared.')) return
    setBusy(true); await api.reset(); setCheck(null); await reload(); setBusy(false)
  }
  return (
    <>
      <PageHead title="Activity log" icon="chain" aside={
        <div className="btns">
          <button className="btn primary" onClick={verify}><Icon name="chain" size={16} />Verify the chain</button>
          <button className="btn quiet danger" onClick={tamper}>Demo: edit an old entry</button>
          <button className="btn quiet" disabled={busy} onClick={reset}>{busy ? 'Rebuilding…' : 'Reset demo data'}</button>
        </div>
      }>
        Every check, SMS reply and officer decision is written here. Each entry carries the SHA-256 fingerprint of the entry before it, so quietly editing an old entry breaks the chain.
      </PageHead>
      {check && (
        <div className={`banner ${check.ok ? 'good' : 'bad'}`} role="status">
          <span className="banner-ico"><Icon name={check.ok ? 'check' : 'cross'} size={22} /></span>
          <span>{check.message}{check.broken_at ? ` (“${check.action}”)` : ''}</span>
        </div>
      )}
      <div className="sheet table-wrap">
        <table className="grid compact audit">
          <thead><tr><th>#</th><th>Time</th><th>Who</th><th>What</th><th>Application</th><th>Details</th><th>Fingerprint</th></tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} className={check && check.broken_at === r.id ? 'broken' : ''}>
                <td className="num">{r.id}</td>
                <td className="ts">{r.ts}</td>
                <td>{r.actor}</td>
                <td><b>{r.action}</b></td>
                <td className="appcell">{r.application ? <a href={`#case/${r.application}`}>{r.application}</a> : '—'}</td>
                <td className="muted small">{Object.entries(r.payload).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.length + ' items' : v}`).join(' · ')}</td>
                <td className="hash" title={`previous: ${r.prev}`}><span>{r.hash.slice(0, 10)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
