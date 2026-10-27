import React, { useEffect, useState } from 'react'
import Queue from './pages/Queue.jsx'
import CaseView from './pages/CaseView.jsx'
import Submit from './pages/Submit.jsx'
import Phone from './pages/Phone.jsx'
import Rules from './pages/Rules.jsx'
import Audit from './pages/Audit.jsx'
import Graph from './pages/Graph.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Teacher from './pages/Teacher.jsx'
import Capture from './pages/Capture.jsx'
import Verify from './pages/Verify.jsx'
import { Guilloche, Icon, OfficerProvider, OfficerPicker } from './ui.jsx'

const GROUPS = [
  { who: 'AICTE leadership', tabs: [{ key: 'dashboard', label: 'Region dashboard', icon: 'chart' }] },
  { who: 'AICTE officer', tabs: [
    { key: 'queue', label: 'Application queue', icon: 'queue' },
    { key: 'graph', label: 'Cross-college links', icon: 'graph' },
  ] },
  { who: 'College', tabs: [
    { key: 'submit', label: 'Submit an application', icon: 'upload' },
    { key: 'selfcheck', label: 'Practice check', icon: 'check' },
  ] },
  { who: 'Teacher', tabs: [
    { key: 'teacher', label: 'Teacher portal', icon: 'user' },
    { key: 'phone', label: "Teacher's phone (SMS)", icon: 'phone' },
  ] },
  { who: 'Rule admin', tabs: [{ key: 'rules', label: 'Rulebook', icon: 'rules' }] },
  { who: 'Auditor', tabs: [{ key: 'audit', label: 'Activity log', icon: 'chain' }] },
]

function useHash() {
  const [h, setH] = useState(window.location.hash.slice(1) || 'queue')
  useEffect(() => {
    const f = () => { setH(window.location.hash.slice(1) || 'queue'); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])
  return h
}

export const go = path => { window.location.hash = path }

export const Seal = ({ size = 34 }) => (
  <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true">
    <circle cx="20" cy="20" r="18.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeDasharray="2 2.2" />
    <circle cx="20" cy="20" r="14.5" fill="currentColor" />
    <path d="m14.2 20.4 3.9 3.9 7.9-8.4" fill="none" stroke="var(--side)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export default function App() {
  const route = useHash()
  const [page, arg] = route.split('/')
  // pages opened from a phone or a QR code stand alone, without the officer sidebar
  if (page === 'capture') return <Capture token={arg} />
  if (page === 'verify') return <Verify id={arg} />
  const active = page === 'case' ? 'queue' : page
  return (
    <OfficerProvider>
      <div className="shell">
        <aside className="side">
          <Guilloche kind="rosette" w={600} className="side-rosette" />
          <a className="brand" href="#queue" aria-label="Pramaan home">
            <span className="seal"><Seal /></span>
            <span>
              <b>Pramaan</b>
              <small>प्रमाण · proof-based checking of AICTE applications</small>
            </span>
          </a>
          <nav aria-label="Screens">
            {GROUPS.map(g => (
              <div className="navgroup" key={g.who}>
                <span className="who">{g.who}</span>
                {g.tabs.map(t => (
                  <a key={t.key} className={active === t.key ? 'on' : ''} href={`#${t.key}`} aria-current={active === t.key ? 'page' : undefined}>
                    <span className="nav-ico"><Icon name={t.icon} size={17} /></span>{t.label}
                  </a>
                ))}
              </div>
            ))}
          </nav>
          <OfficerPicker />
        </aside>
        <main>
          {page === 'case' && <CaseView id={arg} />}
          {active === 'queue' && page !== 'case' && <Queue />}
          {active === 'dashboard' && <Dashboard />}
          {active === 'graph' && <Graph />}
          {active === 'submit' && <Submit key="submit" mode="submit" />}
          {active === 'selfcheck' && <Submit key="practice" mode="practice" />}
          {active === 'teacher' && <Teacher />}
          {active === 'phone' && <Phone />}
          {active === 'rules' && <Rules />}
          {active === 'audit' && <Audit />}
        </main>
      </div>
    </OfficerProvider>
  )
}
