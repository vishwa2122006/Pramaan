"""The check engine: reads every document of an application, runs all checks,
records findings with evidence, scores risk and assigns a lane."""
import hashlib
import json
import math
import os
import re
from datetime import date, datetime

from PIL import Image

from . import audit, extract, forensics, issuers, photo
from .db import (DATA_DIR, Application, CaptureShot, Document, Faculty, Finding, FlagDismissal, Institution, PhotoPrint,
                 RuleVersion, SmsMessage, VerifiedFact, jload)

PAN_SALT = os.environ.get('PRAMAAN_PAN_SALT', 'pramaan-demo-salt')
REQUIRED = {'fire_noc': 'Fire NOC', 'land_doc': 'Land document', 'faculty_list': 'Faculty list', 'lab_photo': 'Lab / infrastructure photo'}


def pan_hash(pan):
    return hashlib.sha256((PAN_SALT + pan.strip().upper()).encode()).hexdigest()


def pan_mask(pan):
    p = pan.strip().upper()
    return '****' + p[-4:] if len(p) >= 4 else '****'


def default_rules():
    with open(os.path.join(DATA_DIR, 'rulebook.json'), encoding='utf-8') as f:
        return json.load(f)


def active_rules(s):
    base = default_rules()
    rv = s.query(RuleVersion).filter_by(active=True).order_by(RuleVersion.id.desc()).first()
    if not rv:
        return base
    data = jload(rv.data, {})
    # versions saved before a rule existed still get that rule, with its default weight and wording
    for k, v in base.items():
        data.setdefault(k, v)
    for rid, r in base['rules'].items():
        data['rules'][rid] = {**r, **data['rules'].get(rid, {})}
    return data


class _Blank(dict):
    def __missing__(self, k):
        return '…'


def _human(v):
    """Lists as 'a, b'; ISO dates as dd-mm-yyyy, the way they are printed on Indian certificates."""
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return ', '.join(v)
    if isinstance(v, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
        return f'{v[8:10]}-{v[5:7]}-{v[:4]}'
    return v


def sentence(rules, rule_id, evidence, kind='plain'):
    """Fixed sentence templates from the rulebook: the same finding always gives the same sentence."""
    r = rules['rules'].get(rule_id, {})
    tpl = r.get(kind) or (r.get('plain') if kind == 'college' else None) or r.get('title', rule_id)
    ev = {k: _human(v) for k, v in (evidence or {}).items()}
    ev.setdefault('academic_year_start', _human(rules.get('academic_year_start')))
    try:
        return tpl.format_map(_Blank(ev))
    except Exception:
        return r.get('title', rule_id)


def dismissal_key(rule_id, detail):
    return hashlib.sha256(f'{rule_id}|{detail}'.encode()).hexdigest()[:32]


def holidays():
    with open(os.path.join(DATA_DIR, 'holidays.json'), encoding='utf-8') as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith('_')}


def holiday_name(d):
    h = holidays().get(d)
    if h:
        return h
    if datetime.strptime(d, '%Y-%m-%d').weekday() == 6:
        return 'Sunday'
    return None


class Ctx:
    def __init__(self, s, app, rules, practice=False):
        self.s, self.app, self.rules, self.findings, self.practice = s, app, rules, [], practice

    def flag(self, rule_id, detail, evidence=None, title=None, weight=None):
        r = self.rules['rules'].get(rule_id, {'title': rule_id, 'severity': 'info', 'weight': 0})
        if r.get('enabled') is False:
            return
        self.findings.append(Finding(application_id=self.app.id, rule_id=rule_id, severity=r['severity'],
                                     weight=r['weight'] if weight is None else weight, title=title or r['title'],
                                     detail=detail, evidence=json.dumps(evidence or {}, ensure_ascii=False)))


