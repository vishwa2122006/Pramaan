"""Builds the demo database: 8 sample colleges run through the real check engine, then teacher SMS
replies, officer decisions, earlier approval cycles and two live capture sessions, so every screen
has something to show."""
import io
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app import audit, capture, pipeline  # noqa: E402
from app.db import (Application, FlagDismissal, Finding, PastCycle, SessionLocal, SmsMessage, VerifiedFact,  # noqa: E402
                    reset_db)
from app.main import UPLOADS, create_application  # noqa: E402
from seed.make_samples import COLLEGES, lab_photo, make_all  # noqa: E402

try:
    import pymupdf as fitz
except ImportError:
    import fitz

try:
    import cv2
except ImportError:
    cv2 = None


def campus_polygon(lat, lng, seed):
    """An irregular surveyed boundary, roughly 600 m x 500 m around the campus point."""
    rng = random.Random(seed)
    pts = []
    for k in range(7):
        ang = 2 * math.pi * k / 7 + rng.uniform(-0.2, 0.2)
        r = rng.uniform(260, 360)
        dlat = r * math.sin(ang) / 111320
        dlng = r * math.cos(ang) / (111320 * math.cos(math.radians(lat)))
        pts.append([round(lat + dlat, 6), round(lng + dlng * 1.15, 6)])
    return pts


# ------------------------------------------------------------------ live capture samples
def _card(code):
    """A white card with the one-time code, as staff would hold it up."""
    doc = fitz.open()
    pg = doc.new_page(width=200, height=80)
    pg.draw_rect(pg.rect, color=(0.2, 0.2, 0.2), fill=(1, 1, 1), width=2)
    pg.insert_text((14, 52), code, fontsize=30, fontname='hebo')
    pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
    return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')


