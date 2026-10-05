"""Thumbnail rendering via PyMuPDF (offline, local).

Used for:
- selected-file preview (first pages)
- merged preview (first pages of each file, in merge order)

If PyMuPDF is unavailable, callers fall back to a placeholder.
"""
from __future__ import annotations


def has_mupdf() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def render_page(path: str, page_no: int = 0, zoom: float = 1.2) -> bytes | None:
    """Render one page to PNG bytes. Returns None on failure."""
    try:
        import fitz
        doc = fitz.open(path)
        if page_no < 0 or page_no >= len(doc):
            doc.close()
            return None
        pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        data = pix.tobytes("png")
        doc.close()
        return data
    except Exception:  # noqa: BLE001
        return None


def page_count_fast(path: str) -> int:
    try:
        import fitz
        doc = fitz.open(path)
        n = len(doc)
        doc.close()
        return n
    except Exception:  # noqa: BLE001
        return 0
