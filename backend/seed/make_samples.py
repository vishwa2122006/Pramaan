"""Creates the SAMPLE documents used by the demo. Every document is watermarked
'SAMPLE - NOT A REAL DOCUMENT'; names, PANs, phone numbers and certificate numbers are invented.
The fire service and its signing keys are stand-ins for a real issuer."""
import base64
import zlib
import hashlib
import io
import json
import os
import random
from datetime import datetime

import numpy as np
import piexif
import qrcode
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

try:
    import pymupdf as fitz
except ImportError:
    import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DATA = os.path.join(BACKEND, 'data')
OUT = os.path.join(BACKEND, 'storage', 'samples')
UPLOAD_DEMO = os.path.join(os.path.dirname(BACKEND), 'sample_documents')

ISS = 'SFRS'
ISSUER_SYSTEM = 'SFRS e-NOC System 3.2'
ISS_NAME = 'State Fire and Rescue Services (sample issuer)'


def issuer_key():
    # demo key derived from a fixed phrase so the sample files are reproducible
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b'pramaan-demo-issuer-SFRS').digest())


def pub_b64():
    return base64.b64encode(issuer_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def signed_qr_payload(ref, to, issued, valid, signer):
    p = {'v': 1, 'iss': ISS, 'ref': ref, 'to': to, 'issued': issued, 'valid': valid, 'signer': signer}
    body = json.dumps(p, sort_keys=True, separators=(',', ':')).encode()
    p['sig'] = base64.b64encode(issuer_key().sign(body)).decode()
    return json.dumps(p, separators=(',', ':'))


OFFICERS = [
    {'name': 'P. Anand', 'post': 'Divisional Fire Officer, Madurai', 'from': '2022-01-01', 'to': '2030-12-31'},
    {'name': 'V. Kannan', 'post': 'Divisional Fire Officer, Nilgiris', 'from': '2023-04-01', 'to': '2030-12-31'},
    {'name': 'R. Selvi', 'post': 'Divisional Fire Officer, Tiruvannamalai', 'from': '2024-01-01', 'to': '2030-12-31'},
    {'name': 'M. Raja', 'post': 'Divisional Fire Officer, Vellore', 'from': '2020-06-01', 'to': '2030-12-31'},
    {'name': 'K. Ravi', 'post': 'Divisional Fire Officer, Cuddalore', 'from': '2021-06-01', 'to': '2026-05-31'},
    {'name': 'S. Meena', 'post': 'Divisional Fire Officer, Cuddalore', 'from': '2026-06-01', 'to': '2030-12-31'},
    {'name': 'A. Joseph', 'post': 'Divisional Fire Officer, Thanjavur', 'from': '2021-01-01', 'to': '2030-12-31'},
    {'name': 'D. Prakash', 'post': 'Divisional Fire Officer, Tiruchirappalli', 'from': '2022-07-01', 'to': '2030-12-31'},
    {'name': 'N. Latha', 'post': 'Divisional Fire Officer, Coimbatore', 'from': '2023-01-01', 'to': '2030-12-31'},
]

# ------------------------------------------------------------------ colleges and their stories
COLLEGES = [
    # code, name, district, lat, lng, intake, faculty_count, order
    dict(code='MAR', name='Marutham College of Engineering', district='Tiruchirappalli', lat=10.7905, lng=78.7047, intake=240, fac=14,
         noc=dict(ref='FRS/TRY/2026/0518', issued='2026-02-16', valid='2029-02-28', signer='D. Prakash'),
         survey='88/2A', fact='88/2A', extent='6.2'),
    dict(code='NOY', name='Noyyal Institute of Technology', district='Coimbatore', lat=11.0168, lng=76.9558, intake=180, fac=11,
         noc=dict(ref='FRS/CBE/2026/0675', issued='2026-04-07', valid='2029-04-30', signer='N. Latha'),
         survey='241/1', fact='241/1', extent='5.0', land_scan=True),
    dict(code='KOL', name='Kollidam Engineering College', district='Thanjavur', lat=10.7870, lng=79.1378, intake=240, fac=14,
         noc=dict(ref='FRS/TNJ/2025/1102', issued='2025-09-09', valid='2028-09-30', signer='A. Joseph'),
         survey='112/4B', fact='112/4A', extent='4.1'),
    dict(code='NIL', name='Nilgiri Ridge Institute of Management', district='Nilgiris', lat=11.4102, lng=76.6950, intake=120, fac=9,
         shared=['ilango', 'kalaivani'],
         noc=dict(ref='FRS/OTY/2026/0142', issued='2026-03-12', valid='2029-03-31', signer='V. Kannan'),
         survey='17/3', fact='17/3', extent='3.4', category='Extension of Approval', programme='PG Management'),
    dict(code='PAL', name='Palar Polytechnic College', district='Vellore', lat=12.9165, lng=79.1325, intake=180, fac=12,
         shared=['arulmozhi'], photo_far=True,
         noc=dict(ref='FRS/VLR/2026/0230', issued='2026-01-20', valid='2029-01-31', signer='M. Raja'),
         survey='305/7', fact='305/7', extent='3.0', programme='Diploma Engineering'),
    dict(code='JAV', name='Javadhu Hills Technical Campus', district='Tiruvannamalai', lat=12.2253, lng=79.0747, intake=240, fac=13,
         noc=dict(ref='FRS/TVM/2025/0811', issued='2025-07-03', valid='2027-06-30', signer='R. Selvi', printed_valid='2029-12-31'),
         survey='54/1', fact='54/1', extent='5.5', photo_noexif=True, category='Change in intake'),
    dict(code='THE', name='Thenpennai College of Pharmacy', district='Cuddalore', lat=11.7480, lng=79.7714, intake=100, fac=7,
         noc=dict(ref='FRS/CDL/2026/0377', issued='2026-08-15', valid='2028-08-31', signer='K. Ravi', no_qr=True),
         survey='76/5', fact='76/5', extent='2.6', programme='UG Pharmacy'),
    dict(code='VAI', name='Vaigai Institute of Technology', district='Madurai', lat=9.9252, lng=78.1198, intake=600, fac=31,
         shared=['ilango', 'kalaivani', 'arulmozhi'], photo_copy_of='MAR',
         noc=dict(ref='FRS/MDU/2024/3391', issued='2024-04-02', valid='2027-03-31', signer='P. Anand'),
         survey='402/1B', fact='402/1B', extent='12.0'),
]
UPLOAD_DEMO_COLLEGE = dict(code='KAV', name='Kaveri Institute of Engineering', district='Salem', lat=11.6643, lng=78.1460, intake=120, fac=7,
                           shared=['kalaivani'], photo_copy_of='NOY',
                           noc=dict(ref='FRS/SLM/2026/0904', issued='2026-10-04', valid='2029-10-31', signer='N. Latha'),
                           survey='19/2', extent='3.1')

# Second live demo: a NOC whose QR is damaged and whose expiry date was edited, plus a doctored scan
TAMPER_DEMO_COLLEGE = dict(code='AMA', name='Amaravathi College of Engineering', district='Karur', lat=10.9601, lng=78.0766,
                           intake=180, fac=10,
                           noc=dict(ref='FRS/KRR/2026/0213', issued='2026-03-12', valid='2026-06-30', forged_valid='2029-06-30',
                                    signer='D. Prakash', qr_damaged=True),
                           survey='63/2', forged_survey='63/2C', extent='4.4', land_scan=True)

SHARED_TEACHERS = {
    'ilango': ('Dr. R. Ilango', 'Professor', 'AKLPI4821Q', '+91 90000 11001'),
    'kalaivani': ('Dr. M. Kalaivani', 'Associate Professor', 'BQRPK7314M', '+91 90000 11002'),
    'arulmozhi': ('Prof. S. Arulmozhi', 'Assistant Professor', 'CMZPA2097L', '+91 90000 11003'),
}
FIRST = ['Arun', 'Bala', 'Charu', 'Deepa', 'Ezhil', 'Gowri', 'Hari', 'Indu', 'Jaya', 'Karthik', 'Lavanya', 'Mani', 'Nandhini',
         'Oviya', 'Pradeep', 'Ramya', 'Sathish', 'Thenmozhi', 'Uma', 'Vignesh', 'Yamini', 'Kavin', 'Malar', 'Senthil', 'Priya',
         'Gokul', 'Anitha', 'Raghu', 'Sudha', 'Vimal', 'Keerthana', 'Murali', 'Divya', 'Ashok']
INIT = 'ABCDGJKLMNPRSTV'
DESIG = ['Professor', 'Associate Professor', 'Assistant Professor', 'Assistant Professor', 'Assistant Professor']


def fake_pan(rng):
    L = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    return ''.join(rng.choice(L) for _ in range(3)) + 'P' + rng.choice(L) + f'{rng.randint(1000, 9999)}' + rng.choice(L)


def faculty_csv(col, rng):
    rows = ['name,designation,pan,phone']
    for key in col.get('shared', []):
        n, d, p, ph = SHARED_TEACHERS[key]
        rows.append(f'{n},{d},{p},{ph}')
    i = 0
    while len(rows) - 1 < col['fac']:
        n = f'{rng.choice(["Dr.", "Mr.", "Ms.", "Prof."])} {rng.choice(INIT)}. {rng.choice(FIRST)}'
        rows.append(f'{n},{rng.choice(DESIG)},{fake_pan(rng)},+91 9{rng.randint(100000000, 999999999)}')
        i += 1
    return '\n'.join(rows) + '\n'


# ------------------------------------------------------------------ PDFs
RED = (0.85, 0.3, 0.3)


def _watermark(page):
    r = page.rect
    for k, (y, txt) in enumerate(((480, 'SAMPLE - NOT A REAL DOCUMENT'), (760, 'FOR DEMONSTRATION ONLY'))):
        page.insert_text((70, y), txt, fontsize=34, color=(0.95, 0.75, 0.75),
                         morph=(fitz.Point(70, y), fitz.Matrix(1, 0, 0, 1, 0, 0).prerotate(-25)), overlay=False)


def _qr_png(text):
    img = qrcode.make(text, box_size=6, border=2)
    b = io.BytesIO()
    img.save(b, format='PNG')
    return b.getvalue()


def fire_noc_pdf(path, col):
    n = col['noc']
    d = lambda s: datetime.strptime(s, '%Y-%m-%d').strftime('%d-%m-%Y')
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    _watermark(page)
    page.insert_text((60, 70), 'State Fire and Rescue Services', fontsize=17, fontname='tibo')
    page.insert_text((60, 90), f'{col["district"]} Division  (sample issuer for demonstration)', fontsize=10, fontname='tiro')
    page.draw_line((60, 110), (535, 110), width=1.2)
    page.insert_text((175, 135), 'NO OBJECTION CERTIFICATE (FIRE SAFETY)', fontsize=12, fontname='hebo')
    page.draw_line((60, 148), (535, 148), width=1.2)
    rows = [('NOC No.', n['ref']), ('Issued to', col['name']), ('Building', 'Main academic block, G+3'),
            ('Date of issue', d(n['issued'])), ('Valid up to', d(n.get('printed_valid', n['valid'])))]
    y = 185
    for k, v in rows:
        page.insert_text((70, y), f'{k}:', fontsize=11.5, fontname='tiro')
        page.insert_text((200, y), v, fontsize=11.5, fontname='tibo')
        y += 26
    page.insert_textbox(fitz.Rect(70, y + 10, 525, y + 90),
                        'Certified that the above building has been inspected and the fire safety arrangements are found '
                        'satisfactory as per the National Building Code. This certificate is subject to annual renewal of '
                        'fire extinguishers.', fontsize=10.5, fontname='tiro')
    off = next(o for o in OFFICERS if o['name'] == n['signer'])
    page.insert_text((340, 690), f'Signed by: {n["signer"]}', fontsize=11, fontname='tibo')
    page.insert_text((340, 706), off['post'].split(',')[0], fontsize=10, fontname='tiro')
    page.draw_circle((140, 690), 38, color=(0.25, 0.35, 0.65), width=1.5)
    page.insert_text((112, 693), 'SEAL (SAMPLE)', fontsize=7.5, color=(0.25, 0.35, 0.65))
    if not n.get('no_qr'):
        q = signed_qr_payload(n['ref'], col['name'], n['issued'], n['valid'], n['signer'])
        page.insert_image(fitz.Rect(445, 25, 545, 125), stream=_qr_png(q))
        page.insert_text((443, 135), 'Scan to verify', fontsize=7.5)
        if n.get('qr_damaged'):  # coffee stain / tear over the QR: present but unreadable
            rng = random.Random('stain' + col['code'])
            for _ in range(60):
                cx, cy, r = rng.uniform(450, 540), rng.uniform(30, 120), rng.uniform(3, 11)
                page.draw_circle((cx, cy), r, color=None, fill=(0.62, 0.52, 0.38), fill_opacity=0.85)
    t = datetime.strptime(n['issued'], '%Y-%m-%d').strftime("D:%Y%m%d103000+05'30'")
    doc.set_metadata({'creator': ISSUER_SYSTEM, 'producer': ISSUER_SYSTEM, 'title': f'Fire NOC {n["ref"]}',
                      'creationDate': t, 'modDate': t})
    doc.save(path)


def land_pdf(path, col):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    _watermark(page)
    page.insert_text((60, 70), 'Sale / Lease Deed (extract)', fontsize=17, fontname='tibo')
    page.insert_text((60, 90), f'Sub-Registrar Office, {col["district"]} (sample)', fontsize=10, fontname='tiro')
    page.draw_line((60, 110), (535, 110), width=1.2)
    trust = col['name'].split(' ')[0] + ' Educational Trust'
    rows = [('Document No.', f'DOC-2015-{zlib.crc32(col["code"].encode()) % 9000 + 1000}'),
            ('Owner / Trust', trust), ('Village', f'{col["district"]} Taluk'), ('Survey No.', col['survey']),
            ('Extent', f'{col["extent"]} acres')]
    y = 150
    for k, v in rows:
        page.insert_text((70, y), f'{k}:', fontsize=11.5, fontname='tiro')
        page.insert_text((200, y), v, fontsize=11.5, fontname='tibo')
        y += 26
    page.insert_textbox(fitz.Rect(70, y + 10, 525, y + 80),
                        'The property described above is held by the Trust for the purpose of running a technical institution, '
                        'free from encumbrances as on the date of this extract.', fontsize=10.5, fontname='tiro')
    page.insert_text((380, 700), 'Sub-Registrar', fontsize=11, fontname='tibo')
    page.draw_circle((150, 690), 40, color=(0.55, 0.2, 0.45), width=2)
    page.draw_circle((150, 690), 33, color=(0.55, 0.2, 0.45), width=0.8)
    page.insert_text((121, 686), 'SUB-REGISTRAR', fontsize=7, color=(0.55, 0.2, 0.45))
    page.insert_text((128, 698), f'{col["district"][:10].upper()}', fontsize=7.5, color=(0.55, 0.2, 0.45))
    t = "D:20150612110000+05'30'"
    doc.set_metadata({'creator': 'TNREGINET deed extract', 'producer': 'TNREGINET deed extract', 'creationDate': t, 'modDate': t})
    doc.save(path)
    return trust


def pdf_to_scan_jpg(pdf_path, jpg_path, seed):
    """Make a 'scanned' JPG: render, tilt slightly, add grain. Needs OCR to read."""
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    img = img.rotate(0.6, expand=True, fillcolor=(250, 248, 240))
    rng = random.Random(seed)
    px = img.load()
    for _ in range(9000):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        v = rng.randint(200, 240)
        px[x, y] = (v, v, v - 8)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    img.save(jpg_path, quality=85)


def tamper_noc_pdf(path, col):
    """A forger's edit: white box over the expiry date, new date typed on top in another font,
    saved incrementally by an online PDF editor months after the issuer created it."""
    n = col['noc']
    doc = fitz.open(path)
    page = doc[0]
    old = datetime.strptime(n['valid'], '%Y-%m-%d').strftime('%d-%m-%Y')
    new = datetime.strptime(n['forged_valid'], '%Y-%m-%d').strftime('%d-%m-%Y')
    hit = page.search_for(old)[0]
    page.draw_rect(fitz.Rect(hit.x0 - 1, hit.y0 - 1, hit.x1 + 2, hit.y1 + 1), color=None, fill=(1, 1, 1))
    page.insert_text((hit.x0, hit.y1 - 2.6), new, fontsize=12.2, fontname='helv')
    doc.set_metadata({**doc.metadata, 'producer': 'iLovePDF', 'modDate': "D:20261020184500+05'30'"})
    doc.saveIncr()


def tamper_scan(jpg_path, col):
    """Change the survey number on a scanned deed by pasting a freshly typed patch, and copy the
    registrar's seal to a second place. Both leave traces the checks can find."""
    img = Image.open(jpg_path).convert('RGB')
    # the scan was rendered at 2x from a 595x842 page and rotated 0.6 degrees; find the survey value
    tmp = fitz.open()
    pg = tmp.new_page(width=595, height=842)
    pg.insert_text((200, 228), col['forged_survey'], fontsize=11.5, fontname='tibo')
    pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(196, 212, 290, 234))
    patch = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    # scan colour and slight blur so it looks right to the eye
    arr = np.asarray(patch).astype(np.float32)
    ink = 1 - arr.mean(axis=2, keepdims=True) / 255.0          # 0 on paper, 1 on ink
    paper = np.array([250, 248, 240], dtype=np.float32)
    arr = paper * (1 - ink) + np.array([20, 20, 22]) * ink      # same paper tint as the scan
    patch = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))
    img.paste(patch, (401, 427))
    # copy the seal (left, near the bottom) onto the right, keeping only its ink
    seal = img.crop((205, 1285, 400, 1480))
    sa = np.asarray(seal).astype(np.int16)
    mask = Image.fromarray(((sa[:, :, 0] - sa[:, :, 1] > 25) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
    img.paste(seal, (720, 1260), mask)
    img.save(jpg_path, quality=85)


# ------------------------------------------------------------------ lab photos (drawn, not real)
def lab_photo(seed):
    rng = random.Random(seed)
    W, H = 1200, 800
    wall = tuple(rng.randint(150, 220) for _ in range(3))
    floor = tuple(rng.randint(90, 150) for _ in range(3))
    img = Image.new('RGB', (W, H), wall)
    d = ImageDraw.Draw(img)
    hz = rng.randint(380, 470)
    d.rectangle([0, hz, W, H], fill=floor)
    for i in range(rng.randint(2, 5)):  # windows
        x = rng.randint(40, W - 220); w = rng.randint(110, 190); y = rng.randint(60, 120)
        d.rectangle([x, y, x + w, y + rng.randint(140, 220)], fill=(170, 200, 235), outline=(70, 70, 80), width=6)
        d.line([x + w // 2, y, x + w // 2, y + 200], fill=(70, 70, 80), width=4)
    bx = rng.randint(250, 650)
    d.rectangle([bx, 90, bx + rng.randint(260, 380), 280], fill=(35, 70, 45), outline=(90, 60, 40), width=8)
    for j in range(rng.randint(3, 6)):  # ceiling lights
        lx = rng.randint(50, W - 150)
        d.rectangle([lx, 15, lx + 120, 30], fill=(250, 250, 235))
    rows = rng.randint(3, 4)
    for r in range(rows):
        y = hz + 40 + r * (H - hz - 40) // rows
        sc = 0.7 + r * 0.25
        n = rng.randint(4, 7)
        for k in range(n):
            x = int(40 + k * (W - 80) / n + rng.randint(-10, 10))
            dw = int(120 * sc)
            d.rectangle([x, y, x + dw, y + int(18 * sc)], fill=(120, 80, 50))
            d.rectangle([x + dw // 4, y - int(55 * sc), x + 3 * dw // 4, y - int(8 * sc)], fill=(30, 30, 35), outline=(10, 10, 10))
            d.rectangle([x + dw // 4 + 4, y - int(51 * sc), x + 3 * dw // 4 - 4, y - int(12 * sc)],
                        fill=tuple(rng.randint(60, 140) for _ in range(3)))
    px = img.load()
    for _ in range(25000):
        x, y = rng.randrange(W), rng.randrange(H)
        c = px[x, y]
        dv = rng.randint(-14, 14)
        px[x, y] = tuple(max(0, min(255, v + dv)) for v in c)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _dms(v):
    v = abs(v); d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60 * 100)
    return ((d, 1), (m, 1), (s, 100))


def save_jpg(img, path, lat=None, lng=None, taken=None, software=None, model='Redmi Note 12', exif=True):
    if not exif:
        img.save(path, quality=88)
        return
    z = {piexif.ImageIFD.Make: b'Xiaomi', piexif.ImageIFD.Model: model.encode()}
    if software:
        z[piexif.ImageIFD.Software] = software.encode()
    e = {piexif.ExifIFD.DateTimeOriginal: taken.encode()} if taken else {}
    g = {}
    if lat is not None:
        g = {piexif.GPSIFD.GPSLatitudeRef: b'N' if lat >= 0 else b'S', piexif.GPSIFD.GPSLatitude: _dms(lat),
             piexif.GPSIFD.GPSLongitudeRef: b'E' if lng >= 0 else b'W', piexif.GPSIFD.GPSLongitude: _dms(lng)}
    img.save(path, quality=88, exif=piexif.dump({'0th': z, 'Exif': e, 'GPS': g}))


def make_photos(col, folder, originals):
    """Returns list of photo paths; `originals` maps college code -> (img, lat, lng) for copy cases."""
    rng = random.Random('photo' + col['code'])
    paths = []
    if col.get('photo_copy_of'):
        src_img, slat, slng = originals[col['photo_copy_of']]
        w, h = src_img.size
        c = src_img.crop((int(w * .03), int(h * .03), int(w * .97), int(h * .97)))
        c = ImageEnhance.Brightness(c).enhance(1.12)
        p = os.path.join(folder, 'computer_lab_1.jpg')
        save_jpg(c, p, slat + 0.0002, slng + 0.0003, '2025:11:20 11:05:12', software='Adobe Photoshop 25.1')
        paths.append(p)
        img2 = lab_photo('second' + col['code'])
        p2 = os.path.join(folder, 'workshop_1.jpg')
        save_jpg(img2, p2, col['lat'] + 0.0004, col['lng'] - 0.0002, '2026:09:30 10:12:40')
        paths.append(p2)
        return paths
    img = lab_photo('lab' + col['code'])
    lat, lng = col['lat'] + 0.0005, col['lng'] + 0.0004
    if col.get('photo_far'):
        lat, lng = col['lat'] + 0.045, col['lng'] + 0.02  # about 5 km away
    p = os.path.join(folder, 'computer_lab_1.jpg')
    save_jpg(img, p, lat, lng, '2026:09:18 10:40:00', exif=not col.get('photo_noexif'))
    paths.append(p)
    originals[col['code']] = (img, lat, lng)
    return paths


def write_registry():
    certs = {}
    for col in COLLEGES + [UPLOAD_DEMO_COLLEGE, TAMPER_DEMO_COLLEGE]:
        n = col['noc']
        if n.get('no_qr'):
            continue  # this certificate number was never issued
        certs[n['ref']] = {'status': 'valid', 'issued_to': col['name'], 'issued': n['issued'], 'valid': n['valid'], 'signer': n['signer']}
    reg = {'_note': 'Stand-in for issuer portals (DigiLocker, state fire service). Demo data only.',
           'prefixes': {'FRS': ISS},
           'issuers': {ISS: {'name': ISS_NAME, 'public_key': pub_b64(), 'officers': OFFICERS}},
           'certificates': {ISS: certs}}
    with open(os.path.join(DATA, 'issuer_registry.json'), 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2)


def make_package(col, folder, originals):
    os.makedirs(folder, exist_ok=True)
    rng = random.Random('fac' + col['code'])
    files = []
    p = os.path.join(folder, 'fire_noc.pdf'); fire_noc_pdf(p, col)
    if col['noc'].get('forged_valid'):
        tamper_noc_pdf(p, col)
    files.append(('fire_noc', p))
    p = os.path.join(folder, 'land_document.pdf'); land_pdf(p, col)
    if col.get('land_scan'):
        j = os.path.join(folder, 'land_document_scan.jpg'); pdf_to_scan_jpg(p, j, col['code']); os.remove(p); p = j
        if col.get('forged_survey'):
            tamper_scan(j, col)
    files.append(('land_doc', p))
    p = os.path.join(folder, 'faculty_list.csv')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(faculty_csv(col, rng))
    files.append(('faculty_list', p))
    for ph in make_photos(col, folder, originals):
        files.append(('lab_photo', ph))
    return files


def make_all():
    os.makedirs(OUT, exist_ok=True)
    write_registry()
    originals, packages = {}, {}
    for col in COLLEGES:
        packages[col['code']] = make_package(col, os.path.join(OUT, col['code']), originals)
    demo = os.path.join(UPLOAD_DEMO, 'Kaveri_Institute_upload_demo')
    make_package(UPLOAD_DEMO_COLLEGE, demo, originals)
    tdemo = os.path.join(UPLOAD_DEMO, 'Amaravathi_tampered_upload_demo')
    make_package(TAMPER_DEMO_COLLEGE, tdemo, originals)
    t = TAMPER_DEMO_COLLEGE
    with open(os.path.join(tdemo, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('Use these files on the "Submit an application" screen to show edit detection.\n'
                f'College code: {t["code"]}\nName: {t["name"]}\nDistrict: {t["district"]}\n'
                f'Campus latitude: {t["lat"]}\nCampus longitude: {t["lng"]}\nIntake: {t["intake"]}\n\n'
                'What is hidden: the Fire NOC QR is stained and unreadable. Its expiry date was changed from 30-06-2026 to\n'
                '30-06-2029 with iLovePDF: a white box covers the old date and the new one is typed in another font.\n'
                'The scanned land deed has a pasted survey number (63/2 -> 63/2C) and a copied registrar seal.\n\n'
                'All files are SAMPLES with invented data.\n')
    with open(os.path.join(demo, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('Use these files on the "College: submit" screen to see Pramaan check a new application live.\n'
                f'College code: {UPLOAD_DEMO_COLLEGE["code"]}\nName: {UPLOAD_DEMO_COLLEGE["name"]}\nDistrict: {UPLOAD_DEMO_COLLEGE["district"]}\n'
                f'Campus latitude: {UPLOAD_DEMO_COLLEGE["lat"]}\nCampus longitude: {UPLOAD_DEMO_COLLEGE["lng"]}\n'
                f'Intake: {UPLOAD_DEMO_COLLEGE["intake"]}\n\nAll files are SAMPLES with invented data.\n')
    return packages


if __name__ == '__main__':
    make_all()
    print('samples written to', OUT)
