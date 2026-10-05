"""Main window — Modules A/B/C/F + merged-preview window.

Layout
  header (title + counters)
  splitter: left card (order manager) | right card (preview tabs)
  left card: Add / Clear toolbar, ordered file list, output row, merge btn
  right card tabs: Selected file | Merged preview | History
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSplitter,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget, QLineEdit,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from src.models import PDFItem
from src.merge_engine import merge_pdfs_ordered
from src.validator import probe_pdf
from src import preview_renderer
from src.history_store import log_merge, recent_merges
from src.ui.dragsort import DragSortList
from src.ui.styles import APP_STYLE

ORG, APP = "OfflinePDF", "PDFMerger"
MAX_THUMBS_PER_FILE = 3          # thumbnails per file in merged preview
THUMB_W_SELECTED = 380
THUMB_W_STRIP = 150
THUMB_W_MERGED = 140


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Merger — Offline Document Consolidation")
        self.resize(1240, 780)
        self.setAcceptDrops(True)
        self.items: list[PDFItem] = []       # DISPLAY order == merge order
        self._thumb_cache: dict[tuple, QPixmap] = {}
        self.settings = QSettings(ORG, APP)
        self._build_ui()
        self.setStyleSheet(APP_STYLE)
        self._refresh_all()
        self.status("Ready — add files to begin. Order shown = merge order.")

    # ---------------- UI construction ----------------
    def _build_ui(self):
        central = QWidget(objectName="central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)

        # ---- header ----
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        t = QLabel("📚 PDF MERGER SYSTEM", objectName="appTitle")
        s = QLabel("Offline consolidation  •  your arranged order is the merge order  •  100% local",
                   objectName="appSub")
        title_box.addWidget(t)
        title_box.addWidget(s)
        header.addLayout(title_box, 1)
        self.countPill = QLabel("0 documents", objectName="pill")
        self.pagesPill = QLabel("0 pages total", objectName="pill")
        header.addWidget(self.countPill)
        header.addWidget(self.pagesPill)
        root.addLayout(header)

        # ---- splitter ----
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        # ---- LEFT card: order manager ----
        left = QWidget(objectName="card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(14, 14, 14, 14)
        lv.setSpacing(10)

        sec = QHBoxLayout()
        sec.addWidget(QLabel("📄  DOCUMENT ORDER  —  PDF 1 → PDF 2 → …",
                             objectName="sectionTitle"), 1)
        lv.addLayout(sec)

        toolbar = QHBoxLayout()
        self.btnAdd = QPushButton("＋  Add files")
        self.btnAdd.clicked.connect(self.add_files_dialog)
        self.btnClear = QPushButton("Clear all", objectName="danger")
        self.btnClear.clicked.connect(self.clear_all)
        toolbar.addWidget(self.btnAdd, 1)
        toolbar.addWidget(self.btnClear)
        lv.addLayout(toolbar)

        lv.addWidget(QLabel("⋮⋮ Grab & drag a row — the list glides live (arrows optional) • drop files anywhere • order = merge order",
                           objectName="hint"))

        self.fileList = DragSortList()
        self.fileList.orderChanged.connect(self.sync_from_view)
        self.fileList.selectionChanged.connect(self.on_selection_changed)
        self.fileList.moveUp.connect(self.move_up)
        self.fileList.moveDown.connect(self.move_down)
        self.fileList.removeAt.connect(self.remove_at)
        self.fileList.filesDropped.connect(self.add_paths)
        lv.addWidget(self.fileList, 1)

        # output row
        outRow = QHBoxLayout()
        self.outputEdit = QLineEdit()
        self.outputEdit.setPlaceholderText("Output file …  e.g. merged_document.pdf")
        last = self.settings.value("last_output", "", str)
        if last:
            self.outputEdit.setText(last)
        self.btnBrowse = QPushButton("Browse…")
        self.btnBrowse.clicked.connect(self.pick_output)
        outRow.addWidget(QLabel("Output:"))
        outRow.addWidget(self.outputEdit, 1)
        outRow.addWidget(self.btnBrowse)
        lv.addLayout(outRow)

        self.btnMerge = QPushButton("⚡   MERGE PDF   ⚡", objectName="primary")
        self.btnMerge.setMinimumHeight(48)
        self.btnMerge.clicked.connect(self.do_merge)
        lv.addWidget(self.btnMerge)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p% — merging…")
        self.progress.hide()
        lv.addWidget(self.progress)

        split.addWidget(left)

        # ---- RIGHT card: preview ----
        right = QWidget(objectName="card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(10)
        rv.addWidget(QLabel("👁  PREVIEW  —  see exactly what the merged PDF will look like",
                            objectName="sectionTitle"))

        self.tabs = QTabWidget()
        rv.addWidget(self.tabs, 1)

        # tab 1: selected file
        tabSel = QWidget()
        sv = QVBoxLayout(tabSel)
        self.selTitle = QLabel("No file selected", objectName="fileName")
        self.selMeta = QLabel("", objectName="fileMeta")
        self.selMeta.setWordWrap(True)
        sv.addWidget(self.selTitle)
        sv.addWidget(self.selMeta)
        self.selThumb = QLabel("Add files, then click one to preview its first page.",
                              alignment=Qt.AlignCenter, objectName="fileMeta")
        self.selThumb.setMinimumHeight(300)
        self.selThumb.setScaledContents(False)
        sv.addWidget(self.selThumb, 1)
        sv.addWidget(QLabel("First pages:", objectName="hint"))
        strip = QHBoxLayout()
        strip.setSpacing(8)
        self.stripLabels = [QLabel(alignment=Qt.AlignCenter) for _ in range(4)]
        for lab in self.stripLabels:
            lab.setFixedSize(THUMB_W_STRIP, 190)
            lab.setScaledContents(False)
            strip.addWidget(lab)
        strip.addStretch(1)
        sv.addLayout(strip)
        self.tabs.addTab(tabSel, "📑  Selected file")

        # tab 2: merged preview
        tabMerged = QWidget()
        mv = QVBoxLayout(tabMerged)
        self.mergedSummary = QLabel("", objectName="fileMeta")
        self.mergedSummary.setWordWrap(True)
        mv.addWidget(self.mergedSummary)
        self.mergedScroll = QScrollArea()
        self.mergedScroll.setWidgetResizable(True)
        self.mergedContainer = QWidget()
        self.mergedLayout = QVBoxLayout(self.mergedContainer)
        self.mergedLayout.setSpacing(6)
        self.mergedLayout.addStretch(1)
        self.mergedScroll.setWidget(self.mergedContainer)
        mv.addWidget(self.mergedScroll, 1)
        self.tabs.addTab(tabMerged, "🔗  Merged preview")

        # tab 3: history
        tabHist = QWidget()
        hv = QVBoxLayout(tabHist)
        histBar = QHBoxLayout()
        histBar.addWidget(QLabel("Local merge history (offline SQLite):",
                                 objectName="hint"), 1)
        btnRefresh = QPushButton("Refresh")
        btnRefresh.clicked.connect(self.refresh_history)
        histBar.addWidget(btnRefresh)
        hv.addLayout(histBar)
        from PySide6.QtWidgets import QListWidget as LW
        self.histList = LW()
        hv.addWidget(self.histList, 1)
        self.tabs.addTab(tabHist, "🕘  History")

        split.addWidget(right)
        split.setSizes([560, 620])
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)

        # menu
        m = self.menuBar()
        fmenu = m.addMenu("&File")
        for label, fn in (("Add files…", self.add_files_dialog),
                          ("Choose output…", self.pick_output),
                          ("Clear all", self.clear_all),
                          ("Quit", self.close)):
            a = QAction(label, self)
            a.triggered.connect(fn)
            fmenu.addAction(a)

        self.setStatusBar(QStatusBar())

    # ---------------- helpers ----------------
    def status(self, msg: str):
        self.statusBar().showMessage(msg, 8000)

    def _renumber(self):
        for i, it in enumerate(self.items, start=1):
            it.position = i

    def _known_paths(self) -> set[str]:
        return {os.path.normcase(os.path.abspath(i.filePath))
                for i in self.items}

    # ---------------- file intake (Module A) ----------------
    def add_files_dialog(self):
        start = self.settings.value("last_dir", os.path.expanduser("~"), str)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select files (selection order is kept)",
            start, "PDF files (*.pdf)")
        if paths:
            self.settings.setValue(
                "last_dir", os.path.dirname(os.path.abspath(paths[0])))
            self.add_paths(paths)

    def add_paths(self, paths: list[str]):
        added, dupes, bad = 0, 0, []
        known = self._known_paths()
        for p in paths:
            if not p.lower().endswith(".pdf"):
                bad.append(f"{os.path.basename(p)} — not a .pdf file")
                continue
            key = os.path.normcase(os.path.abspath(p))
            if key in known:
                dupes += 1
                continue
            pages, st, err = probe_pdf(p)
            item = PDFItem.from_path(p, page_count=pages, status=st, error=err)
            self.items.append(item)      # appended at END → becomes last PDF
            known.add(key)
            added += 1
        self._renumber()
        self._refresh_all()
        notes = []
        if added:
            notes.append(f"Added {added} file(s). New files go to the end — drag to reorder.")
        if dupes:
            notes.append(f"Skipped {dupes} duplicate(s).")
        if bad:
            notes.append("Rejected: " + "; ".join(bad))
            QMessageBox.warning(self, "Some files rejected", "\n".join(bad))
        self.status(" ".join(notes) if notes else "Nothing added.")
        if added and not self.outputEdit.text().strip():
            self.outputEdit.setText(os.path.join(
                self.settings.value("last_dir", os.path.expanduser("~"), str),
                "merged_document.pdf"))

    # ---------------- order manager (Module B) ----------------
    def rebuild_list(self):
        self.fileList.rebuild(self.items)

    def _selected_id(self) -> str:
        return self.fileList.selected_id()

    def sync_from_view(self):
        """Rebuild internal order from the VISUAL list order (drag & drop).

        Light refresh on purpose: the animated list already shows the new
        order, so we only renumber the model + refresh pills and the merged
        preview instead of recreating widgets (which would kill the
        drop-settle animation).
        """
        if self.fileList.count() != len(self.items):
            return
        by_id = {it.id: it for it in self.items}
        new_order = [by_id[pid] for pid in self.fileList.order_ids()
                     if pid in by_id]
        if len(new_order) == len(self.items):
            self.items = new_order
            self._renumber()
            self.fileList.renumber()
            self._update_pills()
            self.render_merged_preview()
            self.status("Order updated — PDF numbers follow the list top → bottom.")

    def move_up(self, idx: int):
        if idx > 0:
            moved_id = self.items[idx].id
            self.items[idx - 1], self.items[idx] = \
                self.items[idx], self.items[idx - 1]
            self._renumber()
            self._refresh_all()
            self.fileList.set_selected(moved_id)

    def move_down(self, idx: int):
        if idx < len(self.items) - 1:
            moved_id = self.items[idx].id
            self.items[idx + 1], self.items[idx] = \
                self.items[idx], self.items[idx + 1]
            self._renumber()
            self._refresh_all()
            self.fileList.set_selected(moved_id)

    def remove_at(self, idx: int):
        if 0 <= idx < len(self.items):
            gone = self.items.pop(idx)
            self._renumber()
            self._refresh_all()
            self.status(f"Removed “{gone.display_name}”. Numbers updated.")

    def clear_all(self):
        if not self.items:
            return
        if QMessageBox.question(self, "Clear all?",
                                f"Remove all {len(self.items)} files from the list?\n"
                                "(Files on disk are not deleted.)"
                                ) != QMessageBox.Yes:
            return
        self.items.clear()
        self._refresh_all()
        self.status("List cleared.")

    # ---------------- refresh ----------------
    def _refresh_all(self):
        self.rebuild_list()
        self._update_pills()
        self.render_selected_preview()
        self.render_merged_preview()

    def _update_pills(self):
        total_pages = sum(i.pageCount for i in self.items)
        n = len(self.items)
        self.countPill.setText(f"📄 {n} document{'s' if n != 1 else ''}")
        self.pagesPill.setText(f"📃 {total_pages} pages total")
        self.btnMerge.setEnabled(bool(self.items))

    # ---------------- preview (Module C + merged window) ----------------
    def _pixmap(self, path: str, page: int, target_w: int,
                zoom: float = 1.0) -> QPixmap | None:
        key = (os.path.abspath(path), page, target_w)
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        data = preview_renderer.render_page(path, page, zoom=zoom)
        if not data:
            return None
        pm = QPixmap()
        if not pm.loadFromData(data):
            return None
        pm = pm.scaledToWidth(target_w, Qt.SmoothTransformation)
        self._thumb_cache[key] = pm
        return pm

    def on_selection_changed(self, _item_id: str = ""):
        # DragSortList already updated the row highlight itself.
        self.render_selected_preview()

    def _current_item(self) -> PDFItem | None:
        sel = self._selected_id()
        for it in self.items:
            if it.id == sel:
                return it
        return None

    def render_selected_preview(self):
        it = self._current_item()
        if it is None:
            if self.items:
                self.selTitle.setText("Click a file to preview it")
                self.selMeta.setText("")
            else:
                self.selTitle.setText("No file selected")
                self.selMeta.setText("")
                self.selThumb.setText(
                    "Add files, then click one to preview its first page.")
                for lab in self.stripLabels:
                    lab.clear()
                    lab.setText("—")
            return
        self.selTitle.setText(f"PDF {it.position} — {it.display_name}")
        self.selMeta.setText(
            f"Position: PDF {it.position} of {len(self.items)}   •   "
            f"{it.pageCount} pages   •   {it.file_size_human}\n{it.filePath}"
            + (f"\n⚠ {it.error}" if it.status != "ready" else ""))
        pm = self._pixmap(it.filePath, 0, THUMB_W_SELECTED, zoom=1.2)
        if pm is None:
            self.selThumb.setText("Preview unavailable "
                                  "(install PyMuPDF: pip install PyMuPDF).")
        else:
            self.selThumb.setPixmap(pm)
        for k, lab in enumerate(self.stripLabels):
            if k < it.pageCount:
                p = self._pixmap(it.filePath, k, THUMB_W_STRIP, zoom=0.7)
                if p is not None:
                    lab.setPixmap(p)
                    lab.setToolTip(f"Page {k + 1}")
                else:
                    lab.setText(f"p.{k + 1}")
            else:
                lab.clear()
                lab.setText("")

    def render_merged_preview(self):
        # clear
        while self.mergedLayout.count() > 1:
            ch = self.mergedLayout.takeAt(0)
            w = ch.widget()
            if w is not None:
                w.deleteLater()
        if not self.items:
            self.mergedSummary.setText(
                "Merged preview will appear here — add files and arrange "
                "PDF 1 → PDF 2 → … The pages below show the exact merge order.")
            return
        total = sum(i.pageCount for i in self.items)
        order = "  →  ".join(f"PDF {i.position}" for i in self.items)
        self.mergedSummary.setText(
            f"📦 Output: {len(self.items)} files → {total} pages   •   {order}\n"
            "Below is page-for-page what the merged PDF will contain, in order.")
        running = 0
        for pos, it in enumerate(self.items, start=1):
            start, end = running + 1, running + it.pageCount
            running = end
            section = QWidget(objectName="rowCard")
            v = QVBoxLayout(section)
            v.setContentsMargins(10, 8, 10, 8)
            v.setSpacing(8)
            head = QHBoxLayout()
            head.addWidget(QLabel(f"PDF {pos}", objectName="badge"))
            title = QLabel(f"{it.display_name}   •   output pages {start}–{end}"
                           f"   •   {it.pageCount} pages", objectName="fileName")
            title.setWordWrap(True)
            head.addWidget(title, 1)
            v.addLayout(head)
            thumbs = QHBoxLayout()
            thumbs.setSpacing(8)
            shown = min(it.pageCount, MAX_THUMBS_PER_FILE)
            for p in range(shown):
                lab = QLabel(alignment=Qt.AlignCenter)
                lab.setFixedSize(THUMB_W_MERGED, 180)
                pm = self._pixmap(it.filePath, p, THUMB_W_MERGED, zoom=0.7)
                if pm is not None:
                    lab.setPixmap(pm)
                else:
                    lab.setText(f"p.{start + p}")
                lab.setToolTip(f"Output page {start + p} "
                               f"(file page {p + 1} of {it.display_name})")
                thumbs.addWidget(lab)
                cap = QLabel(f"→ p.{start + p}", objectName="hint",
                             alignment=Qt.AlignCenter)
                cap.setFixedWidth(THUMB_W_MERGED)
                col = QVBoxLayout()
                # wrap lab+cap: use a small container
                cell = QWidget()
                cv = QVBoxLayout(cell)
                cv.setContentsMargins(0, 0, 0, 0)
                cv.addWidget(lab)
                cv.addWidget(cap)
                thumbs.addWidget(cell)
            if it.pageCount > shown:
                more = QLabel(f"+ {it.pageCount - shown}\nmore page(s)\n"
                              f"(… → p.{end})", objectName="hint",
                              alignment=Qt.AlignCenter)
                more.setFixedSize(90, 180)
                thumbs.addWidget(more)
            thumbs.addStretch(1)
            v.addLayout(thumbs)
            self.mergedLayout.insertWidget(self.mergedLayout.count() - 1,
                                           section)
            if pos < len(self.items):
                arrow = QLabel("▼  then  ▼", objectName="mergeArrow",
                               alignment=Qt.AlignCenter)
                self.mergedLayout.insertWidget(
                    self.mergedLayout.count() - 1, arrow)

    # ---------------- output + merge (Modules D/E/F) ----------------
    def pick_output(self):
        start_dir = os.path.dirname(
            os.path.abspath(self.outputEdit.text().strip())) \
            if self.outputEdit.text().strip() else \
            self.settings.value("last_dir", os.path.expanduser("~"), str)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save merged PDF as", os.path.join(start_dir,
                                                     "merged_document.pdf"),
            "PDF files (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.outputEdit.setText(path)
            self.settings.setValue("last_output", path)
            self.settings.setValue("last_dir", os.path.dirname(path))

    def do_merge(self):
        out = self.outputEdit.text().strip()
        if not out:
            self.pick_output()
            out = self.outputEdit.text().strip()
            if not out:
                return
        self.progress.show()
        self.progress.setValue(2)
        QApplication.processEvents()
        self.btnMerge.setEnabled(False)
        self.status("Merging in displayed order…")

        def cb(done: int, total: int):
            self.progress.setValue(int(done / max(total, 1) * 95))
            QApplication.processEvents()

        res = merge_pdfs_ordered(list(self.items), out, progress_cb=cb)
        self.progress.setValue(100 if res.ok else 0)
        self.btnMerge.setEnabled(True)

        if res.ok:
            self.settings.setValue("last_output", res.output_path)
            self.settings.setValue(
                "last_dir", os.path.dirname(res.output_path))
            detail = " | ".join(f"PDF{p}:{n}[{a}-{b}]"
                                for p, n, a, b in res.page_map)
            log_merge(res.output_path, len(self.items), res.total_pages,
                      detail)
            self.refresh_history()
            self.show_success(res.output_path, res.total_pages,
                              len(self.items))
            self.status(f"✅ {res.message}  Saved → {res.output_path}")
            QTimer.singleShot(2500, self.progress.hide)
        else:
            self.progress.hide()
            QMessageBox.critical(self, "Merge failed", res.message)
            self.status(f"❌ {res.message}")

    def show_success(self, path: str, pages: int, nfiles: int):
        box = QMessageBox(self)
        box.setWindowTitle("Merge complete ✅")
        box.setText(f"Merged {nfiles} file(s) → {pages} pages.\nSaved to:\n{path}")
        box.setInformativeText("Page order follows your PDF 1 → PDF 2 → … list, "
                               "validated by page count.")
        btn_folder = box.addButton("Open folder", QMessageBox.ActionRole)
        btn_open = box.addButton("Open PDF", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        clicked = box.clickedButton()
        try:
            if clicked == btn_folder:
                folder = os.path.dirname(os.path.abspath(path))
                if sys.platform.startswith("win"):
                    os.startfile(folder)  # noqa: S606
                elif sys.platform == "darwin":
                    subprocess.run(["open", folder], check=False)
                else:
                    subprocess.run(["xdg-open", folder], check=False)
            elif clicked == btn_open:
                if sys.platform.startswith("win"):
                    os.startfile(path)  # noqa: S606
                elif sys.platform == "darwin":
                    subprocess.run(["open", path], check=False)
                else:
                    subprocess.run(["xdg-open", path], check=False)
        except Exception:  # noqa: BLE001
            pass

    # ---------------- history ----------------
    def refresh_history(self):
        self.histList.clear()
        rows = recent_merges(30)
        if not rows:
            self.histList.addItem("No merges yet — your local history will appear here.")
            return
        import datetime
        for ts, out, files, pages in rows:
            dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            self.histList.addItem(f"{dt}  •  {files} files → {pages} pages  •  {out}")

    # ---------------- OS drag & drop of files ----------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(".pdf") for u in urls):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()
                     if u.toLocalFile().lower().endswith(".pdf")]
            if paths:
                event.acceptProposedAction()
                self.add_paths(paths)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
