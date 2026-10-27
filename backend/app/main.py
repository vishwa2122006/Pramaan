"""Pramaan API + web app. Run: uvicorn app.main:app --port 8000 (from the backend folder)."""
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit, capture, extract, forensics, issuers, net, pipeline, reports
from .db import (BASE_DIR, DATA_DIR, STORE_DIR, Application, AuditEntry, CaptureSession, CaptureShot, Document, Faculty,
                 Finding, FlagDismissal, Institution, PastCycle, PhotoPrint, PracticeRun, Report, RuleVersion, SessionLocal,
                 SmsMessage, TeacherAccount, TeacherOtp, VerifiedFact, init_db, jload)

app = FastAPI(title='Pramaan API', version='1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
init_db()
UPLOADS = os.path.join(STORE_DIR, 'uploads')
os.makedirs(UPLOADS, exist_ok=True)


def session():
    return SessionLocal()


def app_row(a: Application, inst: Institution, s):
    fs = s.query(Finding).filter_by(application_id=a.id).all()
    top = sorted([f for f in fs if f.weight > 0], key=lambda f: -f.weight)
    return {'id': a.id, 'institution': inst.name, 'district': inst.district, 'category': a.category,
            'programme': a.programme, 'intake': a.intake, 'risk': a.risk, 'lane': a.lane, 'status': a.status,
            'decision': a.decision, 'flags': len([f for f in top if not f.dismissed]),
            'top_finding': next((f.title for f in top if not f.dismissed), 'No problems found'),
            'created': a.created.strftime('%Y-%m-%d %H:%M') if a.created else '', 'officer': a.officer or ''}


# ------------------------------------------------------------------ queue and cases
@app.get('/api/stats')
def stats():
    with session() as s:
        apps = s.query(Application).all()
        c = Counter(a.lane for a in apps)
        return {'total': len(apps), 'inspect': c.get('Inspect', 0), 'review': c.get('Review', 0),
                'fast': c.get('Fast track', 0),
                'flags': s.query(Finding).filter(Finding.weight > 0, (Finding.dismissed == False) | (Finding.dismissed == None)).count(),  # noqa: E712
                'sms_waiting': s.query(SmsMessage).filter_by(status='sent').count(), 'ocr': extract.OCR_STATUS,
                'rules': pipeline.active_rules(s)['version']}


@app.get('/api/applications')
def list_apps():
    with session() as s:
        rows = [app_row(a, a.institution, s) for a in s.query(Application).all()]
        return sorted(rows, key=lambda r: -r['risk'])


KIND_LABEL = {'fire_noc': 'Fire NOC', 'land_doc': 'Land document', 'faculty_list': 'Faculty list', 'lab_photo': 'Lab photo',
              'live_photo': 'Live photo'}


def case_dict(s, a):
    inst = a.institution
    rules = pipeline.active_rules(s)
    docs = []
    for d in s.query(Document).filter_by(application_id=a.id).all():
        meta = jload(d.meta, {})
        meta.pop('read', None)
        fx = meta.pop('forensics', None) or {}
        fsum = None
        if fx.get('type') == 'pdf':
            fsum = {'type': 'pdf', 'history': fx['history']['summary'], 'saves': fx['history']['saves'],
                    'edited': fx['history']['saves'] > 1 or bool(fx['history'].get('editor')),
                    'fonts': len(fx.get('fonts', [])), 'covers': len(fx.get('covers', []))}
        elif fx.get('type') == 'image':
            fsum = {'type': 'image', 'hotspots': len(fx['ela']['spots']), 'copies': len(fx['copy_move'])}
        docs.append({'id': d.id, 'kind': d.kind, 'kind_label': KIND_LABEL.get(d.kind, d.kind), 'filename': d.filename,
                     'sha256': d.sha256[:16], 'sha256_full': d.sha256, 'fields': jload(d.fields, {}), 'meta': meta,
                     'forensics': fsum, 'text': (d.text or '')[:1500]})
    fac = []
    for f in s.query(Faculty).filter_by(application_id=a.id).all():
        sms = s.query(SmsMessage).filter_by(pan_hash=f.pan_hash, application_id=a.id).first() if f.pan_hash else None
        n = s.query(Faculty).filter(Faculty.pan_hash == f.pan_hash, Faculty.institution_id != a.institution_id).count() if f.pan_hash else 0
        fac.append({'name': f.name, 'designation': f.designation, 'pan': f.pan_masked, 'phone': f.phone,
                    'elsewhere': n, 'sms': sms.status if sms else None, 'channel': sms.channel if sms else None})
    fnd = [{'rule': f.rule_id, 'severity': f.severity, 'weight': f.weight, 'title': f.title, 'detail': f.detail,
            'evidence': jload(f.evidence, {}), 'dismissed': bool(f.dismissed), 'dismiss_note': f.dismiss_note or '',
            'plain': pipeline.sentence(rules, f.rule_id, jload(f.evidence, {}))}
           for f in sorted(s.query(Finding).filter_by(application_id=a.id).all(), key=lambda f: (bool(f.dismissed), -f.weight))]
    facts = [{'key': v.key, 'value': v.value, 'source': v.source, 'verified_on': v.verified_on}
             for v in s.query(VerifiedFact).filter_by(institution_id=inst.id).all() if v.key != 'Campus boundary']
    trail = [{'ts': e.ts, 'actor': e.actor, 'action': e.action, 'payload': jload(e.payload, {})}
             for e in s.query(AuditEntry).filter_by(application_id=a.id).order_by(AuditEntry.id).all()]
    rep = [{'id': r.id, 'kind': r.kind, 'created': r.created.strftime('%d %b %H:%M'), 'officer': r.officer}
           for r in s.query(Report).filter_by(application_id=a.id).order_by(Report.created.desc()).all()]
    return {**app_row(a, inst, s), 'decision_note': a.decision_note, 'rule_version': a.rule_version,
            'academic_year': a.academic_year, 'campus': [inst.lat, inst.lng], 'code': inst.code,
            'decided_by': a.decided_by or '', 'decided_at': a.decided_at.strftime('%d %b %Y %H:%M') if a.decided_at else '',
            'inspection_outcome': a.inspection_outcome or '',
            'summary': reports.summary(rules, fnd, a.lane),
            'documents': docs, 'faculty': fac, 'findings': fnd, 'facts': facts, 'trail': trail, 'reports': rep}


@app.get('/api/applications/{app_id}')
def get_app(app_id: str):
    with session() as s:
        a = s.get(Application, app_id)
        if not a:
            raise HTTPException(404, 'No such application')
        return case_dict(s, a)


@app.get('/api/files/{doc_id}')
def get_file(doc_id: int):
    with session() as s:
        d = s.get(Document, doc_id)
        if not d or not os.path.exists(d.path):
            raise HTTPException(404)
        return FileResponse(d.path, filename=d.filename, content_disposition_type='inline')


def officers():
    with open(os.path.join(DATA_DIR, 'officers.json'), encoding='utf-8') as f:
        return json.load(f)['officers']


@app.get('/api/officers')
def get_officers():
    return officers()


class Decision(BaseModel):
    decision: str
    note: str = ''
    officer: str = ''


@app.post('/api/applications/{app_id}/decision')
def decide(app_id: str, body: Decision):
    if body.decision not in ('approve', 'query', 'inspect'):
        raise HTTPException(400, 'Choose approve, query or inspect')
    with session() as s:
        a = s.get(Application, app_id)
        who = body.officer or a.officer or 'Scrutiny officer'
        a.decision, a.decision_note, a.status = body.decision, body.note, 'decided'
        a.decided_by, a.decided_at = who, datetime.now()
        if body.decision != 'inspect':
            a.inspection_outcome = ''
        audit.log(s, who, f'Officer decision: {body.decision.upper()}', app_id, {'note': body.note, 'risk': a.risk})
        s.commit()
        return {'ok': True}


class Outcome(BaseModel):
    outcome: str
    officer: str = ''


@app.post('/api/applications/{app_id}/inspection')
def inspection_outcome(app_id: str, body: Outcome):
    if body.outcome not in ('confirmed', 'no_problem'):
        raise HTTPException(400, 'Choose confirmed or no_problem')
    with session() as s:
        a = s.get(Application, app_id)
        if a.decision != 'inspect':
            raise HTTPException(400, 'Order an inspection first')
        a.inspection_outcome = body.outcome
        audit.log(s, body.officer or a.officer or 'Inspection team', 'Inspection result recorded', app_id,
                  {'outcome': 'problem confirmed' if body.outcome == 'confirmed' else 'no problem found'})
        s.commit()
        return {'ok': True}


class Dismiss(BaseModel):
    rule: str
    detail: str
    note: str = ''
    officer: str = ''
    restore: bool = False


@app.post('/api/applications/{app_id}/dismiss')
def dismiss_flag(app_id: str, body: Dismiss):
    """Officer overrules a flag. It stays visible, stops counting, and feeds the 'overruled flags' figure."""
    with session() as s:
        key = pipeline.dismissal_key(body.rule, body.detail)
        s.query(FlagDismissal).filter_by(application_id=app_id, key=key).delete()
        a = s.get(Application, app_id)
        who = body.officer or a.officer or 'Scrutiny officer'
        if not body.restore:
            if not body.note.strip():
                raise HTTPException(400, 'Say why the flag is wrong, so the record shows it')
            s.add(FlagDismissal(application_id=app_id, rule_id=body.rule, key=key, note=body.note.strip(), officer=who))
        audit.log(s, who, 'Flag restored' if body.restore else 'Flag dismissed', app_id, {'rule': body.rule, 'note': body.note})
        pipeline.process(s, app_id, actor='Re-scored after officer review', cascade=False)
        s.commit()
        return {'ok': True, 'risk': a.risk, 'lane': a.lane}


# ------------------------------------------------------------------ document previews (red boxes, heat-map)
def _boxes(q):
    out = []
    for part in (q or '').split(';'):
        try:
            v = [float(x) for x in part.split(',')]
            if len(v) == 4:
                out.append(v)
        except ValueError:
            pass
    return out


def preview_png(d, page=0, boxes=(), crop=False):
    if d.path.lower().endswith('.pdf'):
        return forensics.pdf_preview(d.path, page, boxes, crop=crop)
    return forensics.image_preview(d.path, boxes, crop=crop)


@app.get('/api/documents/{doc_id}/preview')
def doc_preview(doc_id: int, page: int = 0, boxes: str = ''):
    with session() as s:
        d = s.get(Document, doc_id)
        if not d:
            raise HTTPException(404)
        return Response(preview_png(d, page, _boxes(boxes)), media_type='image/png')


@app.get('/api/documents/{doc_id}/heatmap')
def doc_heatmap(doc_id: int):
    with session() as s:
        d = s.get(Document, doc_id)
        if not d or d.path.lower().endswith('.pdf'):
            raise HTTPException(404, 'Heat-maps are made for scanned images')
        return Response(forensics.heatmap(d.path), media_type='image/png')


@app.post('/api/applications/{app_id}/reprocess')
def reprocess(app_id: str):
    with session() as s:
        pipeline.process(s, app_id, actor='Officer re-run')
        s.commit()
        return {'ok': True}


# ------------------------------------------------------------------ college submission
def _next_id(s, prefix):
    n = s.query(Application).count() + 1
    while s.get(Application, f'{prefix}-{n:04d}'):
        n += 1
    return f'{prefix}-{n:04d}'


def save_upload(app_id, kind, filename, data: bytes, s, root=None):
    folder = os.path.join(root or UPLOADS, app_id)
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename) or 'file'
    path = os.path.join(folder, f'{kind}__{safe}')
    with open(path, 'wb') as f:
        f.write(data)
    d = Document(application_id=app_id, kind=kind, filename=filename, path=path, sha256=hashlib.sha256(data).hexdigest())
    s.add(d)
    return d