# ------------------------------------------------------------------ document readers
def read_documents(s, app):
    """Extract text, fields, QR and photo details once per document."""
    for d in s.query(Document).filter_by(application_id=app.id).all():
        meta = jload(d.meta, {})
        if d.kind in ('fire_noc', 'land_doc') and meta.get('read') and 'forensics' not in meta:
            meta['forensics'] = _forensics(d.path)   # documents read by an older version
            d.meta = json.dumps(meta)
        if meta.get('read'):
            continue
        if d.kind in ('lab_photo', 'live_photo'):
            info = photo.exif_info(d.path)
            img = Image.open(d.path)
            meta.update(info)
            meta['dhash'], meta['phash'] = photo.dhash(img), photo.phash(img)
            meta['size'] = img.size
            s.query(PhotoPrint).filter_by(document_id=d.id).delete()
            s.add(PhotoPrint(document_id=d.id, application_id=app.id, institution_id=app.institution_id,
                             dhash=meta['dhash'], phash=meta['phash'], lat=info['lat'], lng=info['lng'],
                             taken=info['taken'], software=info['software']))
        else:
            text, method = extract.read_text(d.path)
            d.text = text
            meta['read_method'] = method
            if d.kind in ('fire_noc', 'land_doc'):
                meta['forensics'] = _forensics(d.path)
                for cv in (meta['forensics'] or {}).get('covers', []):
                    text = text.replace(cv['hidden_text'], '', 1)  # read the page as a person sees it
            if d.kind == 'fire_noc':
                d.fields = json.dumps(extract.parse_fire_noc(text))
                meta['qr'] = extract.read_qr(d.path)
            elif d.kind == 'land_doc':
                d.fields = json.dumps(extract.parse_land(text))
            elif d.kind == 'faculty_list':
                rows = extract.parse_faculty_csv(text)
                s.query(Faculty).filter_by(application_id=app.id).delete()
                for r in rows:
                    if not r['name']:
                        continue
                    s.add(Faculty(application_id=app.id, institution_id=app.institution_id, name=r['name'],
                                  designation=r['designation'], pan_hash=pan_hash(r['pan']) if r['pan'] else '',
                                  pan_masked=pan_mask(r['pan']) if r['pan'] else 'missing', phone=r['phone']))
                d.fields = json.dumps({'rows': len(rows)})
        meta['read'] = True
        d.meta = json.dumps(meta)
    s.flush()


def _forensics(path):
    try:
        return forensics.analyse(path)
    except Exception as e:  # never let a damaged file stop the other checks
        return {'type': 'error', 'error': str(e)}


# ------------------------------------------------------------------ checks
def check_required(c, docs):
    kinds = {('lab_photo' if d.kind == 'live_photo' else d.kind) for d in docs}
    for k, label in REQUIRED.items():
        if k not in kinds:
            c.flag('R-DOC-01', f'{label} was not uploaded.', {'missing': label}, title=f'{label} missing')


