"""Reading documents: text from PDFs (text layer, OCR if scanned), text from images (OCR),
QR codes, and picking out the fields we need."""
import io
import re
from datetime import datetime

import numpy as np
from PIL import Image

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz

try:
    import cv2
except ImportError:
    cv2 = None

import importlib.util

_ocr = None
OCR_STATUS = ('RapidOCR (PaddleOCR models)' if importlib.util.find_spec('rapidocr_onnxruntime')
              else 'not installed: scanned images need manual reading')


def _get_ocr():
    """RapidOCR runs the PaddleOCR models through ONNX Runtime. Optional."""
    global _ocr, OCR_STATUS
    if _ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
            OCR_STATUS = 'RapidOCR (PaddleOCR models)'
        except Exception as e:  # not installed
            _ocr = False
            OCR_STATUS = f'OCR not installed ({e.__class__.__name__})'
    return _ocr or None


def ocr_image(img: Image.Image) -> str:
    eng = _get_ocr()
    if not eng:
        return ''
    arr = np.array(img.convert('RGB'))[:, :, ::-1]
    res, _ = eng(arr)
    if not res:
        return ''
    # group words into lines by vertical overlap (tolerates tilted scans), then read each line left to right
    items = []
    for box, txt, _conf in res:
        ys = [p[1] for p in box]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), box[0][0], txt))
    items.sort()
    lines = []
    for cy, h, x, txt in items:
        if lines and abs(cy - lines[-1]['cy']) < max(h, lines[-1]['h']) * 0.55:
            ln = lines[-1]
            ln['words'].append((x, txt))
            ln['cy'] = (ln['cy'] * (len(ln['words']) - 1) + cy) / len(ln['words'])
        else:
            lines.append({'cy': cy, 'h': h, 'words': [(x, txt)]})
    return '\n'.join(' '.join(t for _, t in sorted(ln['words'])) for ln in lines)


def page_images(path, zoom=2.0):
    if path.lower().endswith('.pdf'):
        doc = fitz.open(path)
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            yield Image.open(io.BytesIO(pix.tobytes('png')))
    else:
        yield Image.open(path)


def read_text(path):
    """Returns (text, method)."""
    if path.lower().endswith('.pdf'):
        doc = fitz.open(path)
        txt = '\n'.join(p.get_text() for p in doc).strip()
        if len(txt) > 40:
            return txt, 'PDF text layer'
        out = '\n'.join(ocr_image(im) for im in page_images(path))
        return out, ('OCR' if out else 'unreadable scan (OCR not installed)')
    if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff')):
        out = ocr_image(Image.open(path))
        return out, ('OCR' if out else 'unreadable image (OCR not installed)')
    with open(path, encoding='utf-8', errors='ignore') as f:
        return f.read(), 'plain text'


def read_qr(path):
    if cv2 is None:
        return None
    det = cv2.QRCodeDetector()
    for zoom in (3.0, 2.0, 4.0):
        for img in page_images(path, zoom=zoom):
            arr = np.array(img.convert('RGB'))[:, :, ::-1]
            data, pts, _ = det.detectAndDecode(arr)
            if data:
                return data
            g = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data, pts, _ = det.detectAndDecode(bw)
            if data:
                return data
    return None


# ---------------------------------------------------------------- field parsing
DATE = r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})'


def norm_date(s):
    if not s:
        return None
    s = s.replace('/', '-').replace('.', '-')
    for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def _find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_fire_noc(text):
    t = text.replace('\n', ' ')
    return {
        'noc_number': _find(r'NOC\s*No\.?\s*[:\-]?\s*([A-Z]{2,6}\s*/\s*[A-Z]{2,6}\s*/\s*\d{4}\s*/\s*\d{2,6})', t),
        'issued_to': _find(r'Issued\s*to\s*[:\-]?\s*(.+?)\s+(?:Building|Date|Address)', t),
        'issued_on': norm_date(_find(r'Date\s*of\s*issue\s*[:\-]?\s*' + DATE, t)),
        'valid_until': norm_date(_find(r'Valid\s*up\s*to\s*[:\-]?\s*' + DATE, t)),
        'signed_by': _find(r'Signed\s*by\s*[:\-]?\s*([A-Z]\.\s*[A-Z][a-z]+)', t, 0),
    }


def parse_land(text):
    t = text.replace('\n', ' ')
    return {
        'survey_number': _find(r'Survey\s*No\.?\s*[:\-]?\s*([0-9]+\s*/\s*[0-9A-Z]+)', t),
        'extent_acres': _find(r'Extent\s*[:\-]?\s*([0-9.]+)\s*acres', t),
        'owner': _find(r'Owner\s*/?\s*Trust\s*[:\-]?\s*(.+?)\s+(?:Village|Survey|Extent)', t),
        'document_number': _find(r'Document\s*No\.?\s*[:\-]?\s*([A-Z0-9\-]+)', t),
    }


def parse_faculty_csv(text):
    rows = []
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return rows
    head = [h.strip().lower() for h in lines[0].split(',')]
    for l in lines[1:]:
        parts = [p.strip() for p in l.split(',')]
        r = dict(zip(head, parts))
        rows.append({'name': r.get('name', ''), 'designation': r.get('designation', ''),
                     'pan': r.get('pan', '').upper(), 'phone': r.get('phone', '')})
    return rows
