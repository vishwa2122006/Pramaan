import React, { useState } from 'react'
import { api } from '../api.js'
import { go } from '../App.jsx'
import { DecisionTag, Icon, Lane, Loading, PageHead, Risk, laneTone, useLoad } from '../ui.jsx'

const LANES = [
  { key: 'inspect', lane: 'Inspect', hint: 'score 50 or more', icon: 'alert' },
  { key: 'review', lane: 'Review', hint: 'score 20 to 49', icon: 'eye' },
  { key: 'fast', lane: 'Fast track', hint: 'score below 20', icon: 'check' },
]
export const initials = name => name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, '').split(/[\s.]+/).filter(w => w && !/^(of|and|the)$/i.test(w)).slice(0, 2).map(w => w[0]).join('').toUpperCase()

export default function Queue() {
  const [stats] = useLoad(api.stats)
  const [apps, , err] = useLoad(api.apps)
  const [filter, setFilter] = useState('all')
  if (!apps || !stats) return <Loading error={err} />
  const total = Math.max(stats.total, 1)
  const shown = filter === 'all' ? apps : apps.filter(a => a.lane === filter)
  return (
    <>
      <PageHead
        title="Application queue" icon="queue"
        aside={<div className="meta"><span>Rulebook <b>{stats.rules}</b></span><span>OCR <b>{stats.ocr.split(' (')[0]}</b></span></div>}
        extra={
          <>
            <div className="glass-row">
              {LANES.map(l => (
                <button key={l.key} className={`glass lane-${laneTone(l.lane)} ${filter === l.lane ? 'on' : ''}`}
                  onClick={() => setFilter(filter === l.lane ? 'all' : l.lane)} aria-pressed={filter === l.lane}>
                  <span className="glass-ico"><Icon name={l.icon} size={18} /></span>
                  <b>{stats[l.key]}</b>
                  <span>{l.lane}<small>{l.hint}</small></span>
                  <i className="glass-bar"><i style={{ width: `${(100 * stats[l.key]) / total}%` }} /></i>
                </button>
              ))}
              <div className="glass neutral">
                <span className="glass-ico"><Icon name="flag" size={18} /></span>
                <b>{stats.flags}</b><span>Open flags<small>across all colleges</small></span>
              </div>
              <div className="glass neutral">
                <span className="glass-ico"><Icon name="phone" size={18} /></span>
                <b>{stats.sms_waiting}</b><span>SMS unanswered<small>teachers yet to reply</small></span>
              </div>
            </div>
          </>
        }
      >
        {stats.total} applications were checked automatically. The riskiest are at the top; open one to see the proof behind every flag.
      </PageHead>

      <div className="sheet table-wrap queue-sheet">
        <div className="sheet-head">
          <h2><span className="h-ico"><Icon name="queue" size={16} /></span>{filter === 'all' ? 'All applications' : `${filter} lane`}</h2>
          {filter !== 'all' && <button className="btn quiet small" onClick={() => setFilter('all')}>Show all</button>}
        </div>
        <table className="grid queue">
          <thead>
            <tr><th>Institution</th><th>Lane</th><th className="riskcol">Risk</th><th>Main finding</th><th className="num">Flags</th><th>Officer</th><th>Decision</th></tr>
          </thead>
          <tbody>
            {shown.map(a => (
              <tr key={a.id} className={`edge-${laneTone(a.lane)}`} tabIndex={0}
                onClick={() => go(`case/${a.id}`)} onKeyDown={e => e.key === 'Enter' && go(`case/${a.id}`)}>
                <td>
                  <div className="inst-cell">
                    <span className={`mono-av ${laneTone(a.lane)}`} aria-hidden="true">{initials(a.institution)}</span>
                    <div>
                      <b className="inst">{a.institution}</b>
                      <div className="sub"><span className="code">{a.id}</span>{a.district}</div>
                    </div>
                  </div>
                </td>
                <td><Lane lane={a.lane} /></td>
                <td><Risk value={a.risk} /></td>
                <td className="finding-cell">{a.top_finding}</td>
                <td className="num"><span className={`flagcount ${a.flags ? '' : 'zero'}`}>{a.flags}</span></td>
                <td><span className="officer"><span className="av-sm" aria-hidden="true">{initials(a.officer || '?')}</span>{a.officer}</span></td>
                <td><DecisionTag d={a.decision} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
