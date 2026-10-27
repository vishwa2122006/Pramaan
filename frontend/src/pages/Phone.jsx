import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { go } from '../App.jsx'
import { Loading, PageHead, useLoad } from '../ui.jsx'

export default function Phone() {
  const [phones, reloadPhones, err] = useLoad(api.phones)
  const [sel, setSel] = useState(null)
  const [msgs, setMsgs] = useState([])
  const [last, setLast] = useState(null)
  useEffect(() => { if (phones && !sel && phones.length) setSel(phones[0].phone) }, [phones, sel])
  useEffect(() => { if (sel) api.inbox(sel).then(setMsgs) }, [sel])
  if (!phones) return <Loading error={err} />
  const reply = async (m, ans) => {
    const r = await api.reply(m.id, ans)
    setLast({ ...r, answer: ans, institution: m.institution })
    setMsgs(await api.inbox(sel)); reloadPhones()
  }
  const who = phones.find(p => p.phone === sel)
  return (
    <>
      <PageHead title="Teacher's phone" icon="phone">
        When a teacher is listed full-time by more than one college, each claim is sent to the teacher by SMS. Play the teacher here and reply. SMS is simulated in this model; a real SMS gateway plugs in at this step.
      </PageHead>
      <div className="phonewrap">
        <div className="sheet">
          <h2>Teachers who got an SMS</h2>
          {phones.length === 0 && <p className="empty">No SMS has been sent yet. One goes out when a teacher appears in two colleges' faculty lists.</p>}
          {phones.map(p => (
            <button key={p.phone} className={`contact ${p.phone === sel ? 'on' : ''}`} onClick={() => setSel(p.phone)}>
              <span className="avatar" aria-hidden="true">{p.name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, '').split(/[\s.]+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('')}</span>
              <span className="contact-text"><b>{p.name}</b><small>{p.phone}</small></span>
              {p.waiting > 0 && <span className="tag purple">{p.waiting} waiting</span>}
            </button>
          ))}
        </div>
        <div className="phone">
          <div className="notch" />
          <div className="screen">
            <div className="statusbar" aria-hidden="true"><span>9:41</span><span>●●● ▮</span></div>
            <div className="sender"><span className="sender-ico">AP</span>AICTE-PRAMAAN<small>to {who?.name}</small></div>
            {msgs.map(m => (
              <div key={m.id} className="thread">
                <div className="bubble in">{m.text}<small>{m.created}</small></div>
                {m.status === 'sent' ? (
                  <div className="quick">
                    <button className="btn green" onClick={() => reply(m, 'yes')}>Reply YES</button>
                    <button className="btn red" onClick={() => reply(m, 'no')}>Reply NO</button>
                  </div>
                ) : (
                  <div className="bubble out">{m.status.toUpperCase()}<small>{m.replied}</small></div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="sheet">
          <h2>What happens next</h2>
          {last ? (
            <>
              <p>You replied <b>{last.answer.toUpperCase()}</b> about <b>{last.institution}</b>.</p>
              <p>Pramaan re-checked application <b>{last.application}</b> at once: risk is now <b>{last.risk}</b>, lane <b>{last.lane}</b>.</p>
              <button className="btn primary" onClick={() => go(`case/${last.application}`)}>Open that application</button>
            </>
          ) : (
            <ul className="steps">
              <li><b>YES</b>: the teacher confirms working there.</li>
              <li><b>NO</b>: the college is flagged at once (+30 risk) and the officer sees the reply as proof.</li>
              <li>Only one yes/no question is asked; the PAN is never shown in full.</li>
            </ul>
          )}
        </div>
      </div>
    </>
  )
}
