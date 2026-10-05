"""Merge engine — Module D of the RM plan.

FINAL SYSTEM RULE (RM §13):
    The user's arranged order is the source of truth.
    orderedFiles = [PDF1, PDF2, ...] in DISPLAY order.
    for each file in orderedFiles: append ALL pages to output.

The engine NEVER sorts by filename / date / size.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter

from .models import PDFItem
from .validator import validate_output_path, validate_selection


@dataclass
class MergeResult:
    ok: bool
    message: str
    output_path: str = ""
    total_pages: int = 0
    # per-file page ownership: [(position, filename, start_page, end_page)]
    page_map: list[tuple[int, str, int, int]] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.page_map is None:
            self.page_map = []


def merge_pdfs_ordered(items: list[PDFItem], output_path: str,
                       progress_cb=None) -> MergeResult:
    """Merge `items` in the given list order. List order == merge order."""
    ok, msg = validate_selection(items)
    if not ok:
        return MergeResult(False, msg)
    ok, msg = validate_output_path(output_path)
    if not ok:
        return MergeResult(False, msg)

    # Defensive: refuse to overwrite an input file.
    out_abs = os.path.abspath(output_path)
    for it in items:
        if os.path.abspath(it.filePath) == out_abs:
            return MergeResult(
                False,
                f"Output file must not overwrite input “{it.originalFileName}”.\n"
                "Choose a different filename or folder.")

    writer = PdfWriter()
    page_map: list[tuple[int, str, int, int]] = []
    running = 0

    try:
        total = len(items)
        for idx, it in enumerate(items, start=1):
            reader = PdfReader(it.filePath)
            if reader.is_encrypted:
                return MergeResult(
                    False,
                    f"“{it.originalFileName}” is password-protected.")
            n = len(reader.pages)
            if n == 0:
                return MergeResult(
                    False, f"“{it.originalFileName}” has no pages.")
            start = running + 1
            for page in reader.pages:
                writer.add_page(page)
            running += n
            page_map.append((idx, it.originalFileName, start, running))
            if progress_cb:
                progress_cb(idx, total)

        os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
        with open(out_abs, "wb") as fh:
            writer.write(fh)

        # ---- Output validation (RM §10) ----
        if not os.path.exists(out_abs):
            return MergeResult(False, "Merge failed: output was not created.")
        check = PdfReader(out_abs)
        out_pages = len(check.pages)
        expected = sum(it.pageCount for it in items)
        if out_pages != running or out_pages != expected:
            return MergeResult(
                False,
                f"Validation failed: expected {expected} pages, "
                f"got {out_pages}. Output may be incomplete.")

        return MergeResult(
            True,
            f"Merged {len(items)} files → {out_pages} pages.",
            output_path=out_abs,
            total_pages=out_pages,
            page_map=page_map,
        )
    except Exception as exc:  # noqa: BLE001
        # Never leave a half-written output silently.
        try:
            if os.path.exists(out_abs) and os.path.getsize(out_abs) == 0:
                os.remove(out_abs)
        except OSError:
            pass
        return MergeResult(False, f"Merge failed: {exc}")