def assign_officer(s):
    """The officer with the fewest undecided files gets the next one."""
    load = {o['name']: 0 for o in officers()}
    for a in s.query(Application).filter(Application.decision == '').all():
        if a.officer in load:
            load[a.officer] += 1
    return min(load, key=lambda k: (load[k], list(load).index(k)))


def create_application(s, *, code, name, district, lat, lng, category, programme, intake, academic_year, files, created=None,
                       root=None, officer=None):
    inst = s.query(Institution).filter_by(code=code).first()
    if not inst:
        inst = Institution(code=code, name=name, district=district, lat=lat, lng=lng)
        s.add(inst)
        s.flush()
    prefix = 'EOA-27' if category.lower().startswith('extension') else 'NEW-27' if category.lower().startswith('new') else 'CHG-27'
    a = Application(id=_next_id(s, prefix), institution_id=inst.id, category=category, programme=programme,
                    intake=intake, academic_year=academic_year, created=created or datetime.now(),
                    officer=officer or assign_officer(s))
    s.add(a)
    s.flush()
    for kind, fname, data in files:
        save_upload(a.id, kind, fname, data, s, root=root)
    s.flush()
    audit.log(s, name, 'Application submitted', a.id, {'documents': [f[1] for f in files]})
    return a


async def _files(fire_noc, land_doc, faculty_list, lab_photos):
    files = []
    for kind, up in [('fire_noc', fire_noc), ('land_doc', land_doc), ('faculty_list', faculty_list)]:
        if up and up.filename:
            files.append((kind, up.filename, await up.read()))
    for up in lab_photos or []:
        if up and up.filename:
            files.append(('lab_photo', up.filename, await up.read()))
    return files


