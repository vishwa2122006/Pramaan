"""Live geo-tagged photo capture with a one-time code.

When an application is submitted (or an officer starts a surprise session) Pramaan opens a capture
session: a list of required shots and a one-time code such as PRM-7K4Q, valid for 30 minutes.
College staff open the link on a phone. The page uses the camera directly (no gallery upload) and
the phone's location. Each shot carries two frames taken about two seconds apart.

For every shot we check:
  inside   GPS point inside the campus boundary from verified facts
  time     taken inside the session window
  code     the one-time code is visible in the picture (OCR)
  unique   the photo fingerprint matches no other college's photo (done by the main engine)
  live     the two frames show depth. A real room seen from two slightly different spots does not
           move as one flat plane; a screen or a printed photo does."""
import json
import math
import os
import re
import secrets
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

from . import extract
from .db import CaptureSession, CaptureShot, Document, Institution, VerifiedFact, jload

try:
    import cv2
except ImportError:
    cv2 = None

CODE_CHARS = 'ACDEFGHJKLMNPQRTUVWXY34679'   # no look-alikes (0/O, 1/I, 5/S, 8/B, 2/Z)


def new_code():
    return 'PRM-' + ''.join(secrets.choice(CODE_CHARS) for _ in range(4))


def new_session(s, app_id, minutes=30, shots=None, started_by='Pramaan', surprise=False, now=None):
    now = now or datetime.now()
    cs = CaptureSession(id=secrets.token_urlsafe(9), application_id=app_id, code=new_code(),
                        shots=json.dumps(shots or []), created=now, expires=now + timedelta(minutes=minutes),
                        started_by=started_by, surprise=surprise)
    s.add(cs)
    s.flush()
    return cs


# ---------------------------------------------------------------- campus boundary
def default_boundary(lat, lng, half_m=380):
    """Provisional square campus boundary when no surveyed boundary is on record."""
    dlat = half_m / 111320
    dlng = half_m / (111320 * math.cos(math.radians(lat)))
    return [[lat + dlat, lng - dlng], [lat + dlat, lng + dlng], [lat - dlat, lng + dlng], [lat - dlat, lng - dlng]]


def boundary(s, inst):
    f = s.query(VerifiedFact).filter_by(institution_id=inst.id, key='Campus boundary').first()
    if f:
        try:
            return json.loads(f.value), f.source
        except Exception:
            pass
    if inst.lat is None:
        return None, None
    return default_boundary(inst.lat, inst.lng), 'Provisional: 380 m around the declared campus point'


def _xy(lat, lng, lat0, lng0):
    return ((lng - lng0) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 111320)


def inside_polygon(lat, lng, poly):
    x, y = _xy(lat, lng, poly[0][0], poly[0][1])
    pts = [_xy(a, b, poly[0][0], poly[0][1]) for a, b in poly]
    inside = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def metres_outside(lat, lng, poly):
    if inside_polygon(lat, lng, poly):
        return 0
    x, y = _xy(lat, lng, poly[0][0], poly[0][1])
    pts = [_xy(a, b, poly[0][0], poly[0][1]) for a, b in poly]
    best = float('inf')
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = x2 - x1, y2 - y1
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return round(best)


