"""Photo fingerprint (perceptual hash) and photo details (EXIF: GPS, date, editing software)."""
import math

import numpy as np
from PIL import Image, ImageOps

try:
    import piexif
except ImportError:
    piexif = None


def _grey(img, w, h):
    return np.asarray(ImageOps.exif_transpose(img).convert('L').resize((w, h), Image.LANCZOS), dtype=np.float64)


def dhash(img, size=8):
    """Difference hash: shrink to 9x8 grey, compare each pixel with its right neighbour -> 64 bits."""
    a = _grey(img, size + 1, size)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return ''.join('1' if b else '0' for b in bits)


def _dct_matrix(n):
    m = np.zeros((n, n))
    for k in range(n):
        for i in range(n):
            m[k, i] = (math.sqrt(1 / n) if k == 0 else math.sqrt(2 / n)) * math.cos(math.pi * (2 * i + 1) * k / (2 * n))
    return m


_D32 = _dct_matrix(32)


def phash(img):
    """Perceptual hash: 32x32 grey -> 2D DCT -> top-left 8x8 low frequencies vs their median."""
    a = _grey(img, 32, 32)
    d = _D32 @ a @ _D32.T
    low = d[:8, :8].flatten()
    med = np.median(low[1:])
    return ''.join('1' if v > med else '0' for v in low)


def hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


def _rat(v):
    return v[0] / v[1] if v[1] else 0


def exif_info(path):
    out = {'lat': None, 'lng': None, 'taken': None, 'software': None, 'camera': None, 'has_exif': False}
    if piexif is None:
        return out
    try:
        ex = piexif.load(path)
    except Exception:
        return out
    z, g, e = ex.get('0th', {}), ex.get('GPS', {}), ex.get('Exif', {})
    if z or g or e:
        out['has_exif'] = True
    sw = z.get(piexif.ImageIFD.Software)
    out['software'] = sw.decode(errors='ignore') if isinstance(sw, bytes) else None
    mk = z.get(piexif.ImageIFD.Model)
    out['camera'] = mk.decode(errors='ignore') if isinstance(mk, bytes) else None
    dt = e.get(piexif.ExifIFD.DateTimeOriginal)
    if isinstance(dt, bytes):
        d = dt.decode(errors='ignore')
        out['taken'] = d[:10].replace(':', '-') + d[10:]
    try:
        lat = g[piexif.GPSIFD.GPSLatitude]; lng = g[piexif.GPSIFD.GPSLongitude]
        la = _rat(lat[0]) + _rat(lat[1]) / 60 + _rat(lat[2]) / 3600
        lo = _rat(lng[0]) + _rat(lng[1]) / 60 + _rat(lng[2]) / 3600
        if g.get(piexif.GPSIFD.GPSLatitudeRef, b'N') == b'S':
            la = -la
        if g.get(piexif.GPSIFD.GPSLongitudeRef, b'E') == b'W':
            lo = -lo
        out['lat'], out['lng'] = round(la, 6), round(lo, 6)
    except Exception:
        pass
    return out


def km_between(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
