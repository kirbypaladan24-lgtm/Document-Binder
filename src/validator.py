"""Validation — Module E of the RM plan.

Checks (before merge):
- selection is not empty
- file exists
- file is a readable, valid PDF
- file is not encrypted (or reports it clearly)
- output location is writable

Errors are returned as human-readable messages, never silent.
"""
from __future__ import annotations

import os

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import PDFItem


def validate_selection(items: list[PDFItem]) -> tuple[bool, str]:
    """Validate the whole ordered selection. Returns (ok, message)."""
    if not items:
        return False, "No PDFs selected. Add at least one PDF file first."
    for it in items:
        ok, msg = validate_single_file(it.filePath)
        if not ok:
            return False, f"“{it.originalFileName}”: {msg}"
    return True, "OK"


def validate_single_file(path: str) -> tuple[bool, str]:
    if not path or not os.path.exists(path):
        return False, "File is missing (moved, renamed or deleted)."
    if os.path.getsize(path) == 0:
        return False, "File is empty (0 bytes)."
    with open(path, "rb") as fh:
        header = fh.read(5)
    if header != b"%PDF-":
        return False, "Not a valid PDF (bad header). File may be corrupted."
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            return False, "Password-protected / encrypted — cannot merge."
        _ = len(reader.pages)  # force parse
    except PdfReadError:
        return False, "Corrupted or unsupported PDF structure."
    except Exception as exc:  # noqa: BLE001
        return False, f"Cannot be opened ({exc})."
    return True, "OK"


def validate_output_path(output_path: str) -> tuple[bool, str]:
    if not output_path:
        return False, "Choose an output location first."
    folder = os.path.dirname(os.path.abspath(output_path)) or "."
    if not os.path.isdir(folder):
        return False, f"Output folder does not exist:\n{folder}"
    if not os.access(folder, os.W_OK):
        return False, f"Output folder is not writable:\n{folder}"
    if not output_path.lower().endswith(".pdf"):
        return False, "Output filename must end with .pdf"
    return True, "OK"


def probe_pdf(path: str) -> tuple[int, str, str]:
    """Return (page_count, status, error). Used when adding files."""
    ok, msg = validate_single_file(path)
    if not ok:
        # distinguish encrypted / missing for nicer badges
        status = "missing" if "missing" in msg else (
            "encrypted" if "Password" in msg or "encrypted" in msg else "error")
        return 0, status, msg
    try:
        return len(PdfReader(path).pages), "ready", ""
    except Exception as exc:  # noqa: BLE001
        return 0, "error", str(exc)
