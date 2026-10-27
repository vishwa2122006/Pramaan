import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Check, Icon } from '../ui.jsx'
import { Seal } from '../App.jsx'

/* The page college staff open on a phone. Camera only (no gallery), location on, two frames per shot. */
const sleep = ms => new Promise(r => setTimeout(r, ms))

function grab(video) {
  const c = document.createElement('canvas')
  const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight))
  c.width = Math.round(video.videoWidth * scale)
  c.height = Math.round(video.videoHeight * scale)
  c.getContext('2d').drawImage(video, 0, 0, c.width, c.height)
  return new Promise(res => c.toBlob(res, 'image/jpeg', 0.9))
}

export default function Capture({ token }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState(null)
  const [gps, setGps] = useState(null)
  const [gpsErr, setGpsErr] = useState(null)
  const [shot, setShot] = useState(null)
  const [phase, setPhase] = useState('idle')  // idle | camera | step | sending | done
  const [count, setCount] = useState(0)
  const [results, setResults] = useState({})
  const video = useRef(null)
  const stream = useRef(null)
  const secure = window.isSecureContext

  const load = () => api.capturePublic(token).then(setS).catch(e => setErr(e.message))
  useEffect(() => { load() }, [token]) // eslint-disable-line
  useEffect(() => {
    if (!secure || !navigator.geolocation) return
    const id = navigator.geolocation.watchPosition(
      p => { setGps({ lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy }); setGpsErr(null) },
      e => setGpsErr(e.code === 1 ? 'Location permission was refused. Allow location for this page and reload.' : 'Waiting for a GPS fix. Step outside or near a window.'),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 })
    return () => navigator.geolocation.clearWatch(id)
  }, [secure])
  useEffect(() => () => stream.current?.getTracks().forEach(t => t.stop()), [])

  const openCamera = async name => {
    setShot(name); setErr(null)
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } }, audio: false })
      setPhase('camera')
      setTimeout(() => { if (video.current) { video.current.srcObject = stream.current; video.current.play() } }, 0)
    } catch (e) {
      setErr('The camera could not start. Allow camera access for this page and try again.')
    }
  }
  const close = () => { stream.current?.getTracks().forEach(t => t.stop()); stream.current = null; setPhase('idle') }

  const take = async () => {
    const f1 = await grab(video.current)
    setPhase('step')
    for (let i = 2; i > 0; i--) { setCount(i); await sleep(1000) }
    const f2 = await grab(video.current)
    setPhase('sending')
    const fd = new FormData()
    fd.append('shot', shot)
    if (gps) { fd.append('lat', gps.lat); fd.append('lng', gps.lng); fd.append('accuracy', gps.acc) }
    fd.append('frame1', f1, 'frame1.jpg')
    fd.append('frame2', f2, 'frame2.jpg')
    try {
      const r = await api.captureShot(token, fd)
      setResults(x => ({ ...x, [shot]: r.shot }))
      close(); load()
    } catch (e) { setErr(e.message); setPhase('camera') }
  }

  if (err && !s) return <div className="cap"><div className="cap-card"><h1>Live capture</h1><p className="error">{err}</p></div></div>
  if (!s) return <div className="cap"><div className="cap-card"><p>Loading…</p></div></div>

  if (phase !== 'idle') {
    return (
      <div className="cam">
        <video ref={video} playsInline muted />
        <div className="cam-top">
          <b>{shot}</b>
          <span>Hold the card with <strong>{s.code}</strong> inside the picture</span>
        </div>
        {phase === 'step' && <div className="cam-step"><b>{count}</b>Take one small step sideways</div>}
        {phase === 'sending' && <div className="cam-step"><span className="spin" />Sending</div>}
        <div className="cam-bar">
          <button className="cam-cancel" onClick={close}>Cancel</button>
          <button className="cam-shutter" aria-label="Take photo" disabled={phase !== 'camera'} onClick={take}><i /></button>
          <span className="cam-gps">{gps ? `GPS ±${Math.round(gps.acc)} m` : 'No GPS yet'}</span>
        </div>
        {err && <p className="cam-err">{err}</p>}
      </div>
    )
  }

  return (
    <div className="cap">
      <header className="cap-brand"><span className="seal"><Seal size={28} /></span><b>Pramaan live capture</b></header>
      <div className="cap-card">
        <p className="muted">{s.institution} · application {s.application}</p>
        <div className="cap-code">
          <small>Write this code on a card and keep it in every photo</small>
          <b>{s.code}</b>
          <span className={`tag ${s.open ? 'green' : 'red'}`}>{s.open ? `Open for ${s.minutes_left} more minutes` : 'This session has closed'}</span>
        </div>
        {!secure && (
          <p className="error">This page must be opened over https:// for the camera and location to work. Ask the AICTE officer for the secure link.</p>
        )}
        {secure && <p className={`gps ${gps ? 'ok' : ''}`}><Icon name="pin" size={16} />{gps ? `Location found, accurate to ${Math.round(gps.acc)} m` : gpsErr || 'Finding your location…'}</p>}
        {err && <p className="error">{err}</p>}
      </div>
      <ol className="cap-shots">
        {s.shots.map(name => {
          const r = results[name]
          const done = r || s.done.includes(name)
          return (
            <li key={name} className={done ? 'done' : ''}>
              <div>
                <b>{name}</b>
                {r ? (
                  <div className="checks">
                    <Check state={r.checks.inside} label="Inside campus" />
                    <Check state={r.checks.time} label="On time" />
                    <Check state={r.checks.code === 'unchecked' ? null : r.checks.code} label="Code" />
                    <Check state={r.checks.live === 'unclear' ? null : r.checks.live} label="Real room" />
                  </div>
                ) : <small>{done ? 'Sent' : 'Not taken yet'}</small>}
              </div>
              <button className="btn primary" disabled={!secure || !s.open} onClick={() => openCamera(name)}>
                <Icon name="camera" size={16} />{done ? 'Retake' : 'Take photo'}
              </button>
            </li>
          )
        })}
      </ol>
      <p className="cap-foot">Photos are taken with the camera only; uploading from the gallery is not possible. Each photo is sent with its location and time.</p>
    </div>
  )
}
