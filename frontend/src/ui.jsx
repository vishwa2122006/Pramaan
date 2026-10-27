import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    return fn().then(d => { setData(d); setError(null) }).catch(e => setError(e.message))
  }, deps) // eslint-disable-line
  useEffect(() => { load() }, [load])
  return [data, load, error]
}

export const laneTone = lane => ({ Inspect: 'red', Review: 'amber', 'Fast track': 'green' }[lane] || 'grey')
export const riskTone = v => (v >= 50 ? 'red' : v >= 20 ? 'amber' : 'green')

export const Lane = ({ lane }) => <span className={`lane ${laneTone(lane)}`}><i />{lane || '—'}</span>

/* The rubber stamp: lane + score, the one loud element in the app. */
export const Stamp = ({ lane, risk, animate }) => (
  <div className={`stamp ${laneTone(lane)} ${animate ? 'land' : ''}`} role="img" aria-label={`${lane}, risk ${risk} of 100`}>
    <span className="stamp-lane">{lane}</span>
    <span className="stamp-score">{risk}</span>
    <span className="stamp-of">risk of 100</span>
  </div>
)

export const Risk = ({ value }) => (
  <div className={`risk ${riskTone(value)}`}>
    <b>{value}</b>
    <div className="bar" aria-hidden="true"><i style={{ width: `${Math.max(value, 2)}%` }} /></div>
  </div>
)

const SEV = { high: 'red', medium: 'amber', low: 'blue', info: 'grey' }
export const Sev = ({ s }) => <span className={`sev ${SEV[s] || 'grey'}`}>{s}</span>

export const Loading = ({ error }) => (
  <div className="loading">{error ? <>Could not load this screen: {error}. If the Pramaan server has stopped, start it again and refresh.</> : <><span className="spin" />Loading</>}</div>
)

