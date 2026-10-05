"""Data model — PDFItem.

The visual order in the UI is the authoritative merge order.
position = 1-based index in the displayed list (PDF 1, PDF 2, ...).
The merge engine uses position order, never filename/date/size.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field


@dataclass
class PDFItem:
    originalFileName: str
    filePath: str
    position: int = 0          # 1-based display order, managed by MainWindow
    pageCount: int = 0
    fileSize: int = 0
    status: str = "ready"      # ready | error | encrypted | missing
    error: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def display_name(self) -> str:
        return self.originalFileName

    @property
    def file_size_human(self) -> str:
        size = float(self.fileSize)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"

    @staticmethod
    def from_path(path: str, page_count: int = 0, status: str = "ready",
                  error: str = "") -> "PDFItem":
        abspath = os.path.abspath(path)
        size = os.path.getsize(abspath) if os.path.exists(abspath) else 0
        return PDFItem(
            originalFileName=os.path.basename(abspath),
            filePath=abspath,
            pageCount=page_count,
            fileSize=size,
            status=status,
            error=error,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "originalFileName": self.originalFileName,
            "filePath": self.filePath,
            "position": self.position,
            "pageCount": self.pageCount,
            "fileSize": self.fileSize,
            "status": self.status,
        }
