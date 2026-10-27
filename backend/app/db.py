"""Database models. SQLite by default; set DATABASE_URL to use PostgreSQL."""
import json
import os
from datetime import datetime

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String, Text, Boolean,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STORE_DIR = os.path.join(BASE_DIR, 'storage')
os.makedirs(STORE_DIR, exist_ok=True)

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(STORE_DIR, 'pramaan.db'))
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class JSONText(Text):
    pass


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


class Institution(Base):
    __tablename__ = 'institutions'
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True)
    name = Column(String(200))
    district = Column(String(100))
    lat = Column(Float)
    lng = Column(Float)
    created = Column(DateTime, default=datetime.now)


class Application(Base):
    __tablename__ = 'applications'
    id = Column(String(32), primary_key=True)
    institution_id = Column(Integer, ForeignKey('institutions.id'))
    category = Column(String(100))
    programme = Column(String(100))
    intake = Column(Integer)
    academic_year = Column(String(16))
    status = Column(String(20), default='submitted')
    risk = Column(Integer, default=0)
    lane = Column(String(20), default='')
    decision = Column(String(20), default='')
    decision_note = Column(Text, default='')
    rule_version = Column(String(40), default='')
    created = Column(DateTime, default=datetime.now)
    processed = Column(DateTime)
    officer = Column(String(100), default='')          # assigned scrutiny officer
    decided_by = Column(String(100), default='')
    decided_at = Column(DateTime)
    inspection_outcome = Column(String(20), default='')  # '' | confirmed | no_problem
    institution = relationship('Institution')


class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    application_id = Column(String(32), ForeignKey('applications.id'))
    kind = Column(String(32))
    filename = Column(String(255))
    path = Column(String(500))
    sha256 = Column(String(64))
    text = Column(Text, default='')
    fields = Column(Text, default='{}')
    meta = Column(Text, default='{}')


class Faculty(Base):
    __tablename__ = 'faculty'
    id = Column(Integer, primary_key=True)
    application_id = Column(String(32), ForeignKey('applications.id'))
    institution_id = Column(Integer, ForeignKey('institutions.id'))
    name = Column(String(200))
    designation = Column(String(100))
    pan_hash = Column(String(64), index=True)
    pan_masked = Column(String(20))
    phone = Column(String(30))


class Finding(Base):
    __tablename__ = 'findings'
    id = Column(Integer, primary_key=True)
    application_id = Column(String(32), ForeignKey('applications.id'), index=True)
    rule_id = Column(String(20))
    severity = Column(String(10))
    weight = Column(Integer, default=0)
    title = Column(String(300))
    detail = Column(Text)
    evidence = Column(Text, default='{}')
    dismissed = Column(Boolean, default=False)
    dismiss_note = Column(Text, default='')


class SmsMessage(Base):
    __tablename__ = 'sms'
    id = Column(Integer, primary_key=True)
    phone = Column(String(30), index=True)
    faculty_name = Column(String(200))
    pan_hash = Column(String(64))
    application_id = Column(String(32))
    institution_name = Column(String(200))
    text = Column(Text)
    status = Column(String(10), default='sent')  # sent | yes | no
    channel = Column(String(20), default='sms')  # sms | portal | portal-misuse
    created = Column(DateTime, default=datetime.now)
    replied = Column(DateTime)


class PhotoPrint(Base):
    __tablename__ = 'photo_prints'
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'))
    application_id = Column(String(32))
    institution_id = Column(Integer)
    dhash = Column(String(32))
    phash = Column(String(32))
    lat = Column(Float)
    lng = Column(Float)
    taken = Column(String(30))
    software = Column(String(100))


class VerifiedFact(Base):
    __tablename__ = 'verified_facts'
    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, index=True)
    key = Column(String(100))
    value = Column(String(300))
    source = Column(String(300))
    verified_on = Column(String(20))