def check_fire_noc(c, d):
    f = jload(d.fields, {})
    meta = jload(d.meta, {})
    ev = {'document': d.filename, 'doc_id': d.id, 'read_by': meta.get('read_method')}
    if not any(f.values()):
        c.flag('R-READ-01', f'Could not read the Fire NOC ({meta.get("read_method")}).', ev)
    qr = meta.get('qr')
    truth = None
    if not qr:
        c.flag('R-SRC-04', 'No issuer QR code found on the Fire NOC, so it could not be checked with the fire department.', ev)
    else:
        v = issuers.verify_qr(qr)
        ev['qr_check'] = v['message']
        if v['status'] != 'genuine':
            c.flag('R-SRC-01', v['message'] + '.', {**ev, 'qr_data': v.get('payload')})
        else:
            truth = v['payload']
            cert = issuers.lookup_certificate(truth['iss'], truth['ref'])
            if not cert:
                c.flag('R-SRC-02', f"Issuer has no record of certificate {truth['ref']}.", {**ev, 'ref': truth['ref']})
            elif cert.get('status') != 'valid':
                c.flag('R-SRC-02', f"Issuer reports certificate {truth['ref']} as {cert['status'].upper()}.", {**ev, 'ref': truth['ref'], 'issuer_status': cert['status']})
            # printed text vs signed QR
            pairs = [('noc_number', 'ref', 'NOC number'), ('issued_on', 'issued', 'Date of issue'), ('valid_until', 'valid', 'Valid up to')]
            for fk, qk, label in pairs:
                pv = (f.get(fk) or '').replace(' ', '')
                if pv and pv != truth.get(qk):
                    c.flag('R-SRC-03', f'{label} printed as {f.get(fk)}, but the issuer-signed QR says {truth.get(qk)}.',
                           {**ev, 'field': label, 'printed': f.get(fk), 'issuer_signed': truth.get(qk)})
    if not truth and f.get('noc_number'):
        # no usable QR: ask the issuer about the printed certificate number instead
        ref = f['noc_number'].replace(' ', '')
        iss_code = issuers.registry().get('prefixes', {}).get(ref.split('/')[0])
        if iss_code:
            cert = issuers.lookup_certificate(iss_code, ref)
            if not cert:
                c.flag('R-SRC-02', f'Asked the issuer about NOC {ref}: no such certificate was ever issued.', {**ev, 'ref': ref, 'issuer_reply': 'not found'})
            ev['issuer'] = iss_code
    issued = (truth or {}).get('issued') or f.get('issued_on')
    valid = (truth or {}).get('valid') or f.get('valid_until')
    signer = (truth or {}).get('signer') or f.get('signed_by')
    ay_start = c.rules['academic_year_start']
    if valid and valid < ay_start:
        c.flag('R-DOC-02', f'Valid until {valid}; academic year {c.rules["academic_year"]} starts {ay_start}.',
               {**ev, 'valid_until': valid, 'academic_year_start': ay_start})
    if issued:
        h = holiday_name(issued)
        if h:
            c.flag('R-LOGIC-01', f'Fire NOC dated {issued} ({h}). Government offices are closed that day.', {**ev, 'issued_on': issued, 'holiday': h})
    iss_code = (truth or {}).get('iss') or ev.get('issuer')
    if signer and iss_code:
        o = issuers.officer_tenure(iss_code, signer)
        if o and issued and not (o['from'] <= issued <= o['to']):
            c.flag('R-LOGIC-02', f'{o["name"]} ({o["post"]}) held the post from {o["from"]} to {o["to"]}, but signed on {issued}.',
                   {**ev, 'signer': o['name'], 'in_post': f'{o["from"]} to {o["to"]}', 'signed_on': issued})
    return {'fields': f, 'issuer_data': truth}


def check_land(c, d):
    f = jload(d.fields, {})
    meta = jload(d.meta, {})
    ev = {'document': d.filename, 'doc_id': d.id, 'read_by': meta.get('read_method')}
    if not f.get('survey_number'):
        c.flag('R-READ-01', f'Could not find the survey number in the land document ({meta.get("read_method")}).', ev)
        return
    sn = f['survey_number'].replace(' ', '')
    fact = c.s.query(VerifiedFact).filter_by(institution_id=c.app.institution_id, key='Land survey number').first()
    if fact and fact.value.replace(' ', '') != sn:
        c.flag('R-FACT-01', f'Land document says survey no. {sn}; verified record (checked {fact.verified_on}) says {fact.value}.',
               {**ev, 'uploaded': sn, 'verified': fact.value, 'verified_source': fact.source})
    elif not fact:
        c.s.add(VerifiedFact(institution_id=c.app.institution_id, key='Land survey number', value=sn,
                             source=f'{d.filename} (first submission, awaiting officer confirmation)',
                             verified_on=date.today().isoformat()))


