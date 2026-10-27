import React, { useState } from 'react'
import { api } from '../api.js'
import { go } from '../App.jsx'
import { Icon, Lane, Loading, PageHead, laneTone, useLoad } from '../ui.jsx'

// Tamil Nadu's 38 districts as equal tiles, placed roughly where they are (north at the top).
const DISTRICTS = [
  ['Krishnagiri', 3, 0], ['Tirupathur', 4, 0], ['Vellore', 5, 0], ['Ranipet', 6, 0], ['Tiruvallur', 7, 0], ['Chennai', 8, 0],
  ['Dharmapuri', 3, 1], ['Tiruvannamalai', 5, 1], ['Kanchipuram', 6, 1], ['Chengalpattu', 7, 1],
  ['Nilgiris', 0, 2], ['Erode', 1, 2], ['Salem', 3, 2], ['Kallakurichi', 4, 2], ['Villupuram', 5, 2], ['Cuddalore', 6, 2],
  ['Coimbatore', 0, 3], ['Tiruppur', 1, 3], ['Namakkal', 2, 3], ['Perambalur', 3, 3], ['Ariyalur', 4, 3], ['Mayiladuthurai', 5, 3],
  ['Karur', 2, 4], ['Tiruchirappalli', 3, 4], ['Thanjavur', 4, 4], ['Tiruvarur', 5, 4], ['Nagapattinam', 6, 4],
  ['Dindigul', 2, 5], ['Pudukkottai', 4, 5],
  ['Theni', 1, 6], ['Madurai', 2, 6], ['Sivaganga', 3, 6], ['Ramanathapuram', 4, 6],
  ['Tenkasi', 1, 7], ['Virudhunagar', 2, 7],
  ['Tirunelveli', 1, 8], ['Thoothukudi', 2, 8],
  ['Kanniyakumari', 1, 9],
]
const SHORT = { Tiruvannamalai: 'T.malai', Tiruchirappalli: 'Trichy', Kanniyakumari: 'K.kumari', Ramanathapuram: 'R.puram',
  Mayiladuthurai: 'Mayiladu.', Chengalpattu: 'Chengalpet', Kallakurichi: 'Kallakuri.', Virudhunagar: 'Virudhu.', Nagapattinam: 'Nagai' }
// one hue, light to dark, for average risk
const STEPS = [[0, '#F5E1DC', 'under 20'], [20, '#E7AC9F', '20–49'], [50, '#CF6F5C', '50–79'], [80, '#9C3324', '80 and over']]
const shade = r => [...STEPS].reverse().find(s => r >= s[0])
const TW = 74, TH = 46, GAP = 4

function DistrictMap({ data, sel, onSel }) {
  const W = 9 * (TW + GAP), H = 10 * (TH + GAP)
  return (
    <figure className="tilemap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Tamil Nadu districts coloured by average risk score">
        {DISTRICTS.map(([name, c, r]) => {
          const d = data[name]
          const st = d ? shade(d.avg_risk) : null
          const x = c * (TW + GAP), y = r * (TH + GAP)
          const dark = d && d.avg_risk >= 50
          return (
            <g key={name} className={`tile ${d ? 'has' : ''} ${sel === name ? 'sel' : ''}`} transform={`translate(${x},${y})`}
              onClick={() => d && onSel(name)} tabIndex={d ? 0 : -1} role={d ? 'button' : undefined}
              onKeyDown={e => d && (e.key === 'Enter' || e.key === ' ') && onSel(name)}
              aria-label={d ? `${name}: ${d.colleges.length} college${d.colleges.length > 1 ? 's' : ''}, average risk ${d.avg_risk}` : undefined}>
              <title>{d ? `${name}\n${d.colleges.length} college(s), average risk ${d.avg_risk}` : `${name}: no applications`}</title>
              <rect width={TW} height={TH} rx="4" fill={st ? st[1] : 'var(--tile-empty)'} stroke={sel === name ? 'var(--ink-deep)' : st ? 'none' : 'var(--line)'} strokeWidth={sel === name ? 3 : 1} />
              <text x="7" y="18" fontSize="12.5" fontWeight="600" fill={dark ? '#fff' : d ? 'var(--text)' : 'var(--muted)'}>{SHORT[name] || name}</text>
              {d && <text x="7" y="38" fontSize="16" fontWeight="700" fill={dark ? '#fff' : 'var(--text)'}>{d.avg_risk}</text>}
            </g>
          )
        })}
      </svg>
      <figcaption className="legend">
        {STEPS.map(([v, c, l]) => <span key={v}><i className="sw-box" style={{ background: c }} />{l}</span>)}
        <span><i className="sw-box empty" />no applications</span>
      </figcaption>
    </figure>
  )
}

function Bars({ rows }) {
  const max = Math.max(...rows.map(r => r.count), 1)
  return (
    <ul className="hbars">
      {rows.map(r => (
        <li key={r.rule} title={`${r.title}: ${r.count} flag${r.count > 1 ? 's' : ''} in ${r.apps} application${r.apps > 1 ? 's' : ''}`}>
          <span className="hb-label">{r.title}<small>{r.rule}</small></span>
          <span className="hb-track"><i style={{ width: `${(100 * r.count) / max}%` }} /></span>
          <b>{r.count}</b>
        </li>
      ))}
    </ul>
  )
}