class RuleVersion(Base):
    __tablename__ = 'rule_versions'
    id = Column(Integer, primary_key=True)
    version = Column(String(40))
    data = Column(Text)
    created = Column(DateTime, default=datetime.now)
    active = Column(Boolean, default=True)
    note = Column(String(300), default='')


class AuditEntry(Base):
    __tablename__ = 'audit'
    id = Column(Integer, primary_key=True)
    ts = Column(String(30))
    actor = Column(String(100))
    action = Column(String(200))
    application_id = Column(String(32))
    payload = Column(Text)
    prev_hash = Column(String(64))
    hash = Column(String(64))


class FlagDismissal(Base):
    """An officer overruled a flag. Kept apart from findings, which are rebuilt on every re-check."""
    __tablename__ = 'flag_dismissals'
    id = Column(Integer, primary_key=True)
    application_id = Column(String(32), index=True)
    rule_id = Column(String(20))
    key = Column(String(64))  # hash of rule + detail, so the same flag stays dismissed after a re-check
    note = Column(Text, default='')
    officer = Column(String(100), default='')
    created = Column(DateTime, default=datetime.now)


class CaptureSession(Base):
    __tablename__ = 'capture_sessions'
    id = Column(String(40), primary_key=True)        # unguessable link token
    application_id = Column(String(32), index=True)
    code = Column(String(16))                         # one-time code shown in every photo, e.g. PRM-7K4Q
    shots = Column(Text, default='[]')                # required shots
    created = Column(DateTime, default=datetime.now)
    expires = Column(DateTime)
    started_by = Column(String(100), default='')
    surprise = Column(Boolean, default=False)


class CaptureShot(Base):
    __tablename__ = 'capture_shots'
    id = Column(Integer, primary_key=True)
    session_id = Column(String(40), index=True)
    application_id = Column(String(32), index=True)
    document_id = Column(Integer)
    shot = Column(String(60))
    lat = Column(Float)
    lng = Column(Float)
    accuracy = Column(Float)
    taken = Column(DateTime, default=datetime.now)
    second_frame = Column(String(500), default='')
    result = Column(Text, default='{}')               # code / time / unique / live / inside checks


class Report(Base):
    __tablename__ = 'reports'
    id = Column(String(40), primary_key=True)
    application_id = Column(String(32), index=True)
    kind = Column(String(20))                         # internal | college | teacher
    created = Column(DateTime, default=datetime.now)
    officer = Column(String(100), default='')
    payload = Column(Text)                            # the signed content
    signature = Column(String(200))
    sha256 = Column(String(64))                       # of the PDF file
    path = Column(String(500))


class PracticeRun(Base):
    __tablename__ = 'practice_runs'
    id = Column(Integer, primary_key=True)
    code = Column(String(32), index=True)
    created = Column(DateTime, default=datetime.now)


class TeacherAccount(Base):
    __tablename__ = 'teacher_accounts'
    id = Column(Integer, primary_key=True)
    pan_hash = Column(String(64), index=True)
    phone = Column(String(30))
    token = Column(String(64), index=True)
    last_seen = Column(DateTime)
    previous_seen = Column(DateTime)


class TeacherOtp(Base):
    __tablename__ = 'teacher_otps'
    id = Column(Integer, primary_key=True)
    phone = Column(String(30), index=True)
    otp = Column(String(8))
    expires = Column(DateTime)


class PastCycle(Base):
    """Results of earlier approval cycles (for repeat-offender and accuracy figures)."""
    __tablename__ = 'past_cycles'
    id = Column(Integer, primary_key=True)
    institution_code = Column(String(32), index=True)
    academic_year = Column(String(16))
    lane = Column(String(20))
    flags = Column(Text, default='[]')
    decision = Column(String(20), default='')
    inspection_outcome = Column(String(20), default='')


def _migrate():
    """Add columns that newer versions introduced to an existing database (SQLite / PostgreSQL)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c['name'] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                kind = col.type.compile(engine.dialect)
                with engine.begin() as cx:
                    cx.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {kind}'))


def init_db():
    Base.metadata.create_all(engine)
    _migrate()


def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
