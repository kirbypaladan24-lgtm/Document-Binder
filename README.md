# Bindery — put your pages in order, bind them into one document

Drop in PDFs, Word and PowerPoint files. Drag them into sequence —
what you see is exactly what you get. Flip through every page first,
inspect the final file fullscreen, then bind and download one finished
document with the page order double-checked.

> **The one rule:** if the list shows 1 = A, 2 = C, 3 = B, the output is
> A-pages, then C-pages, then B-pages. Never reordered behind your back.

## The two faces

| | Web app (the live product) | Desktop app |
|---|---|---|
| Run | `py web/app.py` → `localhost:8000`, or deployed | `python main.py` |
| Files accepted | PDF, DOCX/DOC, PPTX/PPT (+ ODT, RTF, TXT) | PDF only |
| Processing | on the server, uploads auto-delete within hours | 100% on your machine, never uploaded |
| Best for | everyday documents, sharing with anyone via link | sensitive documents that must stay local |

## What the web app does

- **Queue** — multi-file picker, drag-and-drop anywhere, duplicate
  detection, per-file page counts and sizes, PDF 1 → 2 → 3… badges.
- **Buttery reordering** — grab any row (grip on touch screens):
  a floating ghost follows your cursor while the other rows glide aside,
  badges renumber live. Arrow buttons included as backup.
- **Selected-file preview** — big page view, ◀ ▶ pager across *all*
  pages, numbered filmstrip of every page (lazy-loaded), click any page
  to view it large.
- **Bound preview** — every file's every page in merge order, each tagged
  with its global output number (`p. 7`), sectioned per file with
  `becomes pages a–b` ranges. Rebuilds live on every reorder.
- **Final preview** — after binding, flip through renders of the *actual
  generated file* fullscreen before you trust the download.
- **Fullscreen lightbox** — click any big page; arrows/← →/Esc to navigate.
- **Office conversion** — Word/PowerPoint uploads convert server-side
  (LibreOffice) and merge like natives, badged `converted from DOCX`.
- **Honest limits, upfront** — the page shows the real caps from the
  server (50 MB/file, 30 files default) and rejects oversize picks
  instantly instead of failing mid-upload.
- **Merge & download** — custom output filename (yours is respected, not
  overwritten), validated page map (`sum(inputs) == output`), one-click
  download.
- **Survives cheap hosting** — sleeps/restarts wipe temp uploads, so the
  app detects dead sessions, heals itself, and asks you to re-add files;
  wakes are retried automatically; conversions run one at a time inside
  memory-safe caps.

## What the desktop app does

Everything above for PDFs, plus: fully offline PySide6 UI with the same
animated drag-sort, first-page thumbnails, merged-preview window,
save-dialog with remembered folders, open-folder/open-file on success,
and a local SQLite merge history. No network, ever.

## Privacy, plainly

- **Web:** files travel to the server, sit in isolated per-session
  folders, and are swept automatically (default ≤ 6 h, sooner on
  restarts). No accounts, no tracking, HTTPS in transit. Everyday
  documents: fine. Passports and medical records: use the desktop app.
- **Desktop:** nothing leaves the computer. There is no upload code path.

## Run it

```bat
cd C:\Users\user\OneDrive\Documents\PDF_Merger
pip install -r requirements-web.txt   & REM web + engine
pip install -r requirements.txt       & REM desktop (adds PySide6)
py web/app.py      & REM → http://localhost:8000
python main.py     & REM desktop
```

## Deploy it (web)

**Render:** push to GitHub → New Web Service → `render.yaml` +
`Dockerfile` are auto-detected (LibreOffice baked in, health check
`/health`). Set `SITE_URL=https://your-app.onrender.com` afterwards for
correct link-preview images. Free tier sleeps when idle (app wakes
itself) and wipes temp files (app heals itself) — see
“Free-tier realities” in the table below.

**Elsewhere:** any Docker host (`docker build -t bindery .`),
Heroku-style via `Procfile`, or VPS via
`gunicorn web.app:app --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 300`.

| Var | Default | Meaning |
|---|---|---|
| `MAX_FILES` | 30 | files per session |
| `MAX_FILE_MB` | 50 | per-file cap (sized for 512 MB free boxes) |
| `SESSION_MAX_MB` | 200 | total quota per session |
| `SESSION_TTL_HOURS` | 6 | uploads auto-deleted after this |
| `WEB_DATA_DIR` | `web/data` | temp sessions live here |
| `PORT` | 8000 | listen port |
| `SITE_URL` | (empty) | production URL, for absolute preview-card image URLs |
| `LIBREOFFICE_BIN` | (auto) | override path to `soffice` |
| `OFFICE_CONVERT_TIMEOUT` | 120 | seconds per Office→PDF conversion |

Office conversion needs LibreOffice *where the server runs*: automatic
in Docker/Render, `apt install libreoffice-writer libreoffice-impress`
on bare Linux, install-once on Windows (auto-detected). Without it,
Office uploads are politely refused and PDFs keep working.

## Project map

```
PDF_Merger/
  main.py                  ← desktop entry
  web/
    app.py                 ← Flask: sessions, upload, merge, preview, download, diag
    session_store.py       ← isolated temp sessions + expiry sweep
    static/                ← index.html, styles.css, app.js (vanilla, no build, no CDN)
                            favicon.svg/png, apple-touch-icon.png, cover.png,
                            google*.html (Search Console)
  src/
    models.py              ← PDFItem (position = merge order)
    merge_engine.py        ← sequential append + page-count validation
    validator.py           ← corrupt/encrypted/missing/empty checks
    office_convert.py      ← optional LibreOffice DOC/DOCX/PPTX → PDF
    preview_renderer.py    ← PyMuPDF page thumbnails
    history_store.py       ← desktop SQLite log
    ui/                    ← desktop: main_window, dragsort (FLIP animations), styles
  tests/                   ← merge order, dragsort mechanics, ghost-leak
                            regression, web API, office fallback, limits,
                            branding assets
  Dockerfile / render.yaml / Procfile / requirements-web.txt / .gitignore
```

## Tests

```bat
python -m pytest tests/ -v
```

16 tests: order-is-truth merging, remove-middle renumbering, animated
list mechanics, rapid-redrag ghost-leak regression, full web flow
(upload → custom-order merge → byte-checked download → thumbnails),
Office graceful fallback, session limits reporting, favicon/cover/
verification-file serving, token-based final previews.
