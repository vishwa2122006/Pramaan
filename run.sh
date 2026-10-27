#!/usr/bin/env bash
# Pramaan working model (macOS / Linux)
set -e
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
if [ ! -f .venv/installed.flag ]; then
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install -r requirements-ocr.txt || echo "OCR engine not installed; scanned images will need manual reading."
  touch .venv/installed.flag
fi
[ -f storage/pramaan.db ] || python seed/seed.py
echo "Pramaan running at http://localhost:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