def check_faculty(c, docs):
    s, app = c.s, c.app
    rows = s.query(Faculty).filter_by(application_id=app.id).all()
    if not rows:
        return
    shared = 0
    for fac in rows:
        if not fac.pan_hash:
            continue
        others = (s.query(Faculty, Application, Institution)
                  .join(Application, Faculty.application_id == Application.id)
                  .join(Institution, Application.institution_id == Institution.id)
                  .filter(Faculty.pan_hash == fac.pan_hash, Faculty.institution_id != app.institution_id).all())
        if others:
            shared += 1
            names = sorted({i.name for _, _, i in others})
            c.flag('R-XINST-01', f'{fac.name} ({fac.pan_masked}) is also listed full-time at {", ".join(names)}.',
                   {'teacher': fac.name, 'pan': fac.pan_masked, 'also_at': names, 'match': 'same PAN'})
            sms = s.query(SmsMessage).filter_by(pan_hash=fac.pan_hash, application_id=app.id).first()
            if not sms and not c.practice:
                inst = s.get(Institution, app.institution_id)
                s.add(SmsMessage(phone=fac.phone, faculty_name=fac.name, pan_hash=fac.pan_hash, application_id=app.id,
                                 institution_name=inst.name,
                                 text=f'AICTE: {inst.name} has listed you as FULL-TIME faculty for {c.rules["academic_year"]}. '
                                      f'Reply YES if true or NO if you do not work there.'))
                audit.log(s, 'Pramaan', 'SMS sent to teacher', app.id, {'teacher': fac.name, 'phone': fac.phone})
        sms = s.query(SmsMessage).filter_by(pan_hash=fac.pan_hash, application_id=app.id).first()
        if sms and sms.status == 'no':
            ch = sms.channel or 'sms'
            via = {'portal': 'answered NO in the teacher portal', 'portal-misuse': 'reported misuse of their name in the teacher portal'}.get(ch, 'replied NO to the SMS')
            c.flag('R-SMS-01', f'{fac.name} {via}: does not work at this institution.',
                   {'teacher': fac.name, 'reply': 'NO' if ch != 'portal-misuse' else 'Misuse reported', 'replied': str(sms.replied)[:16],
                    'channel': 'teacher portal' if ch.startswith('portal') else 'SMS'})
    required = math.ceil((app.intake or 0) / c.rules['faculty_student_ratio'])
    effective = len(rows) - shared
    if shared and effective < required:
        c.flag('R-NORM-01', f'{len(rows)} faculty declared and {required} needed (1:{c.rules["faculty_student_ratio"]} for {app.intake} students). '
                            f'{shared} are also claimed elsewhere; without them only {effective} remain.',
               {'declared': len(rows), 'required': required, 'shared': shared, 'effective': effective, 'counted': effective})
    elif len(rows) < required:
        c.flag('R-NORM-01', f'Only {len(rows)} faculty declared; {required} needed.', {'declared': len(rows), 'required': required, 'counted': len(rows)})


def check_photos(c, docs):
    s, app, rules = c.s, c.app, c.rules
    inst = s.get(Institution, app.institution_id)
    for d in [x for x in docs if x.kind in ('lab_photo', 'live_photo')]:
        meta = jload(d.meta, {})
        ev = {'document': d.filename, 'doc_id': d.id}
        mine = s.query(PhotoPrint).filter_by(document_id=d.id).first()
        best = None
        if not mine:
            continue
        for other in s.query(PhotoPrint).filter(PhotoPrint.institution_id != app.institution_id).all():
            dist = photo.hamming(mine.dhash, other.dhash)
            if best is None or dist < best[0]:
                best = (dist, other)
        if best and best[0] <= rules['photo_match_threshold']:
            dist, other = best
            oapp = s.get(Application, other.application_id)
            oinst = s.get(Institution, other.institution_id)
            later = (app.created or datetime.min) >= (oapp.created or datetime.min)
            pev = {**ev, 'other_doc_id': other.document_id, 'other_institution': oinst.name, 'other_application': oapp.id,
                   'distance': dist, 'threshold': rules['photo_match_threshold'],
                   'phash_distance': photo.hamming(mine.phash, other.phash)}
            if later:
                c.flag('R-IMG-01', f'"{d.filename}" matches a photo submitted by {oinst.name} ({oapp.id}): {dist} of 64 fingerprint bits differ (limit {rules["photo_match_threshold"]}).', pev)
            else:
                c.flag('R-IMG-01', f'A later application from {oinst.name} reused this photo ({dist}/64 bits differ). Shown for information.', pev, weight=0,
                       title='This photo was reused by another institution')
        if d.kind == 'live_photo':
            continue  # location and time come from the live capture checks instead of EXIF
        if not meta.get('has_exif') or (meta.get('lat') is None and not meta.get('taken')):
            c.flag('R-IMG-03', f'"{d.filename}" has no camera details (GPS, date). Ask for the original camera photo.', ev)
        if meta.get('lat') is not None and inst.lat is not None:
            km = photo.km_between(meta['lat'], meta['lng'], inst.lat, inst.lng)
            if km > rules['photo_gps_radius_km']:
                c.flag('R-IMG-02', f'"{d.filename}" was taken {km:.1f} km from the campus (limit {rules["photo_gps_radius_km"]} km).',
                       {**ev, 'photo_gps': [meta['lat'], meta['lng']], 'campus': [inst.lat, inst.lng], 'km': round(km, 1)})
        if meta.get('software'):
            c.flag('R-IMG-04', f'"{d.filename}" was saved by {meta["software"]}.', {**ev, 'software': meta['software']})


