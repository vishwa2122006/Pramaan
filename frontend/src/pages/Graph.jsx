import React from 'react'
import { api } from '../api.js'
import { Loading, PageHead, useLoad } from '../ui.jsx'

export default function Graph() {
  const [g, , err] = useLoad(api.graph)
  if (!g) return <Loading error={err} />
  const inst = g.nodes.filter(n => n.type === 'institution')
  const right = g.nodes.filter(n => n.type !== 'institution')
  const H = Math.max(inst.length, right.length) * 70 + 60
  const pos = {}
  inst.forEach((n, i) => { pos[n.id] = [250, 50 + i * ((H - 80) / Math.max(1, inst.length - 1 || 1))] })
  right.forEach((n, i) => { pos[n.id] = [650, 50 + i * ((H - 80) / Math.max(1, right.length - 1 || 1))] })
  return (
    <>
      <PageHead title="Cross-college links" icon="graph">
        Colleges are usually checked one at a time. Pramaan checks them all together: each line means the same teacher (same PAN) or the same lab photo appears in more than one college.
      </PageHead>
      <div className="sheet graph">
        <div className="legend"><span><i className="sw red" />Same teacher listed full-time</span><span><i className="sw amber" />Same lab photo</span></div>
        {g.links.length === 0 ? <p className="empty">No college shares a teacher or a lab photo with another. New links appear here as applications come in.</p> : (
          <svg viewBox={`0 0 900 ${H}`} width="100%">
            {g.links.map((l, i) => {
              const [x1, y1] = pos[l.source], [x2, y2] = pos[l.target]
              return <path key={i} d={`M${x1} ${y1} C ${x1 + 200} ${y1}, ${x2 - 200} ${y2}, ${x2} ${y2}`}
                fill="none" stroke={l.type === 'photo' ? 'var(--amber)' : 'var(--red)'} strokeWidth="2" opacity="0.75" />
            })}
            {inst.map(n => (
              <g key={n.id} transform={`translate(${pos[n.id][0]},${pos[n.id][1]})`}>
                <rect x="-230" y="-20" width="230" height="40" rx="4" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.2" />
                <rect x="-230" y="-20" width="5" height="40" rx="1" fill="var(--ink)" />
                <text x="-112" y="5" textAnchor="middle" fontSize="13.5" fontWeight="600" fill="var(--ink-deep)">{n.label.length > 32 ? n.label.slice(0, 31) + '…' : n.label}</text>
              </g>
            ))}
            {right.map(n => (
              <g key={n.id} transform={`translate(${pos[n.id][0]},${pos[n.id][1]})`}>
                <rect x="0" y="-20" width="240" height="40" rx="20" fill={n.type === 'photo' ? 'var(--amber-t)' : 'var(--red-t)'} stroke={n.type === 'photo' ? 'var(--amber)' : 'var(--red)'} strokeWidth="1.2" />
                <circle cx="20" cy="0" r="5" fill={n.type === 'photo' ? 'var(--amber)' : 'var(--red)'} />
                <text x="34" y="5" fontSize="13.5" fontWeight="500" fill={n.type === 'photo' ? 'var(--amber)' : 'var(--red)'}>{n.type === 'photo' ? 'Photo: ' : ''}{n.label}</text>
              </g>
            ))}
          </svg>
        )}
      </div>
    </>
  )
}
