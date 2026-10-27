"""Plain-language summary and one-click scrutiny reports.

The summary is built from fixed sentence templates in the rulebook, so the same findings always give
the same sentences. Reports are PDFs whose content is signed with Pramaan's Ed25519 key; the QR code on
each report opens a page that checks the signature and, if a file is uploaded, its SHA-256.

Two versions of the application report:
  internal  full detail for AICTE
  college   a query letter: what to fix, without other colleges' names or teachers' PANs"""
import base64
import hashlib
import html
import io
import json
import os
import secrets
from datetime import datetime

import qrcode
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from PIL import Image

from . import pipeline
from .db import STORE_DIR

try:
    import pymupdf as fitz
except ImportError:
    import fitz

KEY_DIR = os.path.join(STORE_DIR, 'keys')
REPORT_DIR = os.path.join(STORE_DIR, 'reports')
LANE_ACTION = {'Inspect': 'order an inspection', 'Review': 'send a query to the college', 'Fast track': 'approve'}


# ---------------------------------------------------------------- signing key
def _key():
    os.makedirs(KEY_DIR, exist_ok=True)
    p = os.path.join(KEY_DIR, 'pramaan_report_signing.key')
    if not os.path.exists(p):
        with open(p, 'wb') as f:
            f.write(secrets.token_bytes(32))
    with open(p, 'rb') as f:
        return Ed25519PrivateKey.from_private_bytes(f.read())


