const BASE = import.meta.env.VITE_API || ''

async function req(path, opts = {}) {
  const r = await fetch(BASE + path, opts)
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`)
  return body
}
const post = (path, data) => req(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })

export const api = {
  stats: () => req('/api/stats'),
  apps: () => req('/api/applications'),
  app: id => req(`/api/applications/${id}`),
  officers: () => req('/api/officers'),
  decide: (id, decision, note, officer) => post(`/api/applications/${id}/decision`, { decision, note, officer }),
  inspection: (id, outcome, officer) => post(`/api/applications/${id}/inspection`, { outcome, officer }),
  dismiss: (id, f, note, officer, restore = false) => post(`/api/applications/${id}/dismiss`, { rule: f.rule, detail: f.detail, note, officer, restore }),
  reprocess: id => req(`/api/applications/${id}/reprocess`, { method: 'POST' }),
  submit: form => req('/api/applications', { method: 'POST', body: form }),
  practice: form => req('/api/practice', { method: 'POST', body: form }),
  phones: () => req('/api/sms/phones'),
  inbox: phone => req(`/api/sms?phone=${encodeURIComponent(phone)}`),
  reply: (id, answer) => post(`/api/sms/${id}/reply`, { answer }),
  rules: () => req('/api/rules'),
  saveRules: (data, note) => post('/api/rules', { data, note }),
  audit: () => req('/api/audit'),
  verify: () => req('/api/audit/verify'),
  tamper: () => req('/api/demo/tamper', { method: 'POST' }),
  reset: () => req('/api/demo/reset', { method: 'POST' }),
  graph: () => req('/api/graph'),
  file: id => `${BASE}/api/files/${id}`,
  preview: (id, page = 0, boxes = []) => `${BASE}/api/documents/${id}/preview?page=${page}&boxes=${boxes.map(b => b.map(v => Math.round(v * 10) / 10).join(',')).join(';')}`,
  heatmap: id => `${BASE}/api/documents/${id}/heatmap`,
  qr: text => `${BASE}/api/qr?text=${encodeURIComponent(text)}`,
  // live capture
  captureInfo: id => req(`/api/applications/${id}/capture`),
  captureStart: (id, officer) => post(`/api/applications/${id}/capture`, { officer }),
  capturePublic: token => req(`/api/capture/${token}`),
  captureShot: (token, form) => req(`/api/capture/${token}/shot`, { method: 'POST', body: form }),
  // reports
  report: (id, kind, officer) => post(`/api/applications/${id}/report`, { kind, officer }),
  reportPdf: rid => `${BASE}/api/reports/${rid}/pdf`,
  reportVerify: rid => req(`/api/reports/${rid}/verify`),
  reportVerifyFile: (rid, file) => { const f = new FormData(); f.append('file', file); return req(`/api/reports/${rid}/verify`, { method: 'POST', body: f }) },
  // teacher portal
  teacherOtp: phone => post('/api/teacher/otp', { phone }),
  teacherLogin: (phone, otp, pan_last4) => post('/api/teacher/login', { phone, otp, pan_last4 }),
  teacherMe: token => req(`/api/teacher/me?token=${encodeURIComponent(token)}`),
  teacherClaim: (token, fid, action, note = '') => post(`/api/teacher/claims/${fid}`, { token, action, note }),
  teacherStatement: token => `${BASE}/api/teacher/statement?token=${encodeURIComponent(token)}`,
  dashboard: () => req('/api/dashboard'),
  netinfo: () => req('/api/netinfo'),
}
