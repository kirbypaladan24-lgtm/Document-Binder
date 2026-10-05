"""Office upload tests — Word/PowerPoint → PDF conversion.

- Helpers + graceful fallback (no LibreOffice) run everywhere.
- Real conversion runs only where LibreOffice + python-docx exist
  (e.g. inside the Docker image, not on a bare laptop).
Run: python -m pytest tests/ -v
"""
import io
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import office_convert  # noqa: E402
from src.office_convert import OFFICE_EXTS, convert_label, is_office_file  # noqa: E402

HAS_LO = office_convert.available()
try:
    import docx  # noqa: F401
    HAS_DOCX_LIB = True
except ImportError:
    HAS_DOCX_LIB = False

os.environ.setdefault("WEB_DATA_DIR", tempfile.mkdtemp(prefix="pdfmerger_office_"))

from web.app import app  # noqa: E402

client = app.test_client()


def test_extension_helpers():
    for ext in (".docx", ".doc", ".pptx", ".ppt", ".odt", ".txt"):
        assert is_office_file("Report" + ext)
        assert is_office_file("Report" + ext.upper())
    assert not is_office_file("a.pdf")
    assert not is_office_file("evil.exe")
    assert convert_label(".docx") == "DOCX"
    assert convert_label(".pptx") == "PPTX"


def test_convert_reports_missing_libreoffice():
    if HAS_LO:
        pytest.skip("LibreOffice present — fallback path not exercised here")
    ok, reason = office_convert.convert_to_pdf("/nope/missing.docx", "/tmp/x.pdf")
    assert not ok and "LibreOffice" in reason


def test_office_upload_rejected_gracefully_without_libreoffice():
    if HAS_LO:
        pytest.skip("LibreOffice present — rejection path not exercised here")
    sid = client.post("/api/session").get_json()["session_id"]
    buf = io.BytesIO(b"PK fake office bytes")
    r = client.post("/api/upload", data={"session_id": sid,
                                         "files": [(buf, "Report.docx")]},
                    content_type="multipart/form-data")
    j = r.get_json()
    assert j["ok"] and not j["added"] and len(j["rejected"]) == 1
    assert "LibreOffice" in j["rejected"][0]["reason"]


@pytest.mark.skipif(not (HAS_LO and HAS_DOCX_LIB),
                    reason="needs LibreOffice + python-docx")
def test_real_docx_upload_converts_and_merges():
    from docx import Document
    doc = Document()
    doc.add_heading("Hello", level=1)
    doc.add_paragraph("Second page coming.")
    doc.add_page_break()
    doc.add_paragraph("Page two.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    sid = client.post("/api/session").get_json()["session_id"]
    r = client.post("/api/upload", data={"session_id": sid,
                                         "files": [(buf, "Report.docx")]},
                    content_type="multipart/form-data")
    j = r.get_json()
    assert j["ok"] and len(j["added"]) == 1, j
    f = j["added"][0]
    assert f["converted"] == "DOCX" and f["pages"] >= 2

    m = client.post("/api/merge", json={"session_id": sid,
                                        "order": [f["id"]]}).get_json()
    assert m["ok"] and m["pages"] == f["pages"]
    assert m["page_map"][0]["name"] == "Report.docx"