def public_key_b64():
    return base64.b64encode(_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sign(payload):
    return base64.b64encode(_key().sign(canonical(payload))).decode()


def check_signature(payload, sig):
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64()))
        pub.verify(base64.b64decode(sig), canonical(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------------------------------------------------------------- plain-language summary
def _cap(t):
    return t[:1].upper() + t[1:] if t else t


def summary(rules, findings, lane, college=False):
    """findings: dicts with rule, severity, weight, evidence, dismissed."""
    live = [f for f in findings if f['weight'] > 0 and not f.get('dismissed')]
    serious = [f for f in live if f['severity'] == 'high']
    other = [f for f in live if f['severity'] != 'high']
    kind = 'college' if college else 'plain'
    seen, items = set(), []
    for f in serious + other:
        t = pipeline.sentence(rules, f['rule'], f['evidence'], kind)
        if t not in seen:
            seen.add(t)
            items.append({'text': t, 'serious': f['severity'] == 'high', 'rule': f['rule']})
    n = len({i['text'] for i in items if i['serious']})
    m = len(items) - n
    if n:
        head = f'{n} serious problem{"s" if n > 1 else ""} found.' + (f' {m} more point{"s" if m > 1 else ""} to check.' if m else '')
    elif m:
        head = f'No serious problems. {m} point{"s" if m > 1 else ""} to check.'
    else:
        head = 'No problems found.'
    steps = [] if college else [LANE_ACTION.get(lane, 'review the file')]
    fixes = []
    for f in serious + other:
        r = rules['rules'].get(f['rule'], {})
        ev = {k: pipeline._human(v) for k, v in {**f['evidence'], 'academic_year_start': rules.get('academic_year_start')}.items()}
        if not college and r.get('next_step'):
            st = r['next_step'].format_map(pipeline._Blank(ev))
            if st and st not in steps:
                steps.append(st)
        if r.get('fix'):
            fx = r['fix'].format_map(pipeline._Blank(ev))
            if fx not in fixes:
                fixes.append(fx)
    text = head + (' ' + ' '.join(f'({k + 1}) {i["text"]}' for k, i in enumerate(items)) if items else '')
    nxt = ('Suggested next step: ' + '; '.join(steps[:4]) + '.') if steps else ''
    return {'headline': head, 'items': items, 'text': text, 'next_step': _cap(nxt), 'fixes': fixes}


# ---------------------------------------------------------------- PDF building
CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #1b1d35; line-height: 1.35; }
h1 { font-size: 17pt; color: #171b4d; margin: 0 0 2pt 0; }
h2 { font-size: 12pt; color: #171b4d; margin: 14pt 0 5pt 0; }
p { margin: 0 0 5pt 0; }
.meta { color: #646985; font-size: 9pt; }
.box { background-color: #eceefa; padding: 8pt; }
.red { color: #be3a2b; font-weight: bold; }
.amber { color: #b06f07; font-weight: bold; }
.green { color: #1d7a4c; font-weight: bold; }
table { border-collapse: collapse; width: 100%; }
td, th { border-bottom: 0.5pt solid #dcdfea; padding: 3pt 4pt; vertical-align: top; text-align: left; font-size: 9pt; }
th { color: #646985; font-weight: normal; }
.mono { font-family: monospace; font-size: 7.5pt; }
.small { font-size: 8.5pt; color: #646985; }
"""


def _esc(t):
    return html.escape(str(t if t is not None else ''))


def _img(images, name, data, width_pt, max_px=900):
    """Add an image to the archive and return an <img> tag with both sizes set (the layout engine needs both)."""
    jpg = _png(data, max_px)
    im = Image.open(io.BytesIO(jpg))
    images[name] = jpg
    return f'<img src="{name}" width="{width_pt}" height="{round(width_pt * im.height / im.width)}"/>'


def _png(data, max_w=900):
    im = Image.open(io.BytesIO(data)) if isinstance(data, bytes) else Image.open(data)
    im = im.convert('RGB')
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=82)
    return b.getvalue()


def _qr(url):
    img = qrcode.make(url, box_size=5, border=1)
    b = io.BytesIO()
    img.save(b, 'PNG')
    return b.getvalue()


def render(body_html, images, footer):
    """Lay out HTML across A4 pages with PyMuPDF's Story engine."""
    arch = fitz.Archive()
    for name, data in images.items():
        arch.add(data, name)
    story = fitz.Story(html=body_html, user_css=CSS, archive=arch)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    page_rect = fitz.paper_rect('a4')
    where = page_rect + (42, 42, -42, -54)
    more = True
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    doc = fitz.open('pdf', buf.getvalue())
    for i, page in enumerate(doc):
        page.insert_text((42, page.rect.height - 28), f'{footer}   ·   page {i + 1} of {len(doc)}', fontsize=7.5,
                         color=(0.4, 0.42, 0.52))
    doc.set_metadata({'creator': 'Pramaan', 'producer': 'Pramaan report service', 'title': footer})
    return doc.tobytes(deflate=True)


def _finding_rows(rules, findings, college):
    rows = []
    for f in findings:
        if f['weight'] <= 0 and not college:
            continue
        sev = {'high': 'red', 'medium': 'amber'}.get(f['severity'], '')
        t = pipeline.sentence(rules, f['rule'], f['evidence'], 'college' if college else 'plain')
        status = ' <span class="small">(dismissed by officer)</span>' if f.get('dismissed') else ''
        if college:
            rows.append(f'<tr><td>{_esc(t)}</td></tr>')
        else:
            rows.append(f'<tr><td class="mono">{_esc(f["rule"])}</td><td class="{sev}">{_esc(f["severity"])}</td>'
                        f'<td>+{f["weight"]}</td><td>{_esc(t)}{status}</td></tr>')
    return rows


def application_report(a, rules, kind, officer, verify_url, report_id, file_for, preview_for):
    """a: the case dict from the API. file_for(doc_id)->path, preview_for(preview)->png bytes."""
    college = kind == 'college'
    now = datetime.now()
    sm = summary(rules, a['findings'], a['lane'], college=college)
    images, parts = {}, []
    title = 'Query letter: what to fix' if college else 'Scrutiny report'
    parts.append(f'<h1>{_esc(title)}</h1>')
    parts.append(f'<p class="meta">Pramaan · AICTE application {_esc(a["id"])} · {_esc(a["institution"])} · '
                 f'{_esc(now.strftime("%d %b %Y %H:%M"))} · {"Issued by" if college else "Officer"}: {_esc(officer)}</p>')
    lane_cls = {'Inspect': 'red', 'Review': 'amber', 'Fast track': 'green'}.get(a['lane'], '')
    if college:
        parts.append(f'<p>To: {_esc(a["institution"])} ({_esc(a["code"])}), {_esc(a["district"])}<br/>'
                     f'Application: {_esc(a["category"])}, {_esc(a["programme"])}, academic year {_esc(a["academic_year"])}</p>')
        parts.append('<p>AICTE has checked the documents you submitted. Please address the points below and reply through the '
                     'AICTE portal within 15 days.</p>')
    parts.append('<div class="box">')
    parts.append(f'<p><b>{_esc(sm["headline"])}</b></p>')
    for k, it in enumerate(sm['items']):
        parts.append(f'<p>({k + 1}) {_esc(it["text"])}</p>')
    if not college:
        parts.append(f'<p><b>{_esc(sm["next_step"])}</b></p>')
        parts.append(f'<p>Risk score <span class="{lane_cls}">{a["risk"]} of 100</span> · Lane <span class="{lane_cls}">{_esc(a["lane"])}</span></p>')
    parts.append('</div>')

    if college:
        if sm['fixes']:
            parts.append('<h2>What to do</h2><table>')
            for k, fx in enumerate(sm['fixes']):
                parts.append(f'<tr><td>{k + 1}.</td><td>{_esc(fx)}</td></tr>')
            parts.append('</table>')
    else:
        parts.append('<h2>Findings</h2><table><tr><th style="width:62pt">Rule</th><th style="width:44pt">Severity</th>'
                     '<th style="width:34pt">Weight</th><th>What was found</th></tr>')
        parts += _finding_rows(rules, a['findings'], False)
        parts.append('</table>')
        # proof images
        proof = []
        for i, f in enumerate([f for f in a['findings'] if f['weight'] > 0]):
            ev = f['evidence']
            if ev.get('other_doc_id') and ev.get('doc_id'):
                ia = _img(images, f'p{i}a.jpg', file_for(ev['doc_id']), 225, 520)
                ib = _img(images, f'p{i}b.jpg', file_for(ev['other_doc_id']), 225, 520)
                proof.append(f'<p><b>{_esc(f["title"])}</b></p><table><tr><td>{ia}<br/>'
                             f'<span class="small">This application</span></td><td>{ib}<br/>'
                             f'<span class="small">{_esc(ev.get("other_institution"))}</span></td></tr></table>')
            elif ev.get('printed'):
                proof.append(f'<p><b>{_esc(f["title"])}</b></p><table><tr><td>Printed on the document<br/><b>{_esc(ev["printed"])}</b></td>'
                             f'<td>Signed by the issuer (QR)<br/><b>{_esc(ev["issuer_signed"])}</b></td></tr></table>')
            elif ev.get('preview'):
                try:
                    pv = ev['preview']
                    tag = _img(images, f'p{i}v.jpg', preview_for(pv), 200 if pv.get('heatmap') else 330, 900)
                    note = 'heat-map: bright areas re-compress unlike the rest' if pv.get('heatmap') else 'red box marks the area'
                    proof.append(f'<p><b>{_esc(f["title"])}</b> <span class="small">{_esc(ev.get("document"))}, {note}</span></p>{tag}')
                except Exception:
                    pass
        if proof:
            parts.append('<h2>Proof</h2>')
            parts += proof
        dismissed = [f for f in a['findings'] if f.get('dismissed')]
        if dismissed:
            parts.append(f'<p class="small">{len(dismissed)} flag(s) were dismissed by the officer and are not counted in the score.</p>')

    parts.append('<h2>Documents checked</h2><table><tr><th>Document</th><th>File</th><th>SHA-256 fingerprint</th></tr>')
    for d in a['documents']:
        parts.append(f'<tr><td>{_esc(d["kind_label"])}</td><td>{_esc(d["filename"])}</td><td class="mono">{_esc(d["sha256_full"])}</td></tr>')
    parts.append('</table>')
    if not college:
        parts.append(f'<p class="small">Checked with rulebook {_esc(a["rule_version"])}.</p>')
        dec = {'approve': 'Approved', 'query': 'Query sent', 'inspect': 'Inspection ordered'}.get(a.get('decision'), 'Pending')
        parts.append(f'<h2>Officer decision</h2><p>{_esc(dec)}' + (f' by {_esc(a.get("decided_by"))}' if a.get('decided_by') else '') + '</p>')
        if a.get('decision_note'):
            parts.append(f'<p><i>{_esc(a["decision_note"])}</i></p>')

    payload = {'report_id': report_id, 'kind': kind, 'application': a['id'], 'institution': a['institution'],
               'created': now.strftime('%Y-%m-%d %H:%M:%S'), 'officer': officer, 'summary': sm['text'],
               'documents': [{'file': d['filename'], 'sha256': d['sha256_full']} for d in a['documents']]}
    if not college:
        payload.update({'risk': a['risk'], 'lane': a['lane'], 'rule_version': a['rule_version'],
                        'decision': a.get('decision') or 'pending', 'next_step': sm['next_step']})
    sig = sign(payload)
    images['qr.png'] = _qr(verify_url)
    parts.append('<h2>Check this report</h2><table><tr><td style="width:90pt"><img src="qr.png" width="80" height="80"/></td><td>'
                 f'<p>Scan the code or open {_esc(verify_url)} to confirm this report was issued by Pramaan and has not been changed.</p>'
                 f'<p class="small">Report {_esc(report_id)} · digitally signed (Ed25519)<br/>'
                 f'<span class="mono">{_esc(sig[:44])}…</span></p></td></tr></table>')
    pdf = render(''.join(parts), images, f'Pramaan {title.lower()} {report_id}')
    return pdf, payload, sig


def teacher_statement(name, pan_masked, claims, verify_url, report_id):
    now = datetime.now()
    parts = ['<h1>Employment claims statement</h1>',
             f'<p class="meta">Pramaan · issued {_esc(now.strftime("%d %b %Y %H:%M"))} at the request of the teacher</p>',
             f'<p>Teacher: <b>{_esc(name)}</b> · PAN {_esc(pan_masked)}</p>',
             '<p>Every institution that has listed this teacher as faculty in an AICTE application, and the teacher\'s answer.</p>',
             '<table><tr><th>Academic year</th><th>Institution</th><th>Listed as</th><th>Teacher\'s answer</th></tr>']
    for c in claims:
        parts.append(f'<tr><td>{_esc(c["academic_year"])}</td><td>{_esc(c["institution"])}</td><td>{_esc(c["designation"])}</td>'
                     f'<td>{_esc(c["status_label"])}</td></tr>')
    parts.append('</table>')
    payload = {'report_id': report_id, 'kind': 'teacher', 'teacher': name, 'pan': pan_masked, 'created': now.strftime('%Y-%m-%d %H:%M:%S'),
               'claims': [{'year': c['academic_year'], 'institution': c['institution'], 'answer': c['status_label']} for c in claims]}
    sig = sign(payload)
    parts.append('<h2>Check this statement</h2><table><tr><td style="width:90pt"><img src="qr.png" width="80" height="80"/></td><td>'
                 f'<p>Scan the code or open {_esc(verify_url)} to confirm this statement was issued by Pramaan and has not been changed.</p>'
                 f'<p class="small">Statement {_esc(report_id)} · digitally signed (Ed25519)</p></td></tr></table>')
    pdf = render(''.join(parts), {'qr.png': _qr(verify_url)}, f'Pramaan employment claims statement {report_id}')
    return pdf, payload, sig


def new_id(prefix='RPT'):
    return f'{prefix}-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}'


def save(pdf, report_id):
    os.makedirs(REPORT_DIR, exist_ok=True)
    p = os.path.join(REPORT_DIR, f'{report_id}.pdf')
    with open(p, 'wb') as f:
        f.write(pdf)
    return p, hashlib.sha256(pdf).hexdigest()