export default function Dashboard() {
  const [d, , err] = useLoad(api.dashboard)
  const [sel, setSel] = useState(null)
  if (!d) return <Loading error={err} />
  const t = d.tiles
  const a = d.accuracy
  const total = Math.max(t.received, 1)
  const pick = sel && d.districts[sel]
  const maxPending = Math.max(...d.officers.map(o => o.pending), 1)
  return (
    <>
      <PageHead title="Region dashboard" icon="chart"
        aside={<div className="meta"><span>Southern region</span><span>Academic year <b>{d.academic_year}</b></span></div>}
        extra={
          <>
            <div className="glass-row five">
              <div className="glass neutral"><span className="glass-ico"><Icon name="folder" size={18} /></span><b>{t.received}</b><span>Applications received</span></div>
              <div className="glass neutral"><span className="glass-ico"><Icon name="shield" size={18} /></span><b>{t.checked}</b><span>Checked by Pramaan</span></div>
              <div className="glass neutral"><span className="glass-ico"><Icon name="gavel" size={18} /></span><b>{t.decided}</b><span>Decided by officers</span></div>
              <div className="glass neutral"><span className="glass-ico"><Icon name="clock" size={18} /></span><b>{t.avg_days ?? '—'}</b><span>Average days to decide</span></div>
              <div className={`glass ${t.pending_15 ? 'lane-amber' : 'neutral'}`}><span className="glass-ico"><Icon name="alert" size={18} /></span><b>{t.pending_15}</b><span>Pending over 15 days</span></div>
            </div>
            <div className="mast-split">
              <div className="triage-bar" aria-hidden="true">
                {['Inspect', 'Review', 'Fast track'].map(l => t.lanes[l] > 0 && <i key={l} className={laneTone(l)} style={{ flexGrow: t.lanes[l] / total }} />)}
              </div>
              <p className="lanes-legend">{['Inspect', 'Review', 'Fast track'].map(l => <span key={l}><Lane lane={l} /> {t.lanes[l]}</span>)}</p>
            </div>
          </>
        }>
        Where the problems are, whether Pramaan's flags hold up, and who has too many files.
      </PageHead>

      <div className="dash-grid">
        <section className="sheet">
          <h2><span className="h-ico"><Icon name="map" size={16} /></span>Average risk by district</h2>
          <p className="muted">Select a district to see its colleges.</p>
          <DistrictMap data={d.districts} sel={sel} onSel={setSel} />
          {pick && (
            <div className="district-list">
              <h3>{sel}</h3>
              <ul>
                {pick.colleges.map(c => (
                  <li key={c.id}><a href={`#case/${c.id}`}>{c.name}</a><span><Lane lane={c.lane} /> {c.risk}</span></li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <div className="dash-col">
          <section className="sheet accuracy">
            <h2><span className="h-ico"><Icon name="shield" size={16} /></span>Is Pramaan accurate?</h2>
            <div className="acc-row">
              <div>
                <b>{a.hit_rate != null ? `${a.hit_rate}%` : '—'}</b>
                <span>Inspection hit rate</span>
                <small>{a.confirmed} of {a.inspections} inspections ordered after a flag found a real problem.</small>
              </div>
              <div>
                <b>{a.overruled_pct != null ? `${a.overruled_pct}%` : '—'}</b>
                <span>Flags overruled</span>
                <small>{a.dismissed} of {a.flags} flags were dismissed by officers.</small>
              </div>
            </div>
            {a.by_rule.length > 0 && (
              <p className="hint">Most overruled: {a.by_rule.map(r => `${r.title} (${r.dismissed} of ${r.total})`).join('; ')}. A rule that is often overruled should carry less weight in the rulebook.</p>
            )}
          </section>

          <section className="sheet">
            <h2><span className="h-ico"><Icon name="alert" size={16} /></span>What goes wrong most</h2>
            <Bars rows={d.rule_counts.slice(0, 8)} />
          </section>
        </div>
      </div>

      <div className="dash-grid three">
        <section className="sheet">
          <h2><span className="h-ico"><Icon name="history" size={16} /></span>Repeat offenders</h2>
          <p className="muted">Flagged in two or more approval cycles.</p>
          {d.repeat.length === 0 ? <p className="empty">None this cycle.</p> : (
            <ul className="plainlist">
              {d.repeat.map(r => (
                <li key={r.code}><a href={`#case/${r.application}`}>{r.name}</a><span>{r.years.join(', ')}</span></li>
              ))}
            </ul>
          )}
        </section>
        <section className="sheet">
          <h2><span className="h-ico"><Icon name="users" size={16} /></span>Teacher-sharing rings</h2>
          <p className="muted">Colleges joined by the same teachers.</p>
          {d.rings.length === 0 ? <p className="empty">No shared teachers found.</p> : (
            <>
              <p className="ring-count"><b>{d.rings.length}</b> ring{d.rings.length > 1 ? 's' : ''}; the biggest links <b>{d.rings[0].colleges.length}</b> colleges through <b>{d.rings[0].teachers}</b> teachers.</p>
              <ul className="plainlist">{d.rings[0].colleges.map(c => <li key={c}>{c}</li>)}</ul>
              <a className="link" href="#graph">See the links</a>
            </>
          )}
        </section>
        <section className="sheet">
          <h2><span className="h-ico"><Icon name="gavel" size={16} /></span>Officer workload</h2>
          <table className="grid compact workload">
            <thead><tr><th>Officer</th><th className="num">Files</th><th>Pending</th><th className="num">Avg days</th></tr></thead>
            <tbody>
              {d.officers.map(o => (
                <tr key={o.name}>
                  <td>{o.name}{o.oldest_pending_days > 15 && <div className="small warn-text">oldest pending {o.oldest_pending_days} days</div>}</td>
                  <td className="num">{o.assigned}</td>
                  <td className="nowrap"><span className="minibar"><i style={{ width: `${(100 * o.pending) / maxPending}%` }} /></span>{o.pending}</td>
                  <td className="num">{o.avg_days ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  )
}
