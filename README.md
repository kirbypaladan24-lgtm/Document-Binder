# 📚 Offline PDF Merger and Document Consolidation System

Implements **PDF_Merger_System_Plan (RM)** — merge PDFs in the **exact user-arranged order**.
The visual list order is the source of truth: PDF 1 → PDF 2 → PDF 3 …

## ✨ Features (per RM modules)

- **Module A — File selection:** Add PDFs (multi-select), drag & drop anywhere, `.pdf` only,
  duplicate detection, metadata (name, pages, size).
- **Module B — Order manager:** PDF 1 / PDF 2 / … badges, buttery drag-to-reorder
  (floating ghost, live gliding rows, settle-on-drop), ▲ Move Up / ▼ Move Down /
  ✕ Remove, Clear All, live renumbering. **Never auto-sorts.**
- **Module C — Preview:** selected-file first-page thumbnail + first-4-pages strip,
  page count, size, position.
- **🔗 Merged-preview window (requested):** right-side tab shows **page-for-page what the
  merged PDF will contain** — section per file in merge order with output page ranges
  (e.g. *PDF 1: Chapter_1.pdf → output pages 1–5*), thumbnails, ▼ then ▼ separators,
  total files/pages summary. Updates live on every reorder/add/remove.
- **Module D — Merge engine:** sequential append, `pypdf`-based, order-faithful.
- **Module E — Validation:** missing/corrupt/encrypted/empty checks, output-writable check,
  refuses to overwrite an input, page-count validation (`sum(inputs) == output`).
- **Module F — Output:** save dialog (default `merged_document.pdf`), remembers last folder,
  success dialog with **Open folder / Open PDF**, offline SQLite history + log tab.

100% **offline/local** — no uploads (RM §7).

## 🚀 Run

```bat
cd C:\Users\user\OneDrive\Documents\PDF_Merger
pip install -r requirements.txt
python main.py
```

Preview thumbnails need `PyMuPDF` (in requirements). Without it, the app still merges —
previews show a placeholder message.

## 🧪 Tests (RM §11)

```bat
python -m pytest tests/ -v
```

Covers: normal merge, reordered merge (order = truth), remove-middle renumbering.

## 📁 Structure

```
PDF_Merger/
  main.py                  ← entry point
  requirements.txt         ← PySide6, pypdf, PyMuPDF
  src/
    models.py              ← PDFItem (position = merge order)
    validator.py           ← Module E
    merge_engine.py        ← Module D (+ §10 validation)
    preview_renderer.py    ← PyMuPDF thumbnails
    history_store.py       ← offline SQLite log
    ui/
      main_window.py       ← beautiful UI + merged preview
      styles.py            ← dark violet/cyan theme
  tests/
    test_merge_order.py    ← RM §11 TEST 01/02/04
```

## 📏 The one rule (RM §13)

> If the list shows PDF 1 = A, PDF 2 = C, PDF 3 = B → output is A-pages, then C-pages,
> then B-pages. Never reorder automatically.

---

# 🌐 Web version (deployable)

Same merge engine, browser UI — no install for your users. Dependency-free
vanilla frontend (same dark theme, buttery pointer drag-sort with live
gliding rows, selected-file + merged preview tabs, validated page-map result).

```
PDF_Merger/
  web/
    app.py               ← Flask service (sessions, upload, merge, preview, download)
    session_store.py     ← isolated temp session folders + auto-cleanup
    static/              ← index.html, styles.css, app.js (no build step, no CDN)
```

## Run locally

```bat
cd C:\Users\user\OneDrive\Documents\PDF_Merger
pip install -r requirements-web.txt
python web/app.py
REM → http://localhost:8000
```

## Deploy

**Render (easiest):** push this folder to GitHub → New Web Service → it picks up
`render.yaml` + `Dockerfile` automatically. Health check: `/health`.

**Railway / Fly.io / any Docker host:** `docker build -t pdf-merger .`
then run with `-p 8000:8000 -v pdfdata:/data`.

**Heroku-style (Procfile):** needs Python buildpack +
`pip install -r requirements-web.txt`, then the Procfile's
`gunicorn web.app:app` command.

**VPS:** `gunicorn web.app:app --bind 0.0.0.0:8000 --workers 2 --timeout 300`
behind nginx/Caddy for HTTPS.

## Limits & privacy (env vars)

| Var | Default | Meaning |
|---|---|---|
| `MAX_FILES` | 30 | files per session |
| `MAX_FILE_MB` | 100 | per-file size cap |
| `SESSION_MAX_MB` | 500 | total quota per session |
| `SESSION_TTL_HOURS` | 6 | uploads auto-deleted after this |
| `WEB_DATA_DIR` | `web/data` | where temp sessions live |
| `PORT` | 8000 | listen port |
| `SITE_URL` | (empty) | production URL, e.g. `https://your-app.onrender.com` — makes link previews (tab icon, social cards) use absolute image URLs |

Brand assets live in `web/static/`: `favicon.svg`, `favicon.png`,
`apple-touch-icon.png`, `cover.png` (social preview).

### Office files — Word & PowerPoint

The web app also accepts **.docx, .doc, .pptx** (plus .ppt, .odt, .odp,
.rtf, .txt). Office uploads are converted to PDF on the server, then
merge exactly like PDFs — converted cards are badged
(“converted from DOCX”) and keep their original filename in the page map.

Conversion needs **LibreOffice** on the server:

| Where | What to do |
|---|---|
| Docker / Render | Nothing — the `Dockerfile` installs it automatically |
| Your PC (Windows) | Install LibreOffice once (auto-detected, incl. `LIBREOFFICE_BIN` override) |
| Other Linux host | `apt install libreoffice-writer libreoffice-impress` |

Without LibreOffice, office uploads are politely rejected and PDFs keep
working — nothing crashes. (`src/office_convert.py` is shared, so the
desktop app can grow the same trick later.)

⚠️ Unlike the desktop app (100% local), a **deployed** service receives users'
files on the server. Uploads sit in isolated session folders (strict
hex ids — no path traversal), are swept after the TTL, and are never
shared. Say so on your site; for sensitive documents, point people at
the desktop app (`python main.py`) instead.

## Web tests

```bat
python -m pytest tests/test_web.py -v
```

Covers: ordered upload, custom-order merge (C,A,B → pages 1 / 2–3 / 4–6),
download byte validation, thumbnails, and rejection of junk/unknown ids.