@app.post('/api/applications')
async def submit(request: Request, code: str = Form(...), name: str = Form(...), district: str = Form(''), lat: float = Form(None),
                 lng: float = Form(None), category: str = Form('Extension of Approval'), programme: str = Form('UG Engineering'),
                 intake: int = Form(...), fire_noc: UploadFile = File(None), land_doc: UploadFile = File(None),
                 faculty_list: UploadFile = File(None), lab_photos: list[UploadFile] = File(None)):
    files = await _files(fire_noc, land_doc, faculty_list, lab_photos)
    with session() as s:
        rules = pipeline.active_rules(s)
        a = create_application(s, code=code.strip().upper(), name=name.strip(), district=district, lat=lat, lng=lng,
                               category=category, programme=programme, intake=intake,
                               academic_year=rules['academic_year'], files=files)
        pipeline.process(s, a.id)
        cs = capture.new_session(s, a.id, rules.get('capture_minutes', 30), rules.get('capture_shots'), started_by='Pramaan (on submission)')
        audit.log(s, 'Pramaan', 'Live capture session opened', a.id, {'code': cs.code, 'minutes': rules.get('capture_minutes', 30)})
        s.commit()
        return {'id': a.id, 'risk': a.risk, 'lane': a.lane, 'capture': _session_json(cs, request)}


# ------------------------------------------------------------------ teacher SMS (simulated phone)
@app.get('/api/sms/phones')
def sms_phones():
    with session() as s:
        out = {}
        for m in s.query(SmsMessage).order_by(SmsMessage.id).all():
            p = out.setdefault(m.phone, {'phone': m.phone, 'name': m.faculty_name, 'messages': 0, 'waiting': 0})
            p['messages'] += 1
            p['waiting'] += m.status == 'sent'
        return list(out.values())


@app.get('/api/sms')
def sms_inbox(phone: str):
    with session() as s:
        return [{'id': m.id, 'text': m.text, 'status': m.status, 'institution': m.institution_name,
                 'application': m.application_id, 'created': m.created.strftime('%d %b %H:%M'),
                 'replied': m.replied.strftime('%d %b %H:%M') if m.replied else None}
                for m in s.query(SmsMessage).filter_by(phone=phone).order_by(SmsMessage.id).all()]


class Reply(BaseModel):
    answer: str


@app.post('/api/sms/{sms_id}/reply')
def sms_reply(sms_id: int, body: Reply):
    ans = body.answer.strip().lower()
    if ans not in ('yes', 'no'):
        raise HTTPException(400, 'Reply YES or NO')
    with session() as s:
        m = s.get(SmsMessage, sms_id)
        m.status, m.replied, m.channel = ans, datetime.now(), 'sms'
        audit.log(s, f'Teacher {m.faculty_name}', f'SMS reply: {ans.upper()}', m.application_id, {'institution': m.institution_name})
        pipeline.process(s, m.application_id, actor='Pramaan (after SMS reply)', cascade=False)
        s.commit()
        a = s.get(Application, m.application_id)
        return {'ok': True, 'application': a.id, 'risk': a.risk, 'lane': a.lane}


# ------------------------------------------------------------------ rulebook
@app.get('/api/rules')
def get_rules():
    with session() as s:
        versions = [{'id': r.id, 'version': r.version, 'active': r.active, 'created': r.created.strftime('%Y-%m-%d %H:%M'), 'note': r.note}
                    for r in s.query(RuleVersion).order_by(RuleVersion.id.desc()).all()]
        return {'active': pipeline.active_rules(s), 'versions': versions}


class NewRules(BaseModel):
    data: dict
    note: str = ''