KIND_NAME = {'fire_noc': 'Fire NOC', 'land_doc': 'Land document'}


def check_forensics(c, d):
    fx = jload(d.meta, {}).get('forensics') or {}
    name = KIND_NAME.get(d.kind, d.filename)
    ev = {'document': name, 'doc_id': d.id, 'file': d.filename}
    if fx.get('type') == 'pdf':
        h = fx['history']
        edited = h['saves'] >= 2 or (h.get('editor') and h.get('gap_days', 0) >= 1)
        if edited:
            why = []
            if h['saves'] >= 2:
                why.append(f"saved {h['saves']} times (an issued certificate is saved once)")
            if h.get('editor'):
                why.append(f"last saved with {h['producer']}, {h['gap_days']} days after it was created")
            c.flag('R-PDF-01', f'{name}: {h["summary"]}. It was ' + ' and '.join(why) + '.',
                   {**ev, 'history': h['summary'], 'saves': h['saves'], 'created_by': h.get('creator') or 'unknown',
                    'modified_with': h.get('producer') or 'unknown'})
        shows = {}
        for f in fx.get('fonts', []):
            shows[tuple(f['bbox'])] = f['text']
            c.flag('R-PDF-02', f"'{f['label']}' reads {f['text']} in {f['font']} {f['size']} pt; every other field uses {f['expected_font']} {f['expected_size']} pt.",
                   {**ev, 'field': f['label'], 'shows': f['text'], 'font_used': f"{f['font']} {f['size']} pt",
                    'font_expected': f"{f['expected_font']} {f['expected_size']} pt",
                    'preview': {'doc_id': d.id, 'page': f['page'], 'boxes': [f['bbox']]}})
        for w in fx.get('covers', []):
            vis = next((t for b, t in shows.items() if not (forensics.fitz.Rect(b) & forensics.fitz.Rect(w['bbox'])).is_empty), None)
            c.flag('R-PDF-03', f"A white box was drawn over text that is still inside the file. Hidden underneath: \"{w['hidden_text']}\"."
                   + (f' Visible on top: "{vis}".' if vis else ''),
                   {**ev, 'hidden_text': w['hidden_text'], 'shows': vis or '(blank)',
                    'preview': {'doc_id': d.id, 'page': w['page'], 'boxes': [w['bbox']]}})
    elif fx.get('type') == 'image':
        spots, cm = fx['ela']['spots'], fx['copy_move']
        if spots or cm:
            what = []
            if spots:
                what.append('1 area that re-compresses unlike the rest of the page' if len(spots) == 1 else
                            f'{len(spots)} areas that re-compress unlike the rest of the page')
            if cm:
                what.append(f'a patch copied to a second place ({cm[0]["matches"]} matching points)')
            boxes = [sp['bbox'] for sp in spots] + [b for m in cm for b in (m['source'], m['copy'])]
            c.flag('R-IMG-05', f'{name} scan: ' + '; '.join(what) + '. This says where to look, not proof on its own.',
                   {**ev, 'what': ' and '.join(what), 'hotspots': len(spots), 'copied_patches': len(cm),
                    'preview': {'doc_id': d.id, 'page': 0, 'boxes': boxes, 'heatmap': True}})