/* Guilloché: the fine interlaced line-work printed on certificates and banknotes to make them hard to forge. */
const gWave = (w, h, i, n, seed) => {
  const pts = []
  const base = h * (0.15 + 0.7 * i / (n - 1))
  for (let x = 0; x <= w; x += 8) {
    const y = base + Math.sin(x / (w / 3.2) + i * 0.33 + seed) * h * 0.16 + Math.sin(x / (w / 11) + i * 0.9) * h * 0.035
    pts.push(`${x.toFixed(0)},${y.toFixed(1)}`)
  }
  return 'M' + pts.join(' L')
}
const gRose = (cx, cy, R, r, d, turns = 1) => {
  const pts = []
  for (let t = 0; t <= Math.PI * 2 * turns + 0.01; t += 0.02) {
    const x = cx + (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t)
    const y = cy + (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t)
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return 'M' + pts.join(' L')
}

export function Guilloche({ kind = 'waves', w = 1200, h = 260, lines = 22, seed = 0, className = '' }) {
  if (kind === 'rosette') {
    const c = w / 2
    return (
      <svg className={`guilloche ${className}`} viewBox={`0 0 ${w} ${w}`} aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        {[0, 1, 2, 3, 4, 5].map(k => <path key={k} d={gRose(c, c, c * 0.62 - k * 6, c * 0.62 / (7.2 + k * 0.4), c * (0.3 - k * 0.018), 10)} />)}
        <circle cx={c} cy={c} r={c * 0.9} />
        <circle cx={c} cy={c} r={c * 0.86} strokeDasharray="1 3" />
      </svg>
    )
  }
  return (
    <svg className={`guilloche ${className}`} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" preserveAspectRatio="none">
      {Array.from({ length: lines }, (_, i) => <path key={i} d={gWave(w, h, i, lines, seed)} />)}
      {Array.from({ length: lines }, (_, i) => <path key={`b${i}`} className="g2" d={gWave(w, h, i, lines, seed + 2.1)} />)}
    </svg>
  )
}

export const Microtext = ({ text = 'PRAMAAN · PROOF-BASED CHECKING · AICTE · ' }) => (
  <div className="microtext" aria-hidden="true">{text.repeat(30)}</div>
)

export const PageHead = ({ title, children, aside, extra, icon }) => (
  <header className="masthead">
    <Guilloche seed={title.length} />
    <div className="masthead-row">
      <div>
        <div className="mast-title">
          {icon && <span className="mast-ico"><Icon name={icon} size={22} /></span>}
          <h1>{title}</h1>
        </div>
        {children && <p className="lede">{children}</p>}
      </div>
      {aside && <div className="pagehead-aside">{aside}</div>}
    </div>
    {extra && <div className="masthead-extra">{extra}</div>}
    <Microtext />
  </header>
)

const DECISION = { approve: ['green', 'Approved'], query: ['amber', 'Query sent'], inspect: ['red', 'Inspection ordered'] }
export const DecisionTag = ({ d }) => d
  ? <span className={`decision ${DECISION[d][0]}`}>{DECISION[d][1]}</span>
  : <span className="decision pending">Pending</span>

const PATHS = {
  queue: 'M4 6h16M4 12h16M4 18h10',
  graph: 'M6 6a2 2 0 1 0 0 .01M6 18a2 2 0 1 0 0 .01M18 12a2 2 0 1 0 0 .01M8 6.6l8 4.6M8 17.4l8-4.6',
  upload: 'M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3',
  phone: 'M8 3h8a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 16 21H8a1.5 1.5 0 0 1-1.5-1.5v-15A1.5 1.5 0 0 1 8 3Zm3 15h2',
  rules: 'M5 7h9m4 0h1M5 12h3m4 0h7M5 17h11m4 0h-1M16 5v4M10 10v4M18 15v4',
  chain: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  back: 'M15 18l-6-6 6-6',
  open: 'M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4',
  file: 'M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm7 0v5h5',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  cross: 'M6 6l12 12M18 6 6 18',
  chart: 'M4 20h16M7 16v-5M12 16V7M17 16v-8',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4ZM12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z',
  pin: 'M12 21s-6-5.6-6-11a6 6 0 1 1 12 0c0 5.4-6 11-6 11Zm0-9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  doc: 'M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm7 0v5h5M9 13h6M9 17h6',
  minus: 'M6 12h12',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v4l3 2',
  shield: 'M12 3 5 6v6c0 4.5 3 8 7 9 4-1 7-4.5 7-9V6Z',
  alert: 'M12 4 2.8 19.5h18.4ZM12 10v4.5M12 17.2v.3',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Zm9.5 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  flag: 'M5 21V4m0 0h11l-2 4 2 4H5',
  image: 'M4 5h16v14H4ZM4 15l4.5-4.5 4 4 2.5-2.5L20 17M15.5 9.5a1 1 0 1 0 0-.01',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0m1-9a3 3 0 1 0-1-5.8M21 20a5 5 0 0 0-4-4.9',
  map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2Zm0 0v14m6-12v14',
  gavel: 'M14 4l6 6M11.5 6.5l6 6M13 5l-7 7 3 3 7-7M8.5 13.5 3 19l2 2 5.5-5.5M12 21h9',
  history: 'M3.5 12a8.5 8.5 0 1 0 2.5-6M3 4v4h4M12 8v4l3 2',
  folder: 'M3 6h6l2 2h10v11H3Z',
}

/* rule family -> icon and tint for the finding cards */
export const ruleFamily = rule => {
  if (/^R-(PDF|SRC)/.test(rule)) return ['doc', 'Document']
  if (/^R-CAP/.test(rule)) return ['camera', 'Live capture']
  if (/^R-IMG/.test(rule)) return ['image', 'Photo']
  if (/^R-(XINST|SMS|NORM)/.test(rule)) return ['users', 'Faculty']
  if (/^R-FACT/.test(rule)) return ['map', 'Land']
  if (/^R-LOGIC/.test(rule)) return ['clock', 'Logic']
  return ['file', 'Document']
}

/* Which officer is using the screen. Decisions, dismissals and reports carry this name. */
const OfficerCtx = createContext({ officer: '', officers: [], setOfficer: () => {} })
export const useOfficer = () => useContext(OfficerCtx)

export function OfficerProvider({ children }) {
  const [officers, setOfficers] = useState([])
  const [officer, setOfficerState] = useState(() => { try { return localStorage.getItem('pramaan-officer') || '' } catch { return '' } })
  useEffect(() => { api.officers().then(setOfficers).catch(() => {}) }, [])
  useEffect(() => { if (officers.length && !officers.some(o => o.name === officer)) setOfficerState(officers[0].name) }, [officers]) // eslint-disable-line
  const setOfficer = v => { setOfficerState(v); try { localStorage.setItem('pramaan-officer', v) } catch { /* private window */ } }
  return <OfficerCtx.Provider value={{ officer, officers, setOfficer }}>{children}</OfficerCtx.Provider>
}

export function OfficerPicker() {
  const { officer, officers, setOfficer } = useOfficer()
  if (!officers.length) return null
  const ini = (officer || '?').replace(/[^A-Za-z ]/g, ' ').split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2)
  return (
    <label className="whoami">
      <span>Working as</span>
      <span className="whoami-row"><span className="av-sm gold" aria-hidden="true">{ini}</span>
      <select value={officer} onChange={e => setOfficer(e.target.value)}>
        {officers.map(o => <option key={o.name} value={o.name}>{o.name}</option>)}
      </select></span>
    </label>
  )
}

export const Check = ({ state, label, detail }) => {
  const s = state === true || state === 'found' || state === 'live' ? 'ok' : state === false || state === 'missing' || state === 'flat' ? 'bad' : 'unk'
  return (
    <span className={`chk ${s}`} title={detail || ''}>
      <Icon name={s === 'ok' ? 'check' : s === 'bad' ? 'cross' : 'minus'} size={14} />{label}
    </span>
  )
}
export const Icon = ({ name, size = 18 }) => (
  <svg className="ico" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={PATHS[name]} />
  </svg>
)
