"""Verify-at-source. The QR on an issued certificate carries the certificate details plus
the issuer's Ed25519 digital signature. We (1) check the signature with the issuer's public key,
(2) ask the issuer's registry whether that certificate exists and is still valid, and
(3) look up whether the signing officer was in post on the issue date.

In this working model the issuer registry is a local JSON file served at /mock-issuer/...,
standing in for DigiLocker / state fire-service APIs."""
import base64
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .db import DATA_DIR

REG_PATH = os.path.join(DATA_DIR, 'issuer_registry.json')


def registry():
    with open(REG_PATH, encoding='utf-8') as f:
        return json.load(f)


def canonical(payload: dict) -> bytes:
    body = {k: v for k, v in payload.items() if k != 'sig'}
    return json.dumps(body, sort_keys=True, separators=(',', ':')).encode()


def verify_qr(qr_text):
    """Returns dict(status, payload, issuer, message)."""
    try:
        payload = json.loads(qr_text)
    except Exception:
        return {'status': 'unreadable', 'payload': None, 'message': 'QR does not contain issuer data'}
    reg = registry()
    iss = reg['issuers'].get(payload.get('iss', ''))
    if not iss:
        return {'status': 'unknown_issuer', 'payload': payload, 'message': f"Issuer '{payload.get('iss')}' is not in the trusted list"}
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(iss['public_key']))
        pub.verify(base64.b64decode(payload.get('sig', '')), canonical(payload))
    except (InvalidSignature, ValueError):
        return {'status': 'bad_signature', 'payload': payload, 'issuer': iss['name'],
                'message': 'Digital signature does not match: QR data was altered or not made by the issuer'}
    return {'status': 'genuine', 'payload': payload, 'issuer': iss['name'], 'message': f"Signed by {iss['name']}"}


def lookup_certificate(iss_code, ref):
    reg = registry()
    return reg.get('certificates', {}).get(iss_code, {}).get(ref)


def officer_tenure(iss_code, name):
    reg = registry()
    for o in reg['issuers'].get(iss_code, {}).get('officers', []):
        if o['name'].lower().replace(' ', '') == (name or '').lower().replace(' ', ''):
            return o
    return None