def check_live(c, docs):
    """Live capture results (see capture.py) become findings like everything else."""
    for shot in c.s.query(CaptureShot).filter_by(application_id=c.app.id).all():
        r = jload(shot.result, {})
        ev = {'shot': shot.shot, 'doc_id': shot.document_id, 'document': f'live photo ({shot.shot})', 'session': shot.session_id}
        if r.get('inside') is False:
            c.flag('R-CAP-01', f"Live photo '{shot.shot}' was taken {r['outside_m']} m outside the campus boundary "
                               f"(GPS accuracy ±{round(shot.accuracy or 0)} m).",
                   {**ev, 'outside_m': r['outside_m'], 'photo_gps': [shot.lat, shot.lng], 'accuracy_m': round(shot.accuracy or 0)})
        if r.get('code') == 'missing':
            c.flag('R-CAP-02', f"Live photo '{shot.shot}': the one-time code {r['expected_code']} could not be found in the picture.",
                   {**ev, 'code': r['expected_code']})
        if r.get('late_min', 0) > 0:
            c.flag('R-CAP-03', f"Live photo '{shot.shot}' was taken {r['late_min']} minutes after the session closed.",
                   {**ev, 'late_min': r['late_min']})
        if r.get('live') == 'flat':
            c.flag('R-CAP-04', f"Live photo '{shot.shot}': the two frames move as one flat plane ({r['inlier_pct']}% fit one plane), "
                               'which is what a photo of a screen or print looks like.', {**ev, 'plane_fit': f"{r['inlier_pct']}%"})


# ------------------------------------------------------------------ main entry
def process(s, app_id, actor='Pramaan check engine', cascade=True, practice=False):
    app = s.get(Application, app_id)
    rules = active_rules(s)
    read_documents(s, app)
    s.query(Finding).filter_by(application_id=app.id).delete()
    c = Ctx(s, app, rules, practice=practice)
    docs = s.query(Document).filter_by(application_id=app.id).all()
    check_required(c, docs)
    for d in docs:
        if d.kind == 'fire_noc':
            check_fire_noc(c, d)
        elif d.kind == 'land_doc':
            check_land(c, d)
        if d.kind in ('fire_noc', 'land_doc'):
            check_forensics(c, d)
    check_faculty(c, docs)
    check_photos(c, docs)
    check_live(c, docs)
    if practice:
        return c.findings
    dismissed = {x.key: x for x in s.query(FlagDismissal).filter_by(application_id=app.id).all()}
    for f in c.findings:
        x = dismissed.get(dismissal_key(f.rule_id, f.detail))
        if x and f.weight > 0:
            f.dismissed, f.dismiss_note = True, x.note
        s.add(f)
    risk = min(100, sum(f.weight for f in c.findings if not f.dismissed))
    lanes = rules['lanes']
    app.risk = risk
    app.lane = 'Inspect' if risk >= lanes['inspect'] else 'Review' if risk >= lanes['review'] else 'Fast track'
    app.rule_version = rules['version']
    app.status = 'processed' if not app.decision else app.status
    app.processed = datetime.now()
    audit.log(s, actor, 'Pre-screened application', app.id,
              {'risk': risk, 'lane': app.lane, 'findings': len(c.findings), 'rules': rules['version']})
    s.flush()
    if cascade:  # other colleges that share a teacher or a photo get re-checked too
        related = set()
        for fac in s.query(Faculty).filter_by(application_id=app.id).all():
            if fac.pan_hash:
                for o in s.query(Faculty).filter(Faculty.pan_hash == fac.pan_hash, Faculty.application_id != app.id).all():
                    related.add(o.application_id)
        for f in c.findings:
            ev = jload(f.evidence, {})
            if ev.get('other_application'):
                related.add(ev['other_application'])
        for rid in related:
            process(s, rid, actor, cascade=False)
    return app
