"""Office → PDF conversion via headless LibreOffice.

Covers Word (.docx/.doc), PowerPoint (.pptx/.ppt) plus the freebies
LibreOffice handles the same way (.odt/.odp/.rtf/.txt).

Design:
- LibreOffice is an *optional* system dependency, not a pip package.
- If `soffice` is missing, callers get a clear (False, reason) and can
  reject the file gracefully instead of crashing.
- Each conversion gets a fresh LibreOffice user-profile dir, so parallel
  conversions (gunicorn workers) never fight over profile locks.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid

OFFICE_EXTS = {
    ".docx", ".doc",       # Word
    ".pptx", ".ppt",       # PowerPoint
    ".odt", ".odp", ".rtf", ".txt",
}

#: friendly label per extension for UI badges
EXT_LABELS = {
    ".docx": "DOCX", ".doc": "DOC",
    ".pptx": "PPTX", ".ppt": "PPT",
    ".odt": "ODT", ".odp": "ODP", ".rtf": "RTF", ".txt": "TXT",
}

CONVERT_TIMEOUT = int(os.environ.get("OFFICE_CONVERT_TIMEOUT", "120"))


def is_office_file(name: str) -> bool:
    return os.path.splitext(name.lower())[1] in OFFICE_EXTS


def find_soffice() -> str | None:
    """Locate the LibreOffice binary, or None if not installed."""
    override = os.environ.get("LIBREOFFICE_BIN")
    if override and os.path.exists(override):
        return override
    found = shutil.which("soffice")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/libreoffice/program/soffice",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def available() -> bool:
    return find_soffice() is not None


def convert_to_pdf(src_path: str, dest_pdf: str,
                   timeout: int = CONVERT_TIMEOUT) -> tuple[bool, str]:
    """Convert an office document to PDF.

    Returns (True, "") on success with dest_pdf written, else
    (False, human-readable reason).
    """
    soffice = find_soffice()
    if not soffice:
        return False, ("Word/PowerPoint files need LibreOffice on the "
                       "server — PDF files work without it.")
    if not os.path.exists(src_path):
        return False, "File is missing."
    tmpdir = tempfile.mkdtemp(prefix="lo_convert_")
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    try:
        profile_uri = _path_uri(profile)
        cmd = [soffice, "--headless", "--nolockcheck", "--nodefault",
               "--nologo", "--norestore",
               f"--env:UserInstallation={profile_uri}",
               "--convert-to", "pdf", "--outdir", tmpdir, src_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
        stem = os.path.splitext(os.path.basename(src_path))[0]
        made = os.path.join(tmpdir, stem + ".pdf")
        if proc.returncode != 0 or not os.path.exists(made):
            log = (proc.stdout or b"").decode("utf-8", "replace")[-600:]
            return False, f"Could not convert this file to PDF. {log}".strip()
        os.makedirs(os.path.dirname(os.path.abspath(dest_pdf)) or ".",
                    exist_ok=True)
        if os.path.exists(dest_pdf):
            os.remove(dest_pdf)
        shutil.move(made, dest_pdf)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Conversion took too long — try a smaller file."
    except Exception as exc:  # noqa: BLE001
        return False, f"Conversion failed ({exc})."
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)


def _path_uri(path: str) -> str:
    import pathlib
    return pathlib.Path(os.path.abspath(path)).as_uri()


def convert_label(ext: str) -> str:
    return EXT_LABELS.get(ext.lower(), ext.upper().lstrip("."))
