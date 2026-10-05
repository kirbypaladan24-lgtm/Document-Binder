"""Animated drag-to-reorder file list.

Feel goals:
- press & hold any row (grip recommended) → the file "lifts":
  a floating ghost follows the cursor (scaled-up snapshot + shadow),
  the source slot dims to mark the hole, cursor becomes a closed hand.
- while dragging, siblings GLIDE out of the way (FLIP-animated layout
  reorder) and PDF badges renumber live.
- on drop, the ghost settles into the slot (slide + fade) and the row
  fades back in. Order is emitted; MainWindow syncs the model.

Plain mouse tracking is used for the internal reorder (no QDrag), so OS
file drops (.pdf) are still accepted separately via filesDropped.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QApplication, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from src.models import PDFItem

ROW_H = 66
ANIM_MS = 170
GHOST_SCALE = 1.04


class RowCard(QWidget):
    """One file row. Presses (except on buttons) go to the parent list."""

    def __init__(self, item: PDFItem, badge: str, list_ref: "DragSortList"):
        super().__init__(objectName="rowCard")
        self.item_id = item.id
        self._list = list_ref
        self.setFixedHeight(ROW_H)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

        self.grip = QLabel("⋮⋮", objectName="grip",
                           alignment=Qt.AlignCenter,
                           toolTip="Hold & drag to move — drop it where you want it")
        self.grip.setFixedWidth(22)
        h.addWidget(self.grip)

        self.num = QLabel(badge, objectName="pdfNum",
                          alignment=Qt.AlignCenter)
        self.num.setFixedWidth(62)
        h.addWidget(self.num)

        txt = QVBoxLayout()
        txt.setSpacing(1)
        self.name = QLabel(item.display_name, objectName="fileName")
        self.name.setToolTip(item.filePath + "\n\nHold & drag the row to reorder.")
        meta = (f"{item.pageCount} pages  •  {item.file_size_human}")
        if item.status != "ready":
            meta += f"  •  ⚠ {item.error or item.status}"
        self.sub = QLabel(meta + f"\n{item.filePath}", objectName="fileMeta")
        self.sub.setToolTip(item.filePath)
        txt.addWidget(self.name)
        txt.addWidget(self.sub)
        h.addLayout(txt, 1)

        self.btns: list[QPushButton] = []
        for glyph, tip, sig in (("▲", "Move up", "up"),
                                ("▼", "Move down", "down"),
                                ("✕", "Remove", "remove")):
            b = QPushButton(glyph, objectName="tool", toolTip=tip,
                            fixedWidth=34)
            b.clicked.connect(
                lambda _=None, s=sig: self._list._card_button(self, s))
            h.addWidget(b)
            self.btns.append(b)

    # -- events: everything except button clicks is a potential drag --
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._list._card_pressed(self, event.globalPos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # pre-grab moves land here (cursor still over the card)
        self._list._card_moved(event.globalPos())
        event.accept()

    def mouseReleaseEvent(self, event):
        # non-drag releases land here (no grab active) — let the list
        # clear its press tracking so later hover-moves can't start
        # a drag from a stale press.
        if event.button() == Qt.LeftButton:
            self._list._card_released(self)
        super().mouseReleaseEvent(event)

    def set_badge(self, badge: str):
        self.num.setText(badge)

    def set_selected(self, on: bool):
        self.setObjectName("rowCardSelected" if on else "rowCard")
        self.style().unpolish(self)
        self.style().polish(self)


class DragSortList(QWidget):
    orderChanged = Signal()        # drop finished — visual order is final
    selectionChanged = Signal(str)  # selected item id ("" = none)
    moveUp = Signal(int)
    moveDown = Signal(int)
    removeAt = Signal(int)
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[RowCard] = []
        self._selected_id = ""
        self._press_card: RowCard | None = None
        self._press_pos = QPoint()
        self._dragging = False
        self._drag_card: RowCard | None = None
        self._drag_eff: QGraphicsOpacityEffect | None = None
        self._ghost: QLabel | None = None
        self._grab_offset = QPoint()
        self._anims: list[QPropertyAnimation] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAcceptDrops(True)
        self._scroll.viewport().installEventFilter(self)
        outer.addWidget(self._scroll, 1)

        self._inner = QWidget()
        self._inner.setAttribute(Qt.WA_StyledBackground, False)
        self._box = QVBoxLayout(self._inner)
        self._box.setContentsMargins(2, 2, 2, 2)
        self._box.setSpacing(6)
        self._box.addStretch(1)
        self._scroll.setWidget(self._inner)

        self._empty = QLabel("📭  Nothing here yet\nclick ＋ Add or drop files anywhere",
                             alignment=Qt.AlignCenter, objectName="hint")
        outer.addWidget(self._empty)

        self._scrollTimer = QTimer(self)
        self._scrollTimer.setInterval(30)
        self._scrollTimer.timeout.connect(self._autoscroll_tick)
        self.setAcceptDrops(True)

    # ---------------- public API (used by MainWindow) ----------------
    def rebuild(self, items: list[PDFItem]):
        self._reset_drag_state()
        vbar = self._scroll.verticalScrollBar()
        saved_scroll = vbar.value()
        while self._box.count() > 1:  # keep trailing stretch
            ch = self._box.takeAt(0)
            w = ch.widget()
            if w is not None:
                w.deleteLater()
        self._cards = []
        for k, it in enumerate(items, start=1):
            card = RowCard(it, f"PDF {k}", self)
            self._box.insertWidget(self._box.count() - 1, card)
            self._cards.append(card)
        if self._selected_id and not any(
                c.item_id == self._selected_id for c in self._cards):
            self._selected_id = ""
        self._apply_selection_styles()
        self._empty.setVisible(not self._cards)
        vbar.setValue(saved_scroll)

    def order_ids(self) -> list[str]:
        return [c.item_id for c in self._cards]

    def count(self) -> int:
        return len(self._cards)

    def selected_id(self) -> str:
        return self._selected_id

    def set_selected(self, item_id: str):
        self._selected_id = item_id
        self._apply_selection_styles()

    def renumber(self):
        for k, c in enumerate(self._cards, start=1):
            c.set_badge(f"PDF {k}")

    def card_at(self, index: int) -> RowCard | None:
        if 0 <= index < len(self._cards):
            return self._cards[index]
        return None

    def index_of(self, card: RowCard) -> int:
        try:
            return self._cards.index(card)
        except ValueError:
            return -1

    # ---------------- press / drag machinery ----------------
    def _card_pressed(self, card: RowCard, gpos: QPoint):
        self._press_card = card
        self._press_pos = gpos
        if self._selected_id != card.item_id:
            self.set_selected(card.item_id)
            self.selectionChanged.emit(card.item_id)

    def _card_moved(self, gpos: QPoint):
        if self._dragging and self._drag_card is not None:
            self._update_drag(gpos)
            return
        if (self._press_card is not None
                and (gpos - self._press_pos).manhattanLength()
                >= QApplication.startDragDistance()):
            self._begin_drag(gpos)

    def _card_released(self, card: RowCard):
        if not self._dragging and self._press_card is card:
            self._press_card = None

    def mouseMoveEvent(self, event):
        # post-grab moves land here (grab routes everything to us)
        if self._dragging:
            self._update_drag(event.globalPos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._finish_drag()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            self._press_card = None

    def _begin_drag(self, gpos: QPoint):
        card = self._press_card
        if card is None or card not in self._cards:
            return
        # A previous drop may still be settling (ghost fading). Clear it
        # FIRST: stopping its fade animation means its `finished` cleanup
        # never fires, which would orphan the old ghost window — a frozen
        # snapshot stuck on top of every app.
        self._clear_settle()
        self._dragging = True
        self._drag_card = card
        self._press_card = None

        # floating ghost: snapshot of the row, lifted + shadowed.
        # NOTE: deliberately NO WindowStaysOnTopHint — a ghost must never
        # be able to pin itself above other apps if anything goes wrong.
        pm = card.grab()
        pm = pm.scaledToWidth(int(card.width() * GHOST_SCALE),
                              Qt.SmoothTransformation)
        ghost = QLabel(None, Qt.Window | Qt.FramelessWindowHint | Qt.Tool)
        ghost.setAttribute(Qt.WA_TranslucentBackground)
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        ghost.setPixmap(pm)
        shadow = QGraphicsDropShadowEffect(
            blurRadius=26, offset=QPoint(0, 12), color=QColor(0, 0, 0, 170))
        ghost.setGraphicsEffect(shadow)
        ghost.setWindowOpacity(0.96)
        self._grab_offset = gpos - card.mapToGlobal(QPoint(0, 0))
        ghost.move(gpos - self._grab_offset)
        ghost.show()
        self._ghost = ghost

        # dim the source slot → the "hole"
        eff = QGraphicsOpacityEffect(card)
        eff.setOpacity(0.35)
        card.setGraphicsEffect(eff)
        self._drag_eff = eff

        QApplication.setOverrideCursor(Qt.ClosedHandCursor)
        self.grabMouse()
        self._scrollTimer.start()

    def _update_drag(self, gpos: QPoint):
        if not self._dragging or self._drag_card is None:
            return
        if self._ghost is not None:
            self._ghost.move(gpos - self._grab_offset)
        y = self._inner.mapFromGlobal(gpos).y()
        others = [c for c in self._cards if c is not self._drag_card]
        target = sum(1 for c in others if c.y() + c.height() * 0.5 < y)
        target = max(0, min(len(others), target))
        self._move_placeholder_to(target)

    def _target_index_for_y(self, y: int) -> int:
        """Pure helper (testable): slot index for an inner-coord y."""
        others = [c for c in self._cards if c is not self._drag_card]
        target = sum(1 for c in others if c.y() + c.height() * 0.5 < y)
        return max(0, min(len(others), target))

    def _move_placeholder_to(self, target: int):
        """FLIP: move the dimmed placeholder, glide siblings to their
        new spots with an eased position animation."""
        if self._drag_card is None or self._drag_card not in self._cards:
            return
        if self._cards.index(self._drag_card) == target:
            return
        for a in self._anims:
            a.stop()
        self._anims = []
        old = {c: QPoint(c.pos()) for c in self._cards}
        self._box.removeWidget(self._drag_card)
        self._box.insertWidget(target, self._drag_card)
        self._cards.remove(self._drag_card)
        self._cards.insert(target, self._drag_card)
        self._box.activate()
        for c in self._cards:
            if c.pos() != old[c]:
                a = QPropertyAnimation(c, b"pos", self)
                a.setDuration(ANIM_MS)
                a.setStartValue(old[c])
                a.setEndValue(QPoint(c.pos()))
                a.setEasingCurve(QEasingCurve.OutCubic)
                a.start()
                self._anims.append(a)
        self.renumber()

    def _finish_drag(self):
        if not self._dragging or self._drag_card is None:
            return
        card = self._drag_card
        self._dragging = False
        self._press_card = None
        self._scrollTimer.stop()
        try:
            self.releaseMouse()
        except Exception:  # noqa: BLE001
            pass
        try:
            QApplication.restoreOverrideCursor()
        except Exception:  # noqa: BLE001
            pass
        for a in self._anims:
            try:
                a.stop()
            except Exception:  # noqa: BLE001
                pass
        self._anims = []

        # settle: ghost glides into the slot + fades, row fades back in.
        # self._ghost is kept until the fade finishes so a rebuild that
        # interrupts the settle can still find and delete it.
        if self._ghost is not None:
            ghost = self._ghost
            dest = card.mapToGlobal(QPoint(0, 0))
            geff = QGraphicsOpacityEffect(ghost)
            ghost.setGraphicsEffect(geff)
            panim = QPropertyAnimation(ghost, b"pos", self)
            panim.setDuration(130)
            panim.setStartValue(ghost.pos())
            panim.setEndValue(dest)
            panim.setEasingCurve(QEasingCurve.OutCubic)
            oanim = QPropertyAnimation(geff, b"opacity", self)
            oanim.setDuration(150)
            oanim.setStartValue(0.96)
            oanim.setEndValue(0.0)

            def _ghost_done():
                ghost.deleteLater()
                if self._ghost is ghost:
                    self._ghost = None

            oanim.finished.connect(_ghost_done)
            panim.start()
            oanim.start()
            self._anims = [panim, oanim]
        if self._drag_eff is not None:
            eff, self._drag_eff = self._drag_eff, None
            ranim = QPropertyAnimation(eff, b"opacity", self)
            ranim.setDuration(150)
            ranim.setStartValue(0.35)
            ranim.setEndValue(1.0)

            def _clear():
                try:
                    card.setGraphicsEffect(None)
                except Exception:  # noqa: BLE001
                    pass

            ranim.finished.connect(_clear)
            ranim.start()
            self._anims.append(ranim)
        self._drag_card = None
        self.orderChanged.emit()

    def _clear_settle(self):
        """Kill any in-flight drop-settle visuals (ghost fade, row fade).

        Stopping the ghost's fade means its `finished` handler never runs,
        so the ghost window is explicitly hidden + deleted here instead of
        relying on that handler. Row dim effects are swept too.
        """
        for a in self._anims:
            try:
                a.stop()
            except Exception:  # noqa: BLE001
                pass
        self._anims = []
        if self._ghost is not None:
            g, self._ghost = self._ghost, None
            try:
                g.hide()
                g.deleteLater()
            except Exception:  # noqa: BLE001
                pass
        for c in self._cards:
            try:
                if c.graphicsEffect() is not None:
                    c.setGraphicsEffect(None)
            except Exception:  # noqa: BLE001
                pass
        self._drag_eff = None

    def _reset_drag_state(self):
        if self._dragging:
            try:
                self.releaseMouse()
            except Exception:  # noqa: BLE001
                pass
            try:
                QApplication.restoreOverrideCursor()
            except Exception:  # noqa: BLE001
                pass
        self._scrollTimer.stop()
        self._clear_settle()
        self._dragging = False
        self._drag_card = None
        self._press_card = None

    def _autoscroll_tick(self):
        if not self._dragging:
            return
        vp = self._scroll.viewport()
        if not vp.rect().contains(vp.mapFromGlobal(QCursor.pos())):
            return
        bar = self._scroll.verticalScrollBar()
        p = vp.mapFromGlobal(QCursor.pos())
        margin = 52
        if p.y() < margin:
            bar.setValue(bar.value() - 14)
        elif p.y() > vp.height() - margin:
            bar.setValue(bar.value() + 14)
        else:
            return
        self._update_drag(QCursor.pos())

    # ---------------- buttons / selection / drops ----------------
    def _card_button(self, card: RowCard, which: str):
        idx = self.index_of(card)
        if idx < 0:
            return
        if which == "up":
            self.moveUp.emit(idx)
        elif which == "down":
            self.moveDown.emit(idx)
        else:
            self.removeAt.emit(idx)

    def _apply_selection_styles(self):
        for c in self._cards:
            c.set_selected(c.item_id == self._selected_id)

    def eventFilter(self, obj, event):
        # click on empty scroll area → clear selection
        if (obj is self._scroll.viewport()
                and event.type() == event.Type.MouseButtonPress
                and not self._dragging):
            if self._selected_id:
                self.set_selected("")
                self.selectionChanged.emit("")
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
                u.toLocalFile().lower().endswith(".pdf")
                for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()
                     if u.toLocalFile().lower().endswith(".pdf")]
            if paths:
                event.acceptProposedAction()
                self.filesDropped.emit(paths)
                return
        super().dropEvent(event)