@app.post('/api/rules')
def save_rules(body: NewRules):
    with session() as s:
        old = pipeline.active_rules(s)
        base = old['version'].split(' v')[0]
        n = s.query(RuleVersion).count() + 2  # v1 is the built-in rulebook
        data = body.data
        data['version'] = f'{base} v{n}'
        for r in s.query(RuleVersion).all():
            r.active = False
        s.add(RuleVersion(version=data['version'], data=json.dumps(data), active=True, note=body.note))
        audit.log(s, 'Rule administrator', 'Rulebook updated', '', {'version': data['version'], 'note': body.note})
        for a in s.query(Application).all():
            pipeline.process(s, a.id, actor=f'Re-check with {data["version"]}', cascade=False)
        s.commit()
        return {'ok': True, 'version': data['version']}


# ------------------------------------------------------------------ audit
@app.get('/api/audit')
def get_audit(limit: int = 200):
    with session() as s:
        rows = s.query(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit).all()
        return [{'id': e.id, 'ts': e.ts, 'actor': e.actor, 'action': e.action, 'application': e.application_id,
                 'payload': jload(e.payload, {}), 'hash': e.hash, 'prev': e.prev_hash} for e in rows]


@app.get('/api/audit/verify')
def verify_audit():
    with session() as s:
        return audit.verify(s)


@app.post('/api/demo/tamper')
def demo_tamper():
    """Demo only: quietly edits an old log entry the way an insider might, to show the chain catches it."""
    with session() as s:
        e = s.query(AuditEntry).filter(AuditEntry.action == 'Pre-screened application').order_by(AuditEntry.id).first()
        p = jload(e.payload, {})
        p['risk'] = 5
        p['lane'] = 'Fast track'
        e.payload = json.dumps(p, sort_keys=True)
        s.commit()
        return {'ok': True, 'edited_entry': e.id}


@app.post('/api/demo/reset')
def demo_reset():
    from seed.seed import seed
    seed(quiet=True)
    return {'ok': True}


# ------------------------------------------------------------------ cross-college graph
@app.get('/api/graph')
def graph():
    with session() as s:
        nodes, links = {}, []
        for f in s.query(Faculty).all():
            if not f.pan_hash:
                continue
            others = s.query(Faculty).filter(Faculty.pan_hash == f.pan_hash, Faculty.institution_id != f.institution_id).count()
            if others:
                inst = s.get(Institution, f.institution_id)
                nodes[f'i{inst.id}'] = {'id': f'i{inst.id}', 'label': inst.name, 'type': 'institution'}
                nodes[f't{f.pan_hash[:10]}'] = {'id': f't{f.pan_hash[:10]}', 'label': f'{f.name} ({f.pan_masked})', 'type': 'teacher'}
                links.append({'source': f'i{inst.id}', 'target': f't{f.pan_hash[:10]}', 'type': 'teacher'})
        for fd in s.query(Finding).filter(Finding.rule_id == 'R-IMG-01', Finding.weight > 0).all():
            ev = jload(fd.evidence, {})
            a = s.get(Application, fd.application_id)
            inst = a.institution
            pid = f'p{ev.get("doc_id")}'
            nodes[f'i{inst.id}'] = {'id': f'i{inst.id}', 'label': inst.name, 'type': 'institution'}
            oinst = s.query(Institution).filter_by(name=ev.get('other_institution')).first()
            if oinst:
                nodes[f'i{oinst.id}'] = {'id': f'i{oinst.id}', 'label': oinst.name, 'type': 'institution'}
                nodes[pid] = {'id': pid, 'label': f'Lab photo ({ev.get("distance")}/64)', 'type': 'photo'}
                links.append({'source': f'i{inst.id}', 'target': pid, 'type': 'photo'})
                links.append({'source': f'i{oinst.id}', 'target': pid, 'type': 'photo'})
        seen, uniq = set(), []
        for l in links:
            k = (l['source'], l['target'])
            if k not in seen:
                seen.add(k); uniq.append(l)
        return {'nodes': list(nodes.values()), 'links': uniq}


@app.get('/api/qr')
def qr_png(text: str):
    import io as _io
    import qrcode
    img = qrcode.make(text, box_size=8, border=2)
    b = _io.BytesIO()
    img.save(b, 'PNG')
    return Response(b.getvalue(), media_type='image/png')


# ------------------------------------------------------------------ network info (links a phone can open)
@app.get('/api/netinfo')
def netinfo(request: Request):
    return {'base': net.public_base(request), 'lan_ips': net.lan_ips(), 'scheme': request.url.scheme,
            'loopback_only': net.is_loopback_only(request) and request.url.scheme != 'https'}


