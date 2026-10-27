# Pramaan: working model

**SIH26261 · AICTE · Team Chaos**
Proof-based checking of AICTE approval applications.

When a college uploads its documents, Pramaan:
1. reads them,
2. checks certificates with the issuer, and checks **the file itself** for edits,
3. catches logic problems,
4. compares teachers and lab photos across **all** colleges,
5. asks teachers to confirm by SMS or in the teacher portal,
6. asks the college for **live, geo-tagged photos** with a one-time code,
7. scores the risk and sends the riskiest files to inspection first, with the proof for every flag,
8. writes a plain-language summary and a **signed PDF report** in one click.

Every step is written to a tamper-proof log.

---

## Run it in VS Code

You need **Python 3.10 or newer** (https://www.python.org/downloads/, tick **"Add python.exe to PATH"**) and, only for editing the web app, **Node.js**.

1. **File → Open Folder** and pick the `Pramaan` folder. Install the Python extension if VS Code suggests it.
2. **Terminal → Run Task… → "1. Setup (first time only)"**. This installs the libraries and creates the sample colleges. It takes 3–5 minutes and needs internet.
3. **Terminal → Run Task… → "2. Start Pramaan"** (or press `Ctrl+Shift+B`). Then open http://localhost:8000.
4. To stop, click the bin icon on the task's terminal, or press `Ctrl+C` in it.
5. To debug with breakpoints instead, open the **Run and Debug** panel (`Ctrl+Shift+D`) → **"Pramaan: run server (debug)"** → ▶. Put breakpoints in `backend/app/pipeline.py`.

> **Updating from an earlier version?** Run **Terminal → Run Task… → "Reset sample data"** once. It rebuilds the sample colleges with the new data (officers, live photos, earlier cycles). Your old database still opens without it, but the new screens will be mostly empty.

### Live photo capture from a phone

Phone browsers only allow the camera and GPS on `https://` pages, so there is a second way to start Pramaan:

1. Put the laptop and the phone on the **same Wi-Fi** (a phone hotspot works).
2. **Terminal → Run Task… → "3. Start Pramaan for phones (HTTPS, live capture)"**. The terminal prints the address, for example `https://192.168.1.5:8443`.
3. If Windows asks whether Python may use the network, choose **Allow** (private networks).
4. On the laptop open `https://localhost:8443`. Both the laptop and the phone will warn that the certificate is self-signed: choose **Advanced → Proceed**.
5. Open a case → **Live photo capture** → scan the QR code with the phone.

On macOS or Linux you can also use `./run.sh`.

To run it by hand in the VS Code terminal instead:

```
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -r requirements-ocr.txt
.venv\Scripts\python seed\seed.py
.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

> To start the demo again from scratch: **Activity log → Reset demo data**, or run the "Reset sample data" task.

---

## Demo script (about 8 minutes)

| # | Screen | What to show |
|---|---|---|
| 1 | **Region dashboard** | 8 colleges checked. District tiles coloured by risk: click **Madurai** and open Vaigai. "Is Pramaan accurate?" shows the inspection hit rate (3 of 4) and the share of flags officers overruled. |
| 2 | **Vaigai Institute** | "In plain words" at the top: 4 serious problems and the suggested next step. The lab photo matches Marutham's photo. A teacher replied NO. Click **Scrutiny report**: a signed PDF opens. Scan its QR with a phone: "Report genuine". |
| 3 | **College: Submit**, Amaravathi | Click *Fill Amaravathi details* and upload the files in `sample_documents/Amaravathi_tampered_upload_demo`. The NOC's QR is stained, so the issuer cannot be asked. Pramaan still finds: 2 save sessions, last saved with iLovePDF 7 months after issue; "Valid up to" typed in Helvetica while every other field is Times; and a white box hiding the real date **30-06-2026**. The land scan's pasted survey number lights up in the **heat-map** and the copied seal is found. *"Even without a QR code, the file itself tells us it was edited."* |
| 4 | **Palar Polytechnic** → Live photo capture | Map of the surveyed campus: the Library photo was taken 668 m outside it; the Computer lab "photo" fits one flat plane (about 99%), as a photo of a screen does. Compare **Marutham**: four photos, all ticks green. |
| 5 | Live, on a phone | Start Pramaan for phones (above). On any case click **Start a surprise session**, scan the QR, write the code on paper, take a photo holding it up and step sideways when asked. The pin appears on the laptop map within seconds. *"We don't just catch copied photos. We make copying impossible."* |
| 6 | **Practice check** | Fill Kaveri details, upload the Kaveri files. The college sees a checklist: one teacher is also listed elsewhere (the other college is not named). The Sunday-dated NOC and copied photo are **not** shown: fraud checks stay hidden so forgers cannot keep trying. 5 runs a day. |
| 7 | **Teacher portal** | Sign in as Dr. M. Kalaivani (+91 90000 11002, OTP shown on screen, PAN ending 314M). Two colleges list her. Click *I do not work here* on Nilgiri: it is re-checked at once. Download the signed claims statement. |
| 8 | **Javadhu Hills** | Printed "valid up to" (2029) ≠ issuer-signed QR (2027). One flag was dismissed by the officer with a reason; it stays visible but no longer counts. |
| 9 | **Thenpennai** | Fire department has no record of the NOC; dated on a holiday; signer had left the post. Inspection was ordered and the result recorded as *problem confirmed*. |
| 10 | **Rulebook** | Change a weight and save: a new version, every application re-checked. Each rule also holds its plain-language sentence, next step and college fix tip. |
| 11 | **Activity log** | *Verify the chain* (✔), *Demo: edit an old entry*, verify again (✖ caught). |

---

## What is real and what is simulated

| Feature | In this model |
|---|---|
| Reading PDFs (text layer) | **Real** (PyMuPDF) |
| Reading scanned images (OCR) | **Real** (RapidOCR = PaddleOCR models on ONNX Runtime). Optional. |
| QR reading | **Real** (OpenCV) |
| Issuer digital signature check | **Real** Ed25519 verification. The issuer and its key are a **sample** stand-in for DigiLocker or a state fire-service API. |
| PDF edit history, tools, font mismatch, white-box cover-up | **Real** (PyMuPDF: `%%EOF` count, metadata, every span's font and size, drawing order of white rectangles vs. text) |
| Scan heat-map (ELA) and copy-move | **Real** (re-compression at quality 90 compared on blank-paper areas; ORB keypoints matched within the same image) |
| Live capture: camera, GPS, time window, code, uniqueness, depth | **Real** in the browser (`getUserMedia`, Geolocation API). Code read by OCR. Depth: two frames ~2 s apart; a homography (one plane) vs. a fundamental matrix (any camera move) fit with OpenCV. |
| Campus boundaries | **Sample** polygons stored as verified facts. Without one, a provisional 760 m square is used. |
| Plain-language summary | **Real**, fixed sentence templates from the rulebook (no AI text generation) |
| Signed reports and verify page | **Real** Ed25519 signature + SHA-256 of the PDF. Pramaan's signing key is created on first use in `backend/storage/keys`. |
| Practice check | **Real** engine run inside a database transaction that is rolled back; only compliance rules are shown |
| Teacher login | OTP is **simulated** (shown on screen); PAN check is real (last 4 characters) |
| Teacher SMS | **Simulated** phone screen. A real SMS gateway plugs into `SmsMessage` creation. |
| Lab photo fingerprint | **Real** perceptual hashing (dHash + pHash) |
| Region dashboard | **Real** figures from the database. Earlier cycles (2025-26, 2026-27) and three officers are **sample** data. |
| District map | Tile map of Tamil Nadu's 38 districts (works offline; not a geographic outline) |
| Campus map background | OpenStreetMap tiles when online; plain background offline |
| Tamper-proof log | **Real** SHA-256 hash chain |
| Database | SQLite file. Set `DATABASE_URL` to use PostgreSQL. New columns are added automatically to an older database. |

All colleges, people, PAN numbers, phone numbers, certificates and photos are **invented samples**, and every document is watermarked "SAMPLE - NOT A REAL DOCUMENT".

### Limits, and the answer to give

- **Heat-map (ELA)** can light up on heavily compressed photos. It only says "look here" and is never treated as proof on its own; the officer decides. The PDF checks (edit history, fonts, white boxes) are much stronger.
- **GPS can be faked** with special apps. Pramaan records GPS accuracy, asks for several shots, uses a 30-minute window and lets AICTE start **surprise sessions**.
- **"Real room" check** needs the phone to move sideways between the two frames; turning on the spot is not enough, and a shot that hardly moved is marked *unclear*, not flagged. A plain wall or building front is close to flat, which is why staff hold the code card in front of it.
- **OCR** must be installed for the code check; without it the code is shown as *not checked*.

---

## How it is built

```
Pramaan/
├─ run.sh                      one-click start (macOS / Linux)
├─ backend/                    Python · FastAPI
│  ├─ app/
│  │  ├─ main.py               API + serves the web app
│  │  ├─ pipeline.py           the check engine (all rules, scoring, lanes, sentences)
│  │  ├─ extract.py            PDF text, OCR, QR, field picking
│  │  ├─ forensics.py          PDF edit history, fonts, white boxes, ELA heat-map, copy-move
│  │  ├─ capture.py            live capture sessions, campus boundary, code and depth checks
│  │  ├─ reports.py            plain-language summary, PDF reports, Ed25519 signing
│  │  ├─ issuers.py            signature check + issuer lookups
│  │  ├─ photo.py              photo fingerprint (dHash, pHash) + EXIF
│  │  ├─ audit.py              hash-chained activity log
│  │  ├─ cert.py               self-signed HTTPS certificate for phones
│  │  ├─ net.py                laptop's Wi-Fi address for links and QR codes
│  │  └─ db.py                 tables (SQLAlchemy) + automatic column upgrades
│  ├─ data/                    rulebook.json, holidays.json, issuer_registry.json, officers.json
│  ├─ seed/                    makes the sample documents, colleges, live photos and history
│  └─ static/                  built web app
├─ frontend/                   React (Vite) source of the web app
└─ sample_documents/           files to upload live in the demo (Kaveri, Amaravathi)
```

**Flow:** College uploads → read documents → check at source → check the file for edits → logic and rule checks → cross-college teacher and photo checks → SMS / portal to teachers → live geo-tagged photos → risk score → lane → plain-language summary → officer decides, records inspection results, dismisses wrong flags → signed report → everything logged → region dashboard.

### Rules (in `backend/data/rulebook.json`, editable in the app)

| Rule | Check | Weight |
|---|---|---|
| R-DOC-01 | Required document missing | 30 |
| R-READ-01 | Document could not be read | 10 |
| R-SRC-01 | QR signature not genuine | 40 |
| R-SRC-02 | Certificate not found / revoked at issuer | 35 |
| R-SRC-03 | Printed text ≠ issuer-signed QR data | 35 |
| R-SRC-04 | No issuer QR | 10 |
| R-DOC-02 | Fire NOC expires before the academic year | 30 |
| R-LOGIC-01 | Issued on a holiday or Sunday | 15 |
| R-LOGIC-02 | Signer not in post on the issue date | 25 |
| R-FACT-01 | Land record differs from verified facts | 25 |
| R-XINST-01 | Teacher also listed full-time elsewhere | 10 |
| R-SMS-01 | Teacher replied NO (SMS or portal) | 30 |
| R-NORM-01 | Faculty below the norm after removing duplicates | 20 |
| R-IMG-01 | Lab photo matches another college's photo | 35 |
| R-IMG-02 | Photo taken far from campus | 15 |
| R-IMG-03 | Photo has no camera details | 5 |
| R-IMG-04 | Photo edited in software (info) | 0 |
| **R-PDF-01** | Edited after it was issued (extra saves, different tool) | 25 |
| **R-PDF-02** | A key field uses a different font or size | 30 |
| **R-PDF-03** | White box covering text | 30 |
| **R-IMG-05** | Tampering hotspot in a scanned image | 20 |
| **R-CAP-01** | Live photo taken outside the campus boundary | 30 |
| **R-CAP-02** | One-time code missing or wrong | 30 |
| **R-CAP-03** | Live photo taken outside the time window | 15 |
| **R-CAP-04** | Looks like a photo of a screen or print | 20 |

Each rule also stores `plain` (officer sentence), `college` (sentence without other colleges' names or PANs), `next_step` and `fix` (tip for the college). Rules marked `practice` are the ones shown in the practice check.

### Changing the web app

```
cd frontend
npm install
npm run dev      # http://localhost:5173 (talks to the backend on port 8000)
npm run build    # rebuilds backend/static
```

### API (http://localhost:8000/docs)

| Method | Path | What it does |
|---|---|---|
| GET | `/api/applications` | Queue |
| GET | `/api/applications/{id}` | Full case: findings, evidence, summary, documents, reports |
| POST | `/api/applications` | College submission (multipart). Opens a live capture session. |
| POST | `/api/applications/{id}/decision` | Officer decision |
| POST | `/api/applications/{id}/inspection` | Inspection result (confirmed / no_problem) |
| POST | `/api/applications/{id}/dismiss` | Officer overrules (or restores) a flag, with a reason |
| GET | `/api/documents/{id}/preview` | Page image with red boxes |
| GET | `/api/documents/{id}/heatmap` | ELA heat-map of a scan |
| GET, POST | `/api/applications/{id}/capture` | Capture sessions and shots / start a surprise session |
| GET | `/api/capture/{token}` | The phone page's session |
| POST | `/api/capture/{token}/shot` | One live shot: two frames, GPS, accuracy |
| POST | `/api/applications/{id}/report` | Signed PDF (`internal` or `college`) |
| GET, POST | `/api/reports/{id}/verify` | Check a report's signature / an uploaded PDF's fingerprint |
| POST | `/api/practice` | Practice check (nothing is saved) |
| POST | `/api/teacher/otp`, `/api/teacher/login` | Teacher sign-in |
| GET | `/api/teacher/me`, `/api/teacher/statement` | Teacher's listings / signed claims statement |
| POST | `/api/teacher/claims/{faculty_id}` | Confirm, deny or report misuse |
| GET | `/api/dashboard` | Region dashboard figures |
| GET | `/api/sms/phones`, POST `/api/sms/{id}/reply` | Simulated SMS |
| GET, POST | `/api/rules` | Rulebook, new version |
| GET | `/api/audit`, `/api/audit/verify` | Activity log, check the chain |
| GET | `/api/graph` | Cross-college links |