# ---------------------------------------------------------------- checks on the picture
def find_code(path, code):
    """'found' | 'missing' | 'unchecked' (no OCR engine installed)."""
    if not extract._get_ocr():
        return 'unchecked', ''
    img = Image.open(path)
    text = extract.ocr_image(img)
    if not text:  # the card may be small: try the centre enlarged
        w, h = img.size
        text = extract.ocr_image(img.crop((w // 6, h // 6, 5 * w // 6, 5 * h // 6)).resize((w, h)))
    flat = re.sub(r'[^A-Z0-9]', '', text.upper())
    want = code.replace('-', '').upper()
    return ('found' if want[3:] in flat else 'missing'), text[:200]


def liveness(path1, path2):
    """Do the two frames move as one flat plane (screen, print) or show depth (real room)?
    Fits a single homography with a tight tolerance: a flat scene fits almost every point."""
    if cv2 is None or not path2 or not os.path.exists(path2):
        return {'live': 'unclear', 'why': 'second frame missing'}
    a = cv2.imread(path1, cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(path2, cv2.IMREAD_GRAYSCALE)
    if a is None or b is None:
        return {'live': 'unclear', 'why': 'frames unreadable'}
    sc = 960 / max(a.shape)
    a = cv2.resize(a, None, fx=sc, fy=sc)
    b = cv2.resize(b, (a.shape[1], a.shape[0]))
    orb = cv2.ORB_create(3000)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 40 or len(kb) < 40:
        return {'live': 'unclear', 'why': 'too little detail in the picture'}
    # keep only unambiguous matches (repeated windows or tiles would otherwise match the wrong copy)
    ms = [p[0] for p in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
          if len(p) == 2 and p[0].distance < 0.75 * p[1].distance and p[0].distance < 50]
    if len(ms) < 40:
        return {'live': 'unclear', 'why': 'frames too different to compare'}
    pa = np.float32([ka[m.queryIdx].pt for m in ms])
    pb = np.float32([kb[m.trainIdx].pt for m in ms])
    motion = float(np.median(np.linalg.norm(pa - pb, axis=1)))
    if motion < 4:
        return {'live': 'unclear', 'why': 'the phone did not move between frames', 'motion_px': round(motion, 1)}
    # Points consistent with ANY camera move (fundamental matrix) vs. with ONE flat plane (homography).
    # Wrong matches fail both, so the ratio only measures depth.
    F, fmask = cv2.findFundamentalMat(pa, pb, cv2.FM_RANSAC, 1.0, 0.999)
    H, hmask = cv2.findHomography(pa, pb, cv2.RANSAC, 2.5)
    if F is None or H is None or fmask is None or fmask.sum() < 25:
        return {'live': 'unclear', 'why': 'could not compare frames'}
    good = fmask.ravel().astype(bool)
    ratio = float(hmask.ravel().astype(bool)[good].mean())
    verdict = 'flat' if ratio > 0.95 else 'live'   # screens and prints fit one plane almost perfectly
    return {'live': verdict, 'inlier_pct': round(ratio * 100), 'motion_px': round(motion, 1), 'matches': len(ms)}


def evaluate(s, session, inst, path1, path2, lat, lng, accuracy, taken):
    poly, _src = boundary(s, inst)
    res = {'expected_code': session.code}
    if lat is None or poly is None:
        res['inside'] = None
    else:
        out = metres_outside(lat, lng, poly)
        res['outside_m'] = out
        # a reading that could lie inside the boundary given its own accuracy is not flagged
        res['inside'] = out <= min(accuracy or 0, 50)
    late = (taken - session.expires).total_seconds() / 60
    early = (session.created - taken).total_seconds() / 60
    res['late_min'] = max(0, math.ceil(late)) if late > 0 else 0
    res['in_window'] = late <= 0 and early <= 1
    res['code'], res['code_read'] = find_code(path1, session.code)
    res.update(liveness(path1, path2))
    res['accuracy_m'] = round(accuracy or 0)
    return res


def add_shot(s, session, app, shot_name, frame1: bytes, frame2: bytes, lat, lng, accuracy, folder, taken=None):
    taken = taken or datetime.now()
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '_', shot_name.lower()).strip('_') or 'shot'
    stamp = taken.strftime('%H%M%S')
    p1 = os.path.join(folder, f'live_photo__{slug}_{stamp}.jpg')
    p2 = os.path.join(folder, f'live_frame2__{slug}_{stamp}.jpg')
    with open(p1, 'wb') as f:
        f.write(frame1)
    if frame2:
        with open(p2, 'wb') as f:
            f.write(frame2)
    import hashlib
    d = Document(application_id=app.id, kind='live_photo', filename=f'{shot_name} (live).jpg', path=p1,
                 sha256=hashlib.sha256(frame1).hexdigest(),
                 meta=json.dumps({'live': True, 'session': session.id}))
    s.add(d)
    s.flush()
    inst = s.get(Institution, app.institution_id)
    res = evaluate(s, session, inst, p1, p2 if frame2 else '', lat, lng, accuracy, taken)
    shot = CaptureShot(session_id=session.id, application_id=app.id, document_id=d.id, shot=shot_name, lat=lat, lng=lng,
                       accuracy=accuracy, taken=taken, second_frame=p2 if frame2 else '', result=json.dumps(res))
    s.add(shot)
    s.flush()
    return shot, res