# ------------------------------------------------------------------ live capture
def _session_json(cs, request=None):
    now = datetime.now()
    link = (net.public_base(request) if request else '/') + f'#capture/{cs.id}'
    return {'token': cs.id, 'code': cs.code, 'shots': jload(cs.shots, []), 'created': cs.created.strftime('%d %b %H:%M'),
            'expires': cs.expires.strftime('%d %b %H:%M'), 'expires_iso': cs.expires.isoformat(),
            'open': cs.expires > now, 'minutes_left': max(0, int((cs.expires - now).total_seconds() // 60)),
            'surprise': bool(cs.surprise), 'started_by': cs.started_by, 'link': link}


def _shot_json(s, sh):
    r = jload(sh.result, {})
    unique = not s.query(Finding).filter(Finding.application_id == sh.application_id, Finding.rule_id == 'R-IMG-01',
                                         Finding.weight > 0, Finding.evidence.like(f'%"doc_id": {sh.document_id},%')).count()
    return {'id': sh.id, 'shot': sh.shot, 'doc_id': sh.document_id, 'lat': sh.lat, 'lng': sh.lng,
            'accuracy': round(sh.accuracy or 0), 'taken': sh.taken.strftime('%d %b %H:%M:%S'),
            'checks': {'inside': r.get('inside'), 'time': r.get('in_window'), 'code': r.get('code'), 'unique': unique,
                       'live': r.get('live')},
            'outside_m': r.get('outside_m'), 'late_min': r.get('late_min'), 'live_detail': r.get('why') or (
                f"{r.get('inlier_pct')}% of points fit one flat plane" if r.get('inlier_pct') is not None else ''),
            'code_read': r.get('code_read', '')}


@app.get('/api/applications/{app_id}/capture')
def capture_info(app_id: str, request: Request):
    with session() as s:
        a = s.get(Application, app_id)
        if not a:
            raise HTTPException(404)
        poly, src = capture.boundary(s, a.institution)
        sessions = s.query(CaptureSession).filter_by(application_id=app_id).order_by(CaptureSession.created.desc()).all()
        shots = s.query(CaptureShot).filter_by(application_id=app_id).order_by(CaptureShot.taken).all()
        return {'boundary': poly, 'boundary_source': src, 'campus': [a.institution.lat, a.institution.lng],
                'sessions': [{**_session_json(cs, request), 'shots_taken': sum(1 for x in shots if x.session_id == cs.id)} for cs in sessions],
                'shots': [{**_shot_json(s, x), 'session': x.session_id} for x in shots],
                'loopback_only': net.is_loopback_only(request) and request.url.scheme != 'https'}


class NewSession(BaseModel):
    officer: str = ''


@app.post('/api/applications/{app_id}/capture')
def capture_start(app_id: str, body: NewSession, request: Request):
    """A surprise session: the college gets the link and must finish within the window."""
    with session() as s:
        rules = pipeline.active_rules(s)
        a = s.get(Application, app_id)
        cs = capture.new_session(s, app_id, rules.get('capture_minutes', 30), rules.get('capture_shots'),
                                 started_by=body.officer or a.officer or 'Scrutiny officer', surprise=True)
        audit.log(s, cs.started_by, 'Surprise capture session started', app_id, {'code': cs.code})
        s.commit()
        return _session_json(cs, request)


@app.get('/api/capture/{token}')
def capture_public(token: str, request: Request):
    with session() as s:
        cs = s.get(CaptureSession, token)
        if not cs:
            raise HTTPException(404, 'This capture link is not valid. Ask AICTE for a new one.')
        a = s.get(Application, cs.application_id)
        done = [x.shot for x in s.query(CaptureShot).filter_by(session_id=token).all()]
        return {**_session_json(cs, request), 'institution': a.institution.name, 'application': a.id, 'done': done}


@app.post('/api/capture/{token}/shot')
async def capture_shot(token: str, shot: str = Form(...), lat: float = Form(None), lng: float = Form(None),
                       accuracy: float = Form(None), frame1: UploadFile = File(...), frame2: UploadFile = File(None)):
    f1 = await frame1.read()
    f2 = await frame2.read() if frame2 else b''
    with session() as s:
        cs = s.get(CaptureSession, token)
        if not cs:
            raise HTTPException(404, 'This capture link is not valid. Ask AICTE for a new one.')
        a = s.get(Application, cs.application_id)
        sh, res = capture.add_shot(s, cs, a, shot, f1, f2, lat, lng, accuracy, os.path.join(UPLOADS, a.id))
        audit.log(s, f'{a.institution.name} (live capture)', 'Live photo received', a.id,
                  {'shot': shot, 'inside': res.get('inside'), 'code': res.get('code'), 'live': res.get('live')})
        pipeline.process(s, a.id, actor='Pramaan (live capture)')
        s.commit()
        return {'ok': True, 'shot': _shot_json(s, sh), 'risk': a.risk, 'lane': a.lane}


# ------------------------------------------------------------------ reports
class ReportReq(BaseModel):
    kind: str = 'internal'
    officer: str = ''


@app.post('/api/applications/{app_id}/report')
def make_report(app_id: str, body: ReportReq, request: Request):
    if body.kind not in ('internal', 'college'):
        raise HTTPException(400, 'kind must be internal or college')
    with session() as s:
        a = s.get(Application, app_id)
        if not a:
            raise HTTPException(404)
        rules = pipeline.active_rules(s)
        case = case_dict(s, a)
        officer = body.officer or a.officer or 'Scrutiny officer'
        rid = reports.new_id('RPT' if body.kind == 'internal' else 'QRY')
        url = net.public_base(request) + f'#verify/{rid}'
        file_for = lambda doc_id: s.get(Document, doc_id).path

        def preview_for(pv):
            d = s.get(Document, pv['doc_id'])
            if pv.get('heatmap'):
                return forensics.heatmap(d.path)
            return preview_png(d, pv.get('page', 0), pv.get('boxes', []), crop=True)
        pdf, payload, sig = reports.application_report(case, rules, body.kind, officer, url, rid, file_for, preview_for)
        path, sha = reports.save(pdf, rid)
        s.add(Report(id=rid, application_id=app_id, kind=body.kind, officer=officer, payload=json.dumps(payload, ensure_ascii=False),
                     signature=sig, sha256=sha, path=path))
        audit.log(s, officer, 'Report issued' if body.kind == 'internal' else 'Query letter issued', app_id,
                  {'report': rid, 'sha256': sha[:16]})
        s.commit()
        return {'id': rid, 'pdf': f'/api/reports/{rid}/pdf', 'verify': url, 'sha256': sha}


@app.get('/api/reports/{rid}/pdf')
def report_pdf(rid: str):
    with session() as s:
        r = s.get(Report, rid)
        if not r or not os.path.exists(r.path):
            raise HTTPException(404)
        name = {'internal': 'scrutiny_report', 'college': 'query_letter', 'teacher': 'claims_statement'}.get(r.kind, 'report')
        return FileResponse(r.path, media_type='application/pdf', filename=f'{name}_{rid}.pdf', content_disposition_type='inline')


def _verify(s, rid, data=None):
    r = s.get(Report, rid)
    if not r:
        return {'found': False, 'genuine': False, 'message': 'No report with this number was issued by Pramaan.'}
    payload = json.loads(r.payload)
    ok = reports.check_signature(payload, r.signature)
    out = {'found': True, 'genuine': ok, 'id': rid, 'kind': r.kind, 'payload': payload, 'sha256': r.sha256,
           'public_key': reports.public_key_b64(),
           'message': 'Report genuine: signed by Pramaan and unchanged since it was issued.' if ok
           else 'Signature check failed: the stored report was changed after it was issued.'}
    if data is not None:
        got = hashlib.sha256(data).hexdigest()
        out['file_sha256'] = got
        out['file_matches'] = got == r.sha256
        if not out['file_matches']:
            out['genuine'] = False
            out['message'] = 'This file is not the one Pramaan issued: its fingerprint differs, so it was edited or replaced.'
        elif ok:
            out['message'] = 'Report genuine: this exact file was issued by Pramaan and has not been changed.'
    return out


@app.get('/api/reports/{rid}/verify')
def report_verify(rid: str):
    with session() as s:
        return _verify(s, rid)


@app.post('/api/reports/{rid}/verify')
async def report_verify_file(rid: str, file: UploadFile = File(...)):
    data = await file.read()
    with session() as s:
        return _verify(s, rid, data)


# ------------------------------------------------------------------ college self-check (practice mode)
PRACTICE_ITEMS = [
    ('R-DOC-01', 'All required documents uploaded'),
    ('R-READ-01', 'Every document can be read'),
    ('R-SRC-04', 'Fire NOC has a readable issuer QR code'),
    ('R-DOC-02', 'Fire NOC is valid for the academic year'),
    ('R-NORM-01', 'Faculty meets the student : teacher norm'),
    ('R-XINST-01', 'No teacher is listed by another institution'),
    ('R-IMG-03', 'Photos are original camera photos'),
]


@app.post('/api/practice')
async def practice(code: str = Form(...), name: str = Form(...), district: str = Form(''), lat: float = Form(None),
                   lng: float = Form(None), category: str = Form('Extension of Approval'), programme: str = Form('UG Engineering'),
                   intake: int = Form(...), fire_noc: UploadFile = File(None), land_doc: UploadFile = File(None),
                   faculty_list: UploadFile = File(None), lab_photos: list[UploadFile] = File(None)):
    """Runs the real engine, keeps only compliance checks, then throws everything away.
    Fraud checks stay hidden so a forger cannot keep trying until a fake passes."""
    code = code.strip().upper()
    files = await _files(fire_noc, land_doc, faculty_list, lab_photos)
    today = datetime.combine(datetime.now().date(), datetime.min.time())
    with session() as s:
        rules = pipeline.active_rules(s)
        limit = rules.get('practice_runs_per_day', 5)
        used = s.query(PracticeRun).filter(PracticeRun.code == code, PracticeRun.created >= today).count()
        if used >= limit:
            raise HTTPException(429, f'{code} has used all {limit} practice checks for today. Try again tomorrow.')
        s.add(PracticeRun(code=code))
        s.commit()
    tmp = tempfile.mkdtemp(prefix='pramaan-practice-')
    s = session()
    try:
        a = create_application(s, code=code, name=name.strip(), district=district, lat=lat, lng=lng, category=category,
                               programme=programme, intake=intake, academic_year=rules['academic_year'], files=files,
                               root=tmp, officer='(practice)')
        found = pipeline.process(s, a.id, cascade=False, practice=True)
        allowed = {k for k, r in rules['rules'].items() if r.get('practice')}
        shown = [f for f in found if f.rule_id in allowed and f.weight > 0]
        items = []
        for rid, label in PRACTICE_ITEMS:
            fs = [f for f in shown if f.rule_id == rid]
            tips = []
            for f in fs:
                ev = {k: pipeline._human(v) for k, v in {**jload(f.evidence, {}), 'academic_year_start': rules['academic_year_start']}.items()}
                t = rules['rules'][rid]['fix'].format_map(pipeline._Blank(ev))
                if t not in tips:
                    tips.append(t)
            items.append({'rule': rid, 'label': label.replace('student : teacher', f'1:{rules["faculty_student_ratio"]}'),
                          'ok': not fs, 'tips': tips})
    finally:
        s.rollback()
        s.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return {'items': items, 'passed': sum(i['ok'] for i in items), 'total': len(items),
            'runs_left': max(0, limit - used - 1), 'limit': limit}


# ------------------------------------------------------------------ teacher portal
def _digits(p):
    return re.sub(r'\D', '', p or '')[-10:]


def _faculty_by_phone(s, phone):
    want = _digits(phone)
    return [f for f in s.query(Faculty).all() if want and _digits(f.phone) == want]


class OtpReq(BaseModel):
    phone: str


@app.post('/api/teacher/otp')
def teacher_otp(body: OtpReq):
    with session() as s:
        if not _faculty_by_phone(s, body.phone):
            raise HTTPException(404, 'This mobile number is not on any faculty list.')
        otp = f'{secrets.randbelow(900000) + 100000}'
        s.query(TeacherOtp).filter_by(phone=_digits(body.phone)).delete()
        s.add(TeacherOtp(phone=_digits(body.phone), otp=otp, expires=datetime.now() + timedelta(minutes=5)))
        s.commit()
        d = _digits(body.phone)
        return {'sent': True, 'to': f'+91 •••••• {d[-4:]}', 'demo_otp': otp}


class LoginReq(BaseModel):
    phone: str
    otp: str
    pan_last4: str


@app.post('/api/teacher/login')
def teacher_login(body: LoginReq):
    with session() as s:
        o = s.query(TeacherOtp).filter_by(phone=_digits(body.phone)).first()
        if not o or o.otp != body.otp.strip() or o.expires < datetime.now():
            raise HTTPException(401, 'The OTP is wrong or has expired. Ask for a new one.')
        last4 = body.pan_last4.strip().upper()
        rows = [f for f in _faculty_by_phone(s, body.phone) if f.pan_hash and (f.pan_masked or '').endswith(last4) and len(last4) == 4]
        if not rows:
            raise HTTPException(401, 'The last 4 characters of the PAN do not match this mobile number.')
        ph = rows[0].pan_hash
        acc = s.query(TeacherAccount).filter_by(pan_hash=ph).first()
        if not acc:
            acc = TeacherAccount(pan_hash=ph, phone=_digits(body.phone))
            s.add(acc)
        acc.previous_seen, acc.last_seen, acc.token = acc.last_seen, datetime.now(), secrets.token_urlsafe(24)
        s.delete(o)
        s.commit()
        return {'token': acc.token}


STATUS_LABEL = {'yes': 'Confirmed', 'no': 'Denied', 'sent': 'Not answered', None: 'Not answered'}


def _teacher(s, token):
    acc = s.query(TeacherAccount).filter_by(token=token).first() if token else None
    if not acc:
        raise HTTPException(401, 'Please sign in again.')
    return acc


def _claims(s, acc):
    out = []
    for f in s.query(Faculty).filter_by(pan_hash=acc.pan_hash).all():
        a = s.get(Application, f.application_id)
        if not a:
            continue
        sms = s.query(SmsMessage).filter_by(pan_hash=acc.pan_hash, application_id=a.id).first()
        status = sms.status if sms else None
        label = 'Reported misuse' if sms and sms.channel == 'portal-misuse' else STATUS_LABEL.get(status, 'Not answered')
        new = acc.previous_seen is None or (a.created and a.created > acc.previous_seen)
        out.append({'faculty_id': f.id, 'application': a.id, 'institution': a.institution.name, 'district': a.institution.district,
                    'academic_year': a.academic_year, 'designation': f.designation, 'listed_on': a.created.strftime('%d %b %Y'),
                    'status': status or 'sent', 'status_label': label, 'new': bool(new and status in (None, 'sent')),
                    'name': f.name, 'pan': f.pan_masked})
    return sorted(out, key=lambda c: (c['academic_year'], c['listed_on']), reverse=True)


@app.get('/api/teacher/me')
def teacher_me(token: str):
    with session() as s:
        acc = _teacher(s, token)
        claims = _claims(s, acc)
        name = Counter(c['name'] for c in claims).most_common(1)[0][0] if claims else 'Teacher'
        return {'name': name, 'pan': claims[0]['pan'] if claims else '', 'phone': f'+91 •••••• {acc.phone[-4:]}',
                'previous_seen': acc.previous_seen.strftime('%d %b %Y %H:%M') if acc.previous_seen else None,
                'claims': claims, 'alerts': [c for c in claims if c['new']]}


class ClaimAction(BaseModel):
    token: str
    action: str  # confirm | deny | misuse
    note: str = ''


@app.post('/api/teacher/claims/{faculty_id}')
def teacher_claim(faculty_id: int, body: ClaimAction):
    if body.action not in ('confirm', 'deny', 'misuse'):
        raise HTTPException(400, 'Choose confirm, deny or misuse')
    with session() as s:
        acc = _teacher(s, body.token)
        f = s.get(Faculty, faculty_id)
        if not f or f.pan_hash != acc.pan_hash:
            raise HTTPException(403, 'This listing is not yours.')
        a = s.get(Application, f.application_id)
        sms = s.query(SmsMessage).filter_by(pan_hash=f.pan_hash, application_id=a.id).first()
        if not sms:
            sms = SmsMessage(phone=f.phone, faculty_name=f.name, pan_hash=f.pan_hash, application_id=a.id,
                             institution_name=a.institution.name,
                             text=f'{a.institution.name} has listed you as faculty for {a.academic_year}. (teacher portal)')
            s.add(sms)
        sms.status = 'yes' if body.action == 'confirm' else 'no'
        sms.channel = 'portal-misuse' if body.action == 'misuse' else 'portal'
        sms.replied = datetime.now()
        what = {'confirm': 'Teacher portal: confirmed', 'deny': 'Teacher portal: denied', 'misuse': 'Teacher portal: misuse reported'}[body.action]
        audit.log(s, f'Teacher {f.name}', what, a.id, {'institution': a.institution.name, 'note': body.note})
        pipeline.process(s, a.id, actor='Pramaan (after teacher portal)', cascade=False)
        s.commit()
        return {'ok': True, 'application': a.id, 'risk': a.risk, 'lane': a.lane}


@app.get('/api/teacher/statement')
def teacher_statement(token: str, request: Request):
    with session() as s:
        acc = _teacher(s, token)
        claims = _claims(s, acc)
        name = Counter(c['name'] for c in claims).most_common(1)[0][0] if claims else 'Teacher'
        rid = reports.new_id('TCS')
        url = net.public_base(request) + f'#verify/{rid}'
        pdf, payload, sig = reports.teacher_statement(name, claims[0]['pan'] if claims else '', claims, url, rid)
        path, sha = reports.save(pdf, rid)
        s.add(Report(id=rid, application_id='', kind='teacher', officer=name, payload=json.dumps(payload, ensure_ascii=False),
                     signature=sig, sha256=sha, path=path))
        s.commit()
        return Response(pdf, media_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="employment_claims_{rid}.pdf"'})


# ------------------------------------------------------------------ region dashboard
@app.get('/api/dashboard')
def dashboard():
    with session() as s:
        rules = pipeline.active_rules(s)
        now = datetime.now()
        apps = s.query(Application).all()
        decided = [a for a in apps if a.decision]
        days = [(a.decided_at - a.created).total_seconds() / 86400 for a in decided if a.decided_at and a.created]
        lanes = Counter(a.lane for a in apps)
        tiles = {'received': len(apps), 'checked': sum(1 for a in apps if a.processed), 'decided': len(decided),
                 'lanes': {'Inspect': lanes.get('Inspect', 0), 'Review': lanes.get('Review', 0), 'Fast track': lanes.get('Fast track', 0)},
                 'avg_days': round(sum(days) / len(days), 1) if days else None,
                 'pending_15': sum(1 for a in apps if not a.decision and a.created and (now - a.created).days > 15)}
        # districts
        dist = defaultdict(list)
        for a in apps:
            dist[a.institution.district].append({'id': a.id, 'name': a.institution.name, 'risk': a.risk, 'lane': a.lane})
        districts = {d: {'avg_risk': round(sum(c['risk'] for c in cs) / len(cs)), 'colleges': sorted(cs, key=lambda c: -c['risk'])}
                     for d, cs in dist.items()}
        # which rules fire most (current cycle, not counting dismissed)
        fs = s.query(Finding).filter(Finding.weight > 0).all()
        rc = Counter(f.rule_id for f in fs if not f.dismissed)
        rule_counts = [{'rule': r, 'title': rules['rules'].get(r, {}).get('title', r), 'count': n,
                        'apps': len({f.application_id for f in fs if f.rule_id == r and not f.dismissed})}
                       for r, n in rc.most_common(10)]
        # repeat offenders: flagged in 2 or more cycles
        flagged = defaultdict(list)
        for p in s.query(PastCycle).all():
            if p.lane in ('Inspect', 'Review'):
                flagged[p.institution_code].append(p.academic_year)
        names = {}
        for a in apps:
            names[a.institution.code] = (a.institution.name, a.id)
            if a.lane in ('Inspect', 'Review'):
                flagged[a.institution.code].append(a.academic_year)
        repeat = sorted([{'code': c, 'name': names.get(c, (c, ''))[0], 'application': names.get(c, ('', ''))[1],
                          'years': sorted(set(y))} for c, y in flagged.items() if len(set(y)) >= 2],
                        key=lambda r: -len(r['years']))
        # teacher-sharing rings: colleges joined by a shared PAN
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        by_pan = defaultdict(set)
        for f in s.query(Faculty).all():
            if f.pan_hash:
                by_pan[f.pan_hash].add(f.institution_id)
        shared_pans = {p: i for p, i in by_pan.items() if len(i) > 1}
        for insts in shared_pans.values():
            insts = list(insts)
            for x in insts[1:]:
                parent[find(x)] = find(insts[0])
        groups = defaultdict(set)
        for insts in shared_pans.values():
            for i in insts:
                groups[find(i)].add(i)
        rings = []
        for root, members in groups.items():
            teachers = sum(1 for insts in shared_pans.values() if find(next(iter(insts))) == root)
            rings.append({'colleges': sorted(s.get(Institution, i).name for i in members), 'teachers': teachers})
        rings.sort(key=lambda r: -len(r['colleges']))
        # officer workload
        off = []
        for o in officers():
            mine = [a for a in apps if a.officer == o['name']]
            done = [a for a in mine if a.decision]
            dd = [(a.decided_at - a.created).total_seconds() / 86400 for a in done if a.decided_at and a.created]
            off.append({'name': o['name'], 'assigned': len(mine), 'pending': len(mine) - len(done), 'decided': len(done),
                        'avg_days': round(sum(dd) / len(dd), 1) if dd else None,
                        'oldest_pending_days': max([(now - a.created).days for a in mine if not a.decision] or [0])})
        # is Pramaan accurate?
        insp = [(a.inspection_outcome, 'current') for a in apps if a.decision == 'inspect' and a.inspection_outcome]
        insp += [(p.inspection_outcome, 'past') for p in s.query(PastCycle).filter(PastCycle.decision == 'inspect').all() if p.inspection_outcome]
        hits = sum(1 for o, _ in insp if o == 'confirmed')
        total_flags = len(fs)
        dismissed = [f for f in fs if f.dismissed]
        per_rule = []
        for r in sorted({f.rule_id for f in fs}):
            n = sum(1 for f in fs if f.rule_id == r)
            d = sum(1 for f in dismissed if f.rule_id == r)
            if d:
                per_rule.append({'rule': r, 'title': rules['rules'].get(r, {}).get('title', r), 'dismissed': d, 'total': n,
                                 'pct': round(100 * d / n)})
        per_rule.sort(key=lambda x: -x['pct'])
        accuracy = {'inspections': len(insp), 'confirmed': hits, 'hit_rate': round(100 * hits / len(insp)) if insp else None,
                    'flags': total_flags, 'dismissed': len(dismissed),
                    'overruled_pct': round(100 * len(dismissed) / total_flags) if total_flags else None, 'by_rule': per_rule[:3]}
        return {'tiles': tiles, 'districts': districts, 'rule_counts': rule_counts, 'repeat': repeat, 'rings': rings,
                'officers': off, 'accuracy': accuracy, 'academic_year': rules['academic_year']}


# ------------------------------------------------------------------ mock issuer portal (stands in for DigiLocker / fire service APIs)
@app.get('/mock-issuer/{iss}/certificate/{ref:path}')
def mock_issuer(iss: str, ref: str):
    c = issuers.lookup_certificate(iss, ref)
    if not c:
        return JSONResponse({'found': False}, status_code=404)
    return {'found': True, **c}


# ------------------------------------------------------------------ web app
STATIC = os.path.join(BASE_DIR, 'static')
if os.path.isdir(STATIC):
    app.mount('/assets', StaticFiles(directory=os.path.join(STATIC, 'assets')), name='assets')

    @app.get('/{path:path}')
    def spa(path: str):
        f = os.path.join(STATIC, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(STATIC, 'index.html'))
