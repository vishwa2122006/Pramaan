"""Checks on the file itself, for when the issuer QR is missing or damaged.

PDFs
  1. Edit history: each save that changes a PDF appends a new section ending in %%EOF.
     A certificate straight from the issuer has one; an edited copy has two or more.
  2. Dates and tools: created vs. last modified, and which program saved it.
  3. Font mismatch: a key field set in a different font or size from the other fields.
  4. White box cover-up: a white rectangle drawn over text that is still in the file.

Scanned images
  5. Error level analysis (ELA): re-save the JPEG at a fixed quality and compare. Areas pasted in
     later re-compress differently and light up in a heat-map.
  6. Copy-move: the same patch (e.g. a seal) appearing twice in one image, found with ORB keypoints.

Image results only say "look here". They are never treated as proof on their own; the officer decides."""
import io
import re
from datetime import datetime

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

try:
    import pymupdf as fitz
except ImportError:
    import fitz

try:
    import cv2
except ImportError:
    cv2 = None

# Programs commonly used to alter a finished PDF. An issuer's own system is not on this list.
EDITORS = ['ilovepdf', 'smallpdf', 'sejda', 'pdfescape', 'pdf-xchange', 'foxit', 'nitro', 'acrobat', 'pdfelement',
           'libreoffice', 'microsoft', 'word', 'canva', 'photoshop', 'pdf24', 'soda pdf', 'pdffiller', 'docfly']

# Field labels whose values are compared for font consistency
FIELD_LABELS = ['NOC No.', 'Issued to', 'Building', 'Date of issue', 'Valid up to', 'Document No.', 'Owner / Trust',
                'Village', 'Survey No.', 'Extent']
KEY_FIELDS = {'Valid up to', 'Date of issue', 'NOC No.', 'Survey No.', 'Extent', 'Issued to'}


