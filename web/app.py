"""Flask web service — deployable PDF Merger.

Same engine as the desktop app (src/merge_engine, validator): the ordered
list of file ids sent by the browser IS the merge order. No auto-sorting,
page-count validation, encrypted/corrupt rejection.

Run locally:   python web/app.py          → http://localhost:8000
Deploy:        gunicorn web.app:app       (see Procfile / Dockerfile)

Privacy note: unlike the desktop app (100% local), a DEPLOYED service
receives users' files on the server. Uploads live in isolated temp
session folders and are swept after SESSION_TTL_HOURS (default 6).
"""
from __future__ import annotations

import io
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

from src.merge_engine import merge_pdfs_ordered
from src.models import PDFItem
from src import office_convert, preview_renderer
from src.office_convert import OFFICE_EXTS
from src.validator import probe_pdf
from web import session_store

# ---- tunable limits (env-overridable for hosting plans) ----
# Defaults are sized for small free-tier boxes (512MB RAM): one big
# LibreOffice conversion can spike hundreds of MB, so quotas stay
# modest unless you raise them via env vars.
MAX_FILES = int(os.environ.get("MAX_FILES", "30"))
MAX_FILE_MB = int(os.environ.get("MAX_FILE_MB", "50"))
SESSION_MAX_MB = int(os.environ.get("SESSION_MAX_MB", "200"))
SESSION_TTL_HOURS = float(os.environ.get("SESSION_TTL_HOURS", "6"))

# LibreOffice conversions are the memory spike: never run two at once
# in this process, no matter how many threads serve requests.
_CONVERT_LOCK = threading.Lock()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = (SESSION_MAX_MB + 50) * 1024 * 1024


