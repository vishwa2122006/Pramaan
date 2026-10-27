import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Icon, Loading, PageHead } from '../ui.jsx'

const KEY = 'pramaan-teacher-token'
const getTok = () => { try { return sessionStorage.getItem(KEY) || '' } catch { return '' } }
const setTok = t => { try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY) } catch { /* private window */ } }

function Login({ onIn }) {
  const [phone, setPhone] = useState('')
  const [otp, setOtp] = useState('')
  const [pan, setPan] = useState('')
  const [sent, setSent] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const send = async e => {
    e.preventDefault(); setErr(null); setBusy(true)
    try { setSent(await api.teacherOtp(phone)) } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  const login = async e => {
    e.preventDefault(); setErr(null); setBusy(true)
    try { const r = await api.teacherLogin(phone, otp, pan); setTok(r.token); onIn(r.token) } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return (
    <div className="cols wide-left">
      <form className="sheet form login" onSubmit={sent ? login : send}>
        <h2>Sign in</h2>
        <div className="formgrid one">
          <label>Mobile number<input required inputMode="tel" autoComplete="tel" value={phone} disabled={!!sent} onChange={e => setPhone(e.target.value)} placeholder="+91 90000 11002" /></label>
          {sent && <>
            <label>One-time password (OTP)<input required inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={e => setOtp(e.target.value)} /></label>
            <label>Last 4 characters of your PAN<input required maxLength={4} value={pan} onChange={e => setPan(e.target.value.toUpperCase())} placeholder="314M" /></label>
          </>}
        </div>
        {sent && (
          <div className="sms-sim" role="status">
            <Icon name="phone" size={18} />
            <span><b>Simulated SMS to {sent.to}</b>Your Pramaan login code is <strong>{sent.demo_otp}</strong>. It expires in 5 minutes.</span>
          </div>
        )}
        <div className="btns">
          <button className="btn primary" disabled={busy}>{sent ? 'Sign in' : 'Send OTP'}</button>
          {sent && <button type="button" className="btn quiet" onClick={() => { setSent(null); setOtp('') }}>Use another number</button>}
        </div>
        {err && <p className="error">{err}</p>}
      </form>
      <aside className="sheet guide">
        <h2>Try it</h2>
        <p>Sign in as Dr. M. Kalaivani: mobile <b>+91 90000 11002</b>, PAN ending <b>314M</b>. She is listed by two colleges.</p>
        <p className="hint">OTP delivery is simulated in this model; a real SMS gateway sends it in production.</p>
      </aside>
    </div>
  )
}

function Claims({ token, onOut }) {
  const [me, setMe] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)
  const [last, setLast] = useState(null)
  const load = () => api.teacherMe(token).then(setMe).catch(e => { setErr(e.message); if (/sign in/i.test(e.message)) onOut() })
  useEffect(() => { load() }, [token]) // eslint-disable-line
  if (!me) return <Loading error={err} />
  const act = async (c, action) => {
    setBusy(c.faculty_id + action)
    const r = await api.teacherClaim(token, c.faculty_id, action)
    setLast({ ...r, institution: c.institution, action })
    await load(); setBusy(null)
  }
  return (
    <>
      <div className="teacher-head sheet">
        <span className="avatar big" aria-hidden="true">{me.name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, '').split(/[\s.]+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('')}</span>
        <div>
          <h2>{me.name}</h2>
          <p className="muted">PAN {me.pan} · {me.phone}{me.previous_seen ? ` · last signed in ${me.previous_seen}` : ''}</p>
        </div>
        <div className="btns">
          <a className="btn quiet" href={api.teacherStatement(token)}><Icon name="doc" size={16} />Claims statement (PDF)</a>
          <button className="btn quiet" onClick={() => { setTok(''); onOut() }}>Sign out</button>
        </div>
      </div>
      {me.alerts.length > 0 && (
        <div className="banner warn" role="status">
          <span className="banner-ico"><Icon name="user" size={20} /></span>
          <span>{me.alerts.length === 1 ? '1 new college has' : `${me.alerts.length} new colleges have`} listed you as faculty since you last signed in. Please confirm or deny below.</span>
        </div>
      )}
      {last && (
        <div className={`banner ${last.action === 'confirm' ? 'good' : 'bad'}`} role="status">
          <span className="banner-ico"><Icon name={last.action === 'confirm' ? 'check' : 'cross'} size={20} /></span>
          <span>{last.action === 'confirm' ? 'Confirmed' : last.action === 'deny' ? 'Denied' : 'Misuse reported'} for {last.institution}.
            AICTE re-checked application {last.application} at once: risk {last.risk}, lane {last.lane}.</span>
        </div>
      )}
      <h2 className="section-title">Colleges that list you</h2>
      <div className="claims">
        {me.claims.map(c => (
          <article key={c.faculty_id} className={`claim sheet ${c.new ? 'new' : ''}`}>
            <div className="claim-main">
              <div>
                {c.new && <span className="tag purple">New</span>}
                <h3>{c.institution}</h3>
                <p className="muted">{c.district} · academic year {c.academic_year} · listed as {c.designation} · {c.listed_on}</p>
              </div>
              <span className={`tag ${c.status === 'no' ? 'red' : c.status === 'yes' ? 'green' : 'grey'}`}>{c.status_label}</span>
            </div>
            <div className="btns">
              <button className="btn green small" disabled={!!busy} onClick={() => act(c, 'confirm')}>I work here</button>
              <button className="btn red small" disabled={!!busy} onClick={() => act(c, 'deny')}>I do not work here</button>
              <button className="btn quiet danger small" disabled={!!busy} onClick={() => act(c, 'misuse')}>Report misuse of my name</button>
            </div>
          </article>
        ))}
      </div>
      <p className="hint">“I do not work here” counts exactly like replying NO to the SMS: the college is flagged and the officer sees your answer as proof.</p>
    </>
  )
}

export default function Teacher() {
  const [token, setToken] = useState(getTok())
  return (
    <>
      <PageHead title="Teacher portal" icon="user">
        See every college that lists you as faculty, for every year, and confirm or deny each one. You also get an alert whenever a new college lists you.
      </PageHead>
      {token ? <Claims token={token} onOut={() => setToken('')} /> : <Login onIn={setToken} />}
    </>
  )
}
