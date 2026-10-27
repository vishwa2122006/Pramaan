"""Hash-chained activity log: each entry stores the hash of the one before it,
so editing or deleting an old entry breaks the chain and is detected."""
import hashlib
import json
from datetime import datetime

from .db import AuditEntry


def _digest(prev, ts, actor, action, app_id, payload):
    body = json.dumps([prev, ts, actor, action, app_id, payload], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def log(s, actor, action, app_id='', payload=None):
    last = s.query(AuditEntry).order_by(AuditEntry.id.desc()).first()
    prev = last.hash if last else '0' * 64
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    p = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False)
    e = AuditEntry(ts=ts, actor=actor, action=action, application_id=app_id, payload=p, prev_hash=prev,
                   hash=_digest(prev, ts, actor, action, app_id, p))
    s.add(e)
    s.flush()
    return e


def verify(s):
    prev = '0' * 64
    for e in s.query(AuditEntry).order_by(AuditEntry.id).all():
        expect = _digest(prev, e.ts, e.actor, e.action, e.application_id, e.payload)
        if e.prev_hash != prev or e.hash != expect:
            return {'ok': False, 'broken_at': e.id, 'action': e.action,
                    'message': f'Entry #{e.id} was changed after it was written'}
        prev = e.hash
    return {'ok': True, 'message': 'All entries intact'}