def _scene(kind, seed):
    """Different drawn scenes per shot, so sample photos of different places do not look alike."""
    from PIL import ImageDraw, ImageFilter
    rng = random.Random(seed)
    k = kind.lower()
    if 'lab' in k:
        return lab_photo(seed)
    W, H = 1200, 800
    if 'library' in k:
        img = Image.new('RGB', (W, H), tuple(rng.randint(200, 235) for _ in range(3)))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 560, W, H], fill=tuple(rng.randint(110, 150) for _ in range(3)))
        x = rng.randint(10, 60)
        while x < W - 160:
            w = rng.randint(180, 280)
            d.rectangle([x, 60, x + w, 560], fill=(110, 74, 48))
            for y in range(80, 540, 92):
                bx = x + 8
                while bx < x + w - 14:
                    bw = rng.randint(8, 18)
                    d.rectangle([bx, y + rng.randint(0, 18), bx + bw, y + 80], fill=tuple(rng.randint(30, 210) for _ in range(3)))
                    bx += bw + rng.randint(1, 3)
                d.rectangle([x, y + 80, x + w, y + 88], fill=(80, 52, 34))
            x += w + rng.randint(30, 90)
    elif 'fire' in k:
        img = Image.new('RGB', (W, H), tuple(rng.randint(185, 225) for _ in range(3)))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 600, W, H], fill=(120, 120, 115))
        for i in range(rng.randint(2, 4)):
            x = rng.randint(80, W - 200)
            d.rectangle([x, 330, x + 70, 600], fill=(200, 25, 25))
            d.rectangle([x + 20, 300, x + 50, 330], fill=(40, 40, 40))
            d.line([x + 50, 315, x + 110, 300], fill=(30, 30, 30), width=6)
            d.rectangle([x - 20, 160, x + 100, 240], fill=(250, 250, 250), outline=(200, 25, 25), width=5)
        d.rectangle([rng.randint(600, 900), 80, 1150, 520], fill=(160, 120, 80), outline=(70, 50, 30), width=8)
    else:  # building front
        img = Image.new('RGB', (W, H), (150 + rng.randint(-20, 20), 190, 230))
        d = ImageDraw.Draw(img)
        bx0, bx1 = rng.randint(60, 200), rng.randint(1000, 1140)
        d.rectangle([bx0, 160, bx1, 680], fill=tuple(rng.randint(170, 230) for _ in range(3)))
        for fy in range(200, 640, 110):
            for fx in range(bx0 + 30, bx1 - 80, rng.choice([90, 110, 130])):
                d.rectangle([fx, fy, fx + 60, fy + 70], fill=(80, 110, 140), outline=(60, 60, 60), width=3)
        d.rectangle([0, 680, W, H], fill=(95, 140, 70))
        d.rectangle([(bx0 + bx1) // 2 - 70, 520, (bx0 + bx1) // 2 + 70, 680], fill=(90, 60, 40))
        for _ in range(rng.randint(3, 5)):  # trees in front of the building
            tx = rng.randint(40, W - 120)
            d.rectangle([tx + 34, 600, tx + 50, 790], fill=(90, 62, 40))
            for _ in range(7):
                cx, cy, r = tx + rng.randint(0, 84), rng.randint(560, 650), rng.randint(26, 46)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(40 + rng.randint(0, 40), 110 + rng.randint(0, 50), 40))

    px = img.load()
    for _ in range(20000):
        x, y = rng.randrange(W), rng.randrange(H)
        c = px[x, y]
        dv = rng.randint(-12, 12)
        px[x, y] = tuple(max(0, min(255, v + dv)) for v in c)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _frames(seed, code, flat=False, show_code=True, kind='Computer lab'):
    img = _scene(kind, seed)
    card = _card(code) if show_code else None
    pos = (img.width // 2 - 160, int(img.height * 0.52))
    if flat and card:   # a photo of a screen: the card is part of the flat picture too
        img.paste(card, pos)
    a = np.array(img)[:, :, ::-1].copy()
    h, w = a.shape[:2]
    if flat:  # the whole picture moves as one plane
        H = np.array([[1.01, 0.01, 14], [-0.008, 1.0, 6], [1e-5, 0, 1]])
        b = cv2.warpPerspective(a, H, (w, h), borderMode=cv2.BORDER_REPLICATE)
    else:     # a real room after a small step sideways: far, middle and near things shift by different amounts
        layers = [(np.float32([[1, 0, 5], [0, 1, 1]]), 0.0), (np.float32([[1.01, 0, 16], [0, 1.01, 1]]), 0.36),
                  (np.float32([[1.025, 0, 30], [0, 1.025, 0]]), 0.68)]
        b = a.copy()
        for m, start in layers:
            moved = cv2.warpAffine(a, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
            y0 = int(h * start)
            b[y0:] = moved[y0:]
        if card:  # the card is held close to the camera, so it shifts the most
            c = np.array(card)[:, :, ::-1]
            a[pos[1]:pos[1] + c.shape[0], pos[0]:pos[0] + c.shape[1]] = c
            q = (pos[0] + 46, pos[1] + 3)
            b[q[1]:q[1] + c.shape[0], q[0]:q[0] + c.shape[1]] = c
    enc = lambda x: cv2.imencode('.jpg', x, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()
    return enc(a), enc(b)


def seed_capture(s, app, rules, plan):
    cs = capture.new_session(s, app.id, rules.get('capture_minutes', 30), rules.get('capture_shots'),
                             started_by='Pramaan (on submission)', now=app.created + timedelta(hours=2))
    audit.log(s, 'Pramaan', 'Live capture session opened', app.id, {'code': cs.code, 'minutes': 30})
    inst = app.institution
    for k, (shot, d_north, d_east, flat) in enumerate(plan):
        f1, f2 = _frames(f'live-{inst.code}-{k}', cs.code, flat=flat, kind=shot)
        lat = inst.lat + d_north / 111320
        lng = inst.lng + d_east / (111320 * math.cos(math.radians(inst.lat)))
        sh, res = capture.add_shot(s, cs, app, shot, f1, f2, lat, lng, 12.0, os.path.join(UPLOADS, app.id),
                                   taken=cs.created + timedelta(minutes=4 + 5 * k))
        audit.log(s, f'{inst.name} (live capture)', 'Live photo received', app.id,
                  {'shot': shot, 'inside': res.get('inside'), 'code': res.get('code'), 'live': res.get('live')})


# ------------------------------------------------------------------ earlier cycles
PAST = {
    'VAI': [('2025-26', 'Inspect', ['R-IMG-02'], 'inspect', 'confirmed'), ('2026-27', 'Review', ['R-XINST-01'], 'query', '')],
    'THE': [('2026-27', 'Review', ['R-LOGIC-01'], 'query', '')],
    'KOL': [('2026-27', 'Review', ['R-NORM-01'], 'query', '')],
    'JAV': [('2025-26', 'Inspect', ['R-SRC-04', 'R-IMG-03'], 'inspect', 'no_problem')],
    'NIL': [('2025-26', 'Inspect', ['R-NORM-01', 'R-XINST-01'], 'inspect', 'confirmed')],
}


def seed(quiet=False):
    packages = make_all()
    reset_db()
    s = SessionLocal()
    rules = pipeline.active_rules(s)
    now = datetime.now().replace(second=0, microsecond=0)
    ids = {}
    for i, col in enumerate(COLLEGES):
        files = []
        for kind, path in packages[col['code']]:
            with open(path, 'rb') as f:
                files.append((kind, os.path.basename(path), f.read()))
        created = now - timedelta(days=24 - 2.6 * i, hours=3 * i)
        a = create_application(s, code=col['code'], name=col['name'], district=col['district'], lat=col['lat'], lng=col['lng'],
                               category=col.get('category', 'Extension of Approval'), programme=col.get('programme', 'UG Engineering'),
                               intake=col['intake'], academic_year=rules['academic_year'], files=files, created=created)
        s.add(VerifiedFact(institution_id=a.institution_id, key='Land survey number', value=col['fact'],
                           source='Sub-Registrar record, verified in 2025-26 cycle', verified_on='2025-05-14'))
        s.add(VerifiedFact(institution_id=a.institution_id, key='Campus location', value=f'{col["lat"]}, {col["lng"]}',
                           source='Officer site visit, 2025-26 cycle', verified_on='2025-05-14'))
        s.add(VerifiedFact(institution_id=a.institution_id, key='Campus boundary',
                           value=json.dumps(campus_polygon(col['lat'], col['lng'], col['code'])),
                           source='Surveyed boundary from the 2025-26 site visit', verified_on='2025-05-14'))
        ids[col['code']] = a.id
        for yr, lane, flags, dec, outcome in PAST.get(col['code'], []):
            s.add(PastCycle(institution_code=col['code'], academic_year=yr, lane=lane, flags=json.dumps(flags),
                            decision=dec, inspection_outcome=outcome))
        for yr in ('2025-26', '2026-27'):
            if not any(p[0] == yr for p in PAST.get(col['code'], [])):
                s.add(PastCycle(institution_code=col['code'], academic_year=yr, lane='Fast track', flags='[]', decision='approve'))
    s.flush()
    for code in ids:  # two passes so every college is compared with every other
        pipeline.process(s, ids[code], cascade=False)
    for code in ids:
        pipeline.process(s, ids[code], cascade=False)
    # teacher replies (simulated phones)
    replies = [('Dr. R. Ilango', 'VAI', 'no'), ('Dr. R. Ilango', 'NIL', 'yes'), ('Prof. S. Arulmozhi', 'PAL', 'yes')]
    for name, code, ans in replies:
        m = s.query(SmsMessage).filter_by(faculty_name=name, application_id=ids[code]).first()
        if m:
            m.status, m.replied, m.channel = ans, datetime.now(), 'sms'
            audit.log(s, f'Teacher {name}', f'SMS reply: {ans.upper()}', ids[code], {'institution': m.institution_name})
            pipeline.process(s, ids[code], actor='Pramaan (after SMS reply)', cascade=False)
    # live capture: a clean session at Marutham, a problem session at Kollidam
    shots = rules['capture_shots']
    if cv2 is not None:
        seed_capture(s, s.get(Application, ids['MAR']), rules,
                     [(shots[0], 60, -40, False), (shots[1], -90, 70, False), (shots[2], 20, 110, False), (shots[3], -150, -60, False)])
        seed_capture(s, s.get(Application, ids['PAL']), rules,
                     [(shots[0], 40, 30, True), (shots[1], 980, 120, False)])
        for code in ('MAR', 'PAL'):
            pipeline.process(s, ids[code], actor='Pramaan (live capture)', cascade=False)
    # an officer overrules one flag
    jav = s.get(Application, ids['JAV'])
    f = s.query(Finding).filter_by(application_id=jav.id, rule_id='R-IMG-03').first()
    if f:
        s.add(FlagDismissal(application_id=jav.id, rule_id=f.rule_id, key=pipeline.dismissal_key(f.rule_id, f.detail),
                            note='Photo is from the college DSLR; the original file with camera details was checked.', officer=jav.officer))
        audit.log(s, jav.officer, 'Flag dismissed', jav.id, {'rule': f.rule_id})
        pipeline.process(s, jav.id, actor='Re-scored after officer review', cascade=False)
    # decisions already taken on three files
    for code, dec, note, after, outcome in [
            ('MAR', 'approve', 'All checks clear; live capture complete.', 3.5, ''),
            ('KOL', 'query', 'Asked for the registered deed for survey no. 112/4B.', 6, ''),
            ('THE', 'inspect', 'NOC not on record with the fire department.', 2, 'confirmed')]:
        a = s.get(Application, ids[code])
        a.decision, a.decision_note, a.status = dec, note, 'decided'
        a.decided_by, a.decided_at = a.officer, a.created + timedelta(days=after)
        a.inspection_outcome = outcome
        audit.log(s, a.officer, f'Officer decision: {dec.upper()}', a.id, {'note': note, 'risk': a.risk})
        if outcome:
            audit.log(s, 'Inspection team', 'Inspection result recorded', a.id, {'outcome': 'problem confirmed'})
    s.commit()
    if not quiet:
        for a in sorted(s.query(Application).all(), key=lambda a: -a.risk):
            print(f'{a.id}  {a.institution.name:40s} risk {a.risk:3d}  {a.lane:10s} {a.officer}')
    s.close()


if __name__ == '__main__':
    seed()