def _pdf_date(v):
    """PDF dates look like D:20260312101500+05'30'."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", v or '')
    if not m:
        return None
    parts = [int(x) if x else d for x, d in zip(m.groups(), (0, 1, 1, 0, 0, 0))]
    try:
        return datetime(*parts)
    except ValueError:
        return None


def _fmt(d):
    return d.strftime('%d-%m-%Y') if d else 'unknown'


def _short_font(name):
    return re.sub(r'^[A-Z]{6}\+', '', name or '')


# ---------------------------------------------------------------- PDF
def pdf_history(path):
    with open(path, 'rb') as f:
        raw = f.read()
    saves = max(1, len(re.findall(rb'%%EOF', raw)))
    doc = fitz.open(path)
    try:
        if doc.is_fast_webaccess and saves > 1:  # linearised files carry one extra marker legitimately
            saves -= 1
    except Exception:
        pass
    md = doc.metadata or {}
    created, modified = _pdf_date(md.get('creationDate')), _pdf_date(md.get('modDate'))
    creator, producer = (md.get('creator') or '').strip(), (md.get('producer') or '').strip()
    tool = producer or creator
    editor = next((e for e in EDITORS if e in tool.lower()), None)
    gap_days = (modified - created).days if created and modified else 0
    summary = f'Created {_fmt(created)}' + (f' by {creator}' if creator else '')
    if modified and (not created or modified != created):
        summary += f' · Modified {_fmt(modified)}' + (f' with {producer}' if producer and producer != creator else '')
    summary += f' · {saves} save session{"s" if saves != 1 else ""}'
    return {'saves': saves, 'created': created.isoformat() if created else None,
            'modified': modified.isoformat() if modified else None, 'creator': creator, 'producer': producer,
            'editor': editor, 'gap_days': gap_days, 'summary': summary}


def _value_spans(page, covers=()):
    """For each known field label, return the text span(s) printed to its right on the same line."""
    spans = []
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines', []):
            for sp in line['spans']:
                hidden = any(_covered(sp['bbox'], c['bbox']) and sp['text'].strip() in c['hidden_text'] for c in covers)
                if sp['text'].strip() and not hidden:  # skip text that sits under a white box
                    spans.append(sp)
    out = []
    for lab in [s for s in spans if s['text'].strip().rstrip(':') in FIELD_LABELS]:
        label = lab['text'].strip().rstrip(':')
        y = (lab['bbox'][1] + lab['bbox'][3]) / 2
        right = [s for s in spans if s is not lab and s['bbox'][0] > lab['bbox'][2] - 1
                 and abs((s['bbox'][1] + s['bbox'][3]) / 2 - y) < 6]
        if right:
            v = min(right, key=lambda s: s['bbox'][0])
            out.append({'label': label, 'text': v['text'].strip(), 'font': _short_font(v['font']),
                        'size': round(v['size'], 1), 'bbox': [round(x, 1) for x in v['bbox']]})
    return out


def _covered(bbox, cover):
    r = fitz.Rect(bbox) & fitz.Rect(cover)
    return not r.is_empty and r.get_area() > 0.6 * fitz.Rect(bbox).get_area()


def font_mismatch(page, covers=()):
    vals = _value_spans(page, covers)
    if len(vals) < 3:
        return []
    styles = {}
    for v in vals:
        styles.setdefault((v['font'], v['size']), []).append(v)
    common = max(styles, key=lambda k: len(styles[k]))
    if len(styles[common]) < 2:
        return []
    odd = []
    for v in vals:
        if (v['font'], v['size']) != common and v['label'] in KEY_FIELDS:
            odd.append({**v, 'expected_font': common[0], 'expected_size': common[1]})
    return odd


def white_boxes(page):
    """White filled rectangles drawn after (on top of) text that is still in the file."""
    hits = []
    try:
        trace = page.get_texttrace()
    except Exception:
        return hits
    pr = page.rect
    for d in page.get_drawings():
        fill = d.get('fill')
        if not fill or min(fill) < 0.94:
            continue
        r = d['rect']
        if r.width * r.height < 30 or r.width > pr.width * 0.9 or r.height > pr.height * 0.5:
            continue
        hidden = []
        for t in trace:
            if t.get('seqno', 0) >= d.get('seqno', 0):
                continue
            for ch in t['chars']:
                cb = fitz.Rect(ch[3])
                if cb.is_empty:
                    continue
                inter = cb & r
                if not inter.is_empty and inter.get_area() > 0.6 * cb.get_area():
                    hidden.append(chr(ch[0]))
        txt = ''.join(hidden).strip()
        if txt:
            hits.append({'bbox': [round(x, 1) for x in r], 'hidden_text': re.sub(r'\s+', ' ', txt)})
    return hits


def analyse_pdf(path):
    res = {'type': 'pdf', 'history': pdf_history(path), 'fonts': [], 'covers': []}
    doc = fitz.open(path)
    for i, page in enumerate(doc):
        covers = white_boxes(page)
        for w in covers:
            res['covers'].append({**w, 'page': i})
        for f in font_mismatch(page, covers):
            res['fonts'].append({**f, 'page': i})
    return res


def _crop_to(img, boxes, mx, my):
    if not boxes:
        return img
    x0 = max(0, min(b[0] for b in boxes) - mx); y0 = max(0, min(b[1] for b in boxes) - my)
    x1 = min(img.width, max(b[2] for b in boxes) + mx); y1 = min(img.height, max(b[3] for b in boxes) + my)
    return img.crop((int(x0), int(y0), int(x1), int(y1)))


def pdf_preview(path, page_no=0, boxes=(), zoom=1.6, crop=False):
    """PNG of one page with red boxes around suspicious areas (optionally cropped to them)."""
    doc = fitz.open(path)
    page = doc[min(page_no, len(doc) - 1)]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    d = ImageDraw.Draw(img)
    for b in boxes:
        x0, y0, x1, y1 = [v * zoom for v in b]
        d.rectangle([x0 - 5, y0 - 4, x1 + 5, y1 + 4], outline=(200, 30, 30), width=4)
    if crop:
        img = _crop_to(img, [[v * zoom for v in b] for b in boxes], 260, 110)
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


# ---------------------------------------------------------------- scanned images
BLOCK = 16


def ela(img: Image.Image, quality=90):
    """Returns (per-block error map, amplified difference image)."""
    img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)
    re_img = Image.open(io.BytesIO(buf.getvalue()))
    diff = ImageChops.difference(img, re_img)
    a = np.asarray(diff, dtype=np.float32).max(axis=2)
    h, w = a.shape
    hb, wb = h // BLOCK, w // BLOCK
    blocks = a[:hb * BLOCK, :wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean(axis=(1, 3))
    return blocks, a


def _components(mask):
    """Connected groups of True cells (4-neighbour), as lists of (r, c)."""
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for r, c in zip(*np.nonzero(mask)):
        if seen[r, c]:
            continue
        stack, comp = [(r, c)], []
        seen[r, c] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        out.append(comp)
    return out


def ela_hotspots(img: Image.Image):
    """Blank-paper areas that re-compress unlike the rest of the blank paper.
    Text always re-compresses with high error, so only plain areas are compared with each other:
    a pasted patch carries its own background, and that background gives it away."""
    blocks, _ = ela(img)
    g = np.asarray(img.convert('L'), dtype=np.float32)
    hb, wb = blocks.shape
    gb = g[:hb * BLOCK, :wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK)
    std = gb.std(axis=(1, 3))
    plain = std < 6
    plain[:2, :] = plain[-2:, :] = False   # page edges: scanner borders and rotation fill
    plain[:, :2] = plain[:, -2:] = False
    if plain.sum() < 20:
        return {'baseline': None, 'threshold': None, 'spots': []}
    base = float(np.median(blocks[plain]))
    thresh = max(base * 4, base + 0.35)
    hot = plain & (blocks > thresh)
    spots = []
    for comp in _components(hot):
        if len(comp) < 3:
            continue
        ys = [p[0] for p in comp]; xs = [p[1] for p in comp]
        score = float(np.mean([blocks[p] for p in comp]) / max(base, 0.05))
        spots.append({'bbox': [int(max(0, min(xs) - 1) * BLOCK), int(max(0, min(ys) - 1) * BLOCK),
                               int(min(wb, max(xs) + 2) * BLOCK), int(min(hb, max(ys) + 2) * BLOCK)],
                      'blocks': len(comp), 'score': round(score, 1)})
    spots.sort(key=lambda s: -s['score'] * s['blocks'])
    return {'baseline': round(base, 3), 'threshold': round(thresh, 3), 'spots': spots[:4]}


def copy_move(img: Image.Image, min_matches=100):
    """Same patch pasted twice in one image: many keypoint pairs sharing one shift, packed into a small area."""
    if cv2 is None:
        return []
    g = np.asarray(img.convert('L'))
    scale = 1.0
    if max(g.shape) > 1800:
        scale = 1800 / max(g.shape)
        g = cv2.resize(g, None, fx=scale, fy=scale)
    orb = cv2.ORB_create(nfeatures=20000, scaleFactor=1.2, edgeThreshold=15, patchSize=21)
    kps, des = orb.detectAndCompute(g, None)
    if des is None or len(kps) < 30:
        return []
    pts = np.array([k.pt for k in kps])
    bins = {}
    for ms in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des, des, k=4):
        for m in ms[1:]:
            if m.distance > 40 or m.queryIdx > m.trainIdx:
                continue
            p1, p2 = pts[m.queryIdx], pts[m.trainIdx]
            if tuple(p1) > tuple(p2):
                p1, p2 = p2, p1
            d = p2 - p1
            if np.hypot(*d) < 80:
                continue
            bins.setdefault((round(d[0] / 8), round(d[1] / 8)), []).append((p1, p2, m.distance))
    found = []
    H, W = g.shape
    for key in sorted(bins, key=lambda k: -len(bins[k])):
        group = [pp for dx in (-1, 0, 1) for dy in (-1, 0, 1) for pp in bins.get((key[0] + dx, key[1] + dy), [])]
        if len(group) < min_matches:
            break
        a = np.array([p for p, _, _ in group]); b = np.array([q for _, q, _ in group])
        dist = np.array([x for _, _, x in group])
        # keep the dense core (drops stray repeats of the same letter elsewhere on the page)
        c = np.median(a, axis=0)
        core = np.linalg.norm(a - c, axis=1) < max(W, H) * 0.09
        if core.sum() < min_matches:
            continue
        a, b, dist = a[core], b[core], dist[core]
        if np.mean(dist < 15) < 0.25:  # a real copy matches almost bit for bit; repeated letters do not
            continue
        if np.ptp(a[:, 0]) > W * 0.3 or np.ptp(a[:, 1]) > H * 0.3:
            continue
        side = max(W, H) * 0.04  # a seal or signature, not a single line of repeated letters
        if np.ptp(a[:, 0]) < side or np.ptp(a[:, 1]) < side:
            continue
        box = lambda p: [round(float(v) / scale) for v in (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())]
        sb, cb = box(a), box(b)
        if any(abs(sb[0] - f['source'][0]) < 40 and abs(sb[1] - f['source'][1]) < 40 for f in found):
            continue
        found.append({'source': sb, 'copy': cb, 'matches': int(core.sum())})
        if len(found) == 2:
            break
    return found


def analyse_image(path):
    img = Image.open(path)
    res = {'type': 'image', 'ela': ela_hotspots(img), 'copy_move': copy_move(img), 'size': list(img.size)}
    res['is_jpeg'] = (img.format or '').upper() == 'JPEG'
    return res


def heatmap(path, boxes=True):
    """PNG: the scan, darkened, with heat where blank paper re-compresses unlike the rest of the blank paper.
    Text always re-compresses strongly, so it is left dark; that keeps the pasted patch visible."""
    img = Image.open(path).convert('RGB')
    blocks, _ = ela(img)
    g = np.asarray(img.convert('L'), dtype=np.float32)
    hb, wb = blocks.shape
    std = g[:hb * BLOCK, :wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).std(axis=(1, 3))
    plain = std < 6
    base = float(np.median(blocks[plain])) if plain.sum() > 20 else float(np.median(blocks))
    ratio = np.where(plain, blocks / max(base, 0.05), 1.0)
    pad = np.pad(ratio, 1, mode='edge')   # average with neighbours: lone grain fades, a pasted patch stays
    avg = sum(pad[dy:dy + hb, dx:dx + wb] for dy in range(3) for dx in range(3)) / 9
    heat = np.where(plain, np.clip((avg - 2.2) / 3.0, 0, 1), 0)
    heat[:2, :] = heat[-2:, :] = 0
    heat[:, :2] = heat[:, -2:] = 0
    hv = np.asarray(Image.fromarray((heat * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
                    .filter(ImageFilter.GaussianBlur(6)), dtype=np.float32) / 255.0
    hv = np.clip(hv * 1.6, 0, 1)[..., None]
    base_img = np.asarray(img.convert('L').convert('RGB'), dtype=np.float32) * 0.55
    color = np.concatenate([np.full_like(hv, 255), 255 * np.clip(hv * 1.4 - 0.2, 0, 1), np.zeros_like(hv)], axis=2)
    out = np.clip(base_img * (1 - hv * 0.85) + color * hv * 0.95, 0, 255).astype(np.uint8)
    im = Image.fromarray(out)
    if boxes:
        d = ImageDraw.Draw(im)
        for sp in ela_hotspots(img)['spots']:
            x0, y0, x1, y1 = sp['bbox']
            d.rectangle([x0 - 6, y0 - 6, x1 + 6, y1 + 6], outline=(255, 255, 255), width=3)
    b = io.BytesIO()
    im.save(b, 'PNG')
    return b.getvalue()


def image_preview(path, boxes=(), crop=False):
    img = Image.open(path).convert('RGB')
    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in boxes:
        d.rectangle([x0 - 6, y0 - 6, x1 + 6, y1 + 6], outline=(200, 30, 30), width=5)
    if crop:
        img = _crop_to(img, boxes, 160, 120)
    b = io.BytesIO()
    img.save(b, 'PNG')
    return b.getvalue()


def analyse(path):
    p = path.lower()
    if p.endswith('.pdf'):
        return analyse_pdf(path)
    if p.endswith(('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp')):
        return analyse_image(path)
    return None
