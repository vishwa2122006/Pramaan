import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Loading, PageHead, Sev, useLoad } from '../ui.jsx'

export default function Rules() {
  const [d, reload, err] = useLoad(api.rules)
  const [draft, setDraft] = useState(null)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (d) setDraft(JSON.parse(JSON.stringify(d.active))) }, [d])
  if (!d || !draft) return <Loading error={err} />
  const setTop = (k, v) => setDraft({ ...draft, [k]: v })
  const setRule = (id, k, v) => setDraft({ ...draft, rules: { ...draft.rules, [id]: { ...draft.rules[id], [k]: v } } })
  const save = async () => {
    setBusy(true)
    const r = await api.saveRules(draft, note)
    setMsg(`Saved as ${r.version}. Every application was re-checked with the new rules.`)
    setNote(''); await reload(); setBusy(false)
  }
  return (
    <>
      <PageHead title="Rulebook" icon="rules" aside={<div className="meta"><span>Active version <b>{d.active.version}</b></span></div>}>
        AICTE norms and risk weights are settings, not code. Each change becomes a new version, and every case records which version checked it. The weights here are example values; AICTE would set the real ones.
      </PageHead>
      <div className="cols wide-left">
        <div className="sheet">
          <h2>Thresholds</h2>
          <div className="formgrid">
            <label>Students per teacher<input type="number" value={draft.faculty_student_ratio} onChange={e => setTop('faculty_student_ratio', +e.target.value)} /></label>
            <label>Photo match limit (bits of 64)<input type="number" value={draft.photo_match_threshold} onChange={e => setTop('photo_match_threshold', +e.target.value)} /></label>
            <label>Photo distance limit (km)<input type="number" value={draft.photo_gps_radius_km} onChange={e => setTop('photo_gps_radius_km', +e.target.value)} /></label>
            <label>Academic year starts<input value={draft.academic_year_start} onChange={e => setTop('academic_year_start', e.target.value)} /></label>
            <label>Inspect lane from score<input type="number" value={draft.lanes.inspect} onChange={e => setTop('lanes', { ...draft.lanes, inspect: +e.target.value })} /></label>
            <label>Review lane from score<input type="number" value={draft.lanes.review} onChange={e => setTop('lanes', { ...draft.lanes, review: +e.target.value })} /></label>
          </div>
          <h2>Checks</h2>
          <div className="table-wrap"><table className="grid compact rules">
            <thead><tr><th>On</th><th>Rule</th><th>Check</th><th>Severity</th><th>Weight</th></tr></thead>
            <tbody>
              {Object.entries(draft.rules).map(([id, r]) => (
                <tr key={id} className={r.enabled === false ? 'off' : ''}>
                  <td><label className="switch"><input type="checkbox" aria-label={`Use rule ${id}`} checked={r.enabled !== false} onChange={e => setRule(id, 'enabled', e.target.checked)} /><i /></label></td>
                  <td className="rule">{id}</td>
                  <td>{r.title}</td>
                  <td><Sev s={r.severity} /></td>
                  <td><input className="w" aria-label={`Weight for ${id}`} type="number" value={r.weight} onChange={e => setRule(id, 'weight', +e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <div className="row gap">
            <input className="grow" placeholder="Why are you changing this? (saved in the log)" value={note} onChange={e => setNote(e.target.value)} />
            <button className="btn primary" disabled={busy} onClick={save}>{busy ? 'Re-checking…' : 'Save as new version'}</button>
          </div>
          {msg && <p className="okmsg">{msg}</p>}
        </div>
        <div className="sheet">
          <h2>Versions</h2>
          <ul className="versions">
            {d.versions.map(v => (
              <li key={v.id} className={v.active ? 'on' : ''}><b>{v.version}</b><span className="muted">{v.created}{v.note ? ` · ${v.note}` : ''}</span></li>
            ))}
            <li className={d.versions.length === 0 ? 'on' : ''}><b>{d.active.version.split(' v')[0]} v1</b><span className="muted">built-in default</span></li>
          </ul>
        </div>
      </div>
    </>
  )
}