@app.get("/")
def index():
    # Inject SITE_URL so link previews (og:image) get an absolute URL in
    # production. Locally it falls back to a relative path, which is fine.
    # Set e.g. SITE_URL=https://your-app.onrender.com when deploying.
    with open(os.path.join(app.static_folder, "index.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    site = os.environ.get("SITE_URL", "").rstrip("/")
    return Response(html.replace("__SITE_URL__", site), mimetype="text/html")


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.get("/api/diag")
def api_diag():
    """Deploy check: is LibreOffice actually present in this image?"""
    return jsonify(ok=True, libreoffice=office_convert.available(),
                   soffice=office_convert.find_soffice())


# ---------------- sessions / files ----------------
@app.post("/api/session")
def api_session():
    sid = session_store.new_session(SESSION_TTL_HOURS)
    return jsonify(ok=True, session_id=sid,
                   limits={"max_file_mb": MAX_FILE_MB,
                           "max_files": MAX_FILES,
                           "session_max_mb": SESSION_MAX_MB})


@app.delete("/api/session/<sid>")
def api_session_delete(sid):
    session_store.delete_session(sid)
    return jsonify(ok=True)


@app.post("/api/upload")
def api_upload():
    try:
        sid = request.form.get("session_id", "")
        sdir = session_store.session_dir(sid)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    existing = [n for n in os.listdir(sdir) if n.endswith(".pdf")]
    if len(existing) >= MAX_FILES:
        return jsonify(ok=False, error=f"Limit: {MAX_FILES} files per session."), 400

    added, rejected = [], []
    used = session_store.session_files_size(sid)
    for storage in request.files.getlist("files"):
        name = secure_filename(storage.filename or "file.pdf") or "file.pdf"
        ext = os.path.splitext(name.lower())[1]
        office = ext in OFFICE_EXTS
        if ext != ".pdf" and not office:
            rejected.append({"name": name,
                             "reason": "Only PDF, Word or PowerPoint files."})
            continue
        if len(existing) + len(added) >= MAX_FILES:
            rejected.append({"name": name, "reason": f"Limit: {MAX_FILES} files."})
            continue
        fid = session_store.new_file_id()
        raw = os.path.join(sdir, fid + (ext if office else ".pdf"))
        storage.save(raw)
        size = os.path.getsize(raw)
        if size > MAX_FILE_MB * 1024 * 1024:
            os.remove(raw)
            rejected.append({"name": name,
                             "reason": f"Bigger than {MAX_FILE_MB} MB."})
            continue
        converted = None
        dest = os.path.join(sdir, fid + ".pdf")
        if office:
            with _CONVERT_LOCK:
                ok, reason = office_convert.convert_to_pdf(raw, dest)
            try:
                os.remove(raw)
            except OSError:
                pass
            if not ok:
                rejected.append({"name": name, "reason": reason})
                continue
            converted = office_convert.convert_label(ext)
            size = os.path.getsize(dest)
        if used + size > SESSION_MAX_MB * 1024 * 1024:
            os.remove(dest)
            rejected.append({"name": name,
                             "reason": f"Session quota ({SESSION_MAX_MB} MB) exceeded."})
            continue
        pages, status, err = probe_pdf(dest)
        if status != "ready":
            os.remove(dest)
            rejected.append({"name": name, "reason": _friendly(err)})
            continue
        try:
            with open(os.path.join(sdir, fid + ".name"), "w",
                      encoding="utf-8") as fh:
                fh.write(name)
        except OSError:
            pass
        used += size
        added.append({"id": fid, "name": name, "pages": pages,
                      "size": size, "converted": converted})
    return jsonify(ok=True, added=added, rejected=rejected)


@app.delete("/api/file")
def api_file_delete():
    try:
        sid = request.args.get("session_id", "")
        fid = request.args.get("file_id", "")
        path = session_store.file_path(sid, fid)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        os.remove(os.path.splitext(path)[0] + ".name")
    except OSError:
        pass
    # also drop any stale merged outputs from this session
    _drop_outputs(sid)
    return jsonify(ok=True)


def _drop_outputs(sid: str):
    try:
        sdir = session_store.session_dir(sid)
    except ValueError:
        return
    for name in os.listdir(sdir):
        if name.startswith("merged_") and name.endswith((".pdf", ".dlname")):
            try:
                os.remove(os.path.join(sdir, name))
            except OSError:
                pass


# ---------------- merge + download ----------------
@app.post("/api/merge")
def api_merge():
    data = request.get_json(force=True, silent=True) or {}
    try:
        sid = data.get("session_id", "")
        sdir = session_store.session_dir(sid)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    order = data.get("order", [])
    if not order:
        return jsonify(ok=False, error="No files selected."), 400
    if len(order) > MAX_FILES:
        return jsonify(ok=False, error=f"Limit: {MAX_FILES} files."), 400

    items: list[PDFItem] = []
    try:
        for fid in order:
            path = session_store.file_path(sid, fid)
            if not os.path.exists(path):
                return jsonify(ok=False, error="A file is missing — re-upload it."), 400
            pages, status, err = probe_pdf(path)
            if status != "ready":
                return jsonify(ok=False, error=f"“{fid}”: {_friendly(err)}"), 400
            it = PDFItem.from_path(path, page_count=pages)
            it.originalFileName = _display_name(sdir, fid)
            items.append(it)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    for k, it in enumerate(items, start=1):
        it.position = k
    # keep the uploader's filename for display; store output by token
    display = secure_filename(data.get("filename") or "merged_document.pdf")
    if not display.lower().endswith(".pdf"):
        display += ".pdf"
    token = session_store.new_file_id()
    out_path = os.path.join(sdir, f"merged_{token}.pdf")
    try:
        with open(os.path.join(sdir, f"merged_{token}.dlname"), "w",
                  encoding="utf-8") as fh:
            fh.write(display)
    except OSError:
        pass

    res = merge_pdfs_ordered(items, out_path)
    if not res.ok:
        return jsonify(ok=False, error=res.message), 400
    page_map = [{"position": p, "name": n, "start": a, "end": b}
                for p, n, a, b in res.page_map]
    return jsonify(ok=True, pages=res.total_pages, files=len(items),
                   filename=display, page_map=page_map,
                   download_url=f"/api/download?session_id={sid}&token={token}")


@app.get("/api/download")
def api_download():
    try:
        sid = request.args.get("session_id", "")
        token = request.args.get("token", "")
        sdir = session_store.session_dir(sid)
        session_store._check_id(token, "token")
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    path = os.path.join(sdir, f"merged_{token}.pdf")
    if not os.path.exists(path):
        return jsonify(ok=False, error="File expired — merge again."), 404
    dlname = "merged_document.pdf"
    try:
        with open(os.path.join(sdir, f"merged_{token}.dlname"),
                  encoding="utf-8") as fh:
            dlname = fh.read(200).strip() or dlname
    except OSError:
        pass
    return send_file(path, mimetype="application/pdf",
                     as_attachment=True, download_name=dlname)


# ---------------- thumbnails ----------------
@app.get("/api/preview")
def api_preview():
    try:
        sid = request.args.get("session_id", "")
        fid = request.args.get("file_id", "")
        path = session_store.file_path(sid, fid)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    try:
        page = max(0, int(request.args.get("page", "0")))
        zoom = min(2.0, max(0.3, float(request.args.get("zoom", "0.8"))))
    except ValueError:
        return jsonify(ok=False, error="Bad page/zoom."), 400
    if not os.path.exists(path):
        return jsonify(ok=False, error="File expired."), 404
    data = preview_renderer.render_page(path, page, zoom=zoom)
    if not data:
        return jsonify(ok=False, error="No preview."), 404
    resp = send_file(io.BytesIO(data), mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


def _display_name(sdir: str, fid: str) -> str:
    """Original upload filename (stored in a sidecar at upload time)."""
    try:
        with open(os.path.join(sdir, fid + ".name"), encoding="utf-8") as fh:
            name = fh.read(200).strip()
            if name:
                return name
    except OSError:
        pass
    return fid + ".pdf"


def _friendly(err: str) -> str:
    if "Password" in err or "encrypted" in err:
        return "Password-protected — cannot merge."
    if "missing" in err:
        return "File is missing."
    if "Not a valid PDF" in err or "Corrupted" in err:
        return "Corrupted or invalid PDF."
    return err or "Unreadable file."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"PDF Merger web → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port)
