"""Web API tests — full flow through the Flask test client.

Covers: session, ordered upload, custom-order merge (order = truth),
page-map ownership, download bytes, preview PNG, rejections.
Run: python -m pytest tests/ -v
"""
import io
import os
import tempfile

from pypdf import PdfReader, PdfWriter

os.environ["WEB_DATA_DIR"] = tempfile.mkdtemp(prefix="pdfmerger_test_")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app  # noqa: E402

client = app.test_client()


def _pdf_bytes(pages: int) -> io.BytesIO:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf


def _session():
    r = client.post("/api/session")
    assert r.status_code == 200
    return r.get_json()["session_id"]


def _upload(sid, specs):
    data = {"session_id": sid,
            "files": [(buf, name) for buf, name in specs]}
    r = client.post("/api/upload", data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def test_full_flow_custom_order_is_truth():
    sid = _session()
    j = _upload(sid, [(_pdf_bytes(2), "A.pdf"),
                      (_pdf_bytes(3), "B.pdf"),
                      (_pdf_bytes(1), "C.pdf")])
    assert j["ok"] and len(j["added"]) == 3 and not j["rejected"]
    ids = {f["name"]: f["id"] for f in j["added"]}
    assert [f["pages"] for f in j["added"]] == [2, 3, 1]  # upload order kept

    # merge in NON-upload order: C, A, B
    r = client.post("/api/merge", json={
        "session_id": sid,
        "order": [ids["C.pdf"], ids["A.pdf"], ids["B.pdf"]],
        "filename": "out.pdf",
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    m = r.get_json()
    assert m["ok"] and m["pages"] == 6
    assert [(p["name"], p["start"], p["end"]) for p in m["page_map"]] == [
        ("C.pdf", 1, 1), ("A.pdf", 2, 3), ("B.pdf", 4, 6)]

    dl = client.get(m["download_url"])
    assert dl.status_code == 200
    assert dl.headers["Content-Type"] == "application/pdf"
    assert "out.pdf" in dl.headers.get("Content-Disposition", "")
    assert len(PdfReader(io.BytesIO(dl.data)).pages) == 6

    # thumbnails work for a merged-order file
    pv = client.get(f"/api/preview?session_id={sid}&file_id={ids['B.pdf']}"
                    "&page=0&zoom=0.7")
    assert pv.status_code == 200
    assert pv.headers["Content-Type"] == "image/png"


def test_rejections_and_bad_ids():

    sid = _session()
    j = _upload(sid, [(io.BytesIO(b"not a pdf"), "evil.txt"),
                      (io.BytesIO(b"%PDF-fake"), "fake.pdf")])
    assert j["ok"] and not j["added"] and len(j["rejected"]) == 2

    r = client.post("/api/merge", json={"session_id": sid, "order": ["0" * 32]})
    assert r.status_code == 400
    r = client.post("/api/merge", json={"session_id": "nope", "order": []})
    assert r.status_code == 400
    r = client.get("/api/download?session_id=nosuchsession&token=" + "1" * 32)
    assert r.status_code in (400, 404)


def test_branding_tab_and_search_assets():

    html = client.get("/").get_data(as_text=True)
    assert "__SITE_URL__" not in html  # placeholder always injected
    for marker in ('rel="icon" type="image/svg+xml"',
                   'rel="apple-touch-icon"',
                   'property="og:image"', 'name="twitter:card"',
                   'name="description"', 'class="seal"'):
        assert marker in html, marker
    for path, ctype in (("/cover.png", "image/png"),
                        ("/favicon.png", "image/png"),
                        ("/apple-touch-icon.png", "image/png"),
                        ("/favicon.svg", "image/svg+xml")):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["Content-Type"].startswith(ctype), path
    assert client.get("/cover.png").data[:8] == b"\x89PNG\r\n\x1a\n"
    assert "<svg" in client.get("/favicon.svg").get_data(as_text=True)


def test_session_reports_real_limits():
    j = client.post("/api/session").get_json()
    assert j["ok"] and j["session_id"]
    assert j["limits"] == {"max_file_mb": 50, "max_files": 30,
                           "session_max_mb": 200}
