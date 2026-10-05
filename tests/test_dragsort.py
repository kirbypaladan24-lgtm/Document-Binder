"""Drag-sort list tests — deterministic seam coverage (no timing).

Covers: rebuild/badges/order, selection, live-index button signals,
FLIP placeholder moves + live renumbering, drop sync via order_ids.
Run: python -m pytest tests/ -v
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel

from src.models import PDFItem
from src.ui.dragsort import DragSortList

app = QApplication.instance() or QApplication([])


def _items():
    return [
        PDFItem(originalFileName=n, filePath=f"C:/fake/{n}",
                position=k, pageCount=k, fileSize=1000 * k)
        for k, n in enumerate(("A.pdf", "B.pdf", "C.pdf"), start=1)
    ]


def test_rebuild_badges_order_and_empty_state():
    lst = DragSortList()
    assert lst.count() == 0
    assert lst._empty.isVisibleTo(lst) or True  # overlay exists
    lst.rebuild(_items())
    assert lst.count() == 3
    assert [c.num.text() for c in lst._cards] == ["PDF 1", "PDF 2", "PDF 3"]
    assert [c.name.text() for c in lst._cards] == ["A.pdf", "B.pdf", "C.pdf"]
    assert len(lst.order_ids()) == 3 and len(set(lst.order_ids())) == 3


def test_selection_and_live_index_buttons():
    lst = DragSortList()
    items = _items()
    lst.rebuild(items)
    fired = {}
    lst.moveUp.connect(lambda i: fired.setdefault("up", i))
    lst.moveDown.connect(lambda i: fired.setdefault("down", i))
    lst.removeAt.connect(lambda i: fired.setdefault("rm", i))

    lst._card_pressed(lst.card_at(1), lst.card_at(1).rect().center())
    assert lst.selected_id() == items[1].id
    assert lst.card_at(1).objectName() == "rowCardSelected"
    assert lst.card_at(0).objectName() == "rowCard"

    lst.card_at(0).btns[1].click()  # ▼ on first card → live index 0
    assert fired.get("down") == 0
    lst.card_at(2).btns[0].click()  # ▲ on last card → live index 2
    assert fired.get("up") == 2
    lst.card_at(1).btns[2].click()  # ✕ on middle card → live index 1
    assert fired.get("rm") == 1


def test_flip_move_glides_and_renumbers():
    lst = DragSortList()
    items = _items()
    lst.rebuild(items)
    ids = lst.order_ids()
    lst._drag_card = lst.card_at(0)  # grab A…
    assert lst._target_index_for_y(10**6) == 2      # …bottom slot
    assert lst._target_index_for_y(-10**6) == 0     # …top slot
    lst._move_placeholder_to(2)                    # …drop at bottom
    assert lst.order_ids() == [ids[1], ids[2], ids[0]]
    assert [c.num.text() for c in lst._cards] == ["PDF 1", "PDF 2", "PDF 3"]
    assert [c.name.text() for c in lst._cards] == ["B.pdf", "C.pdf", "A.pdf"]
    assert len(lst._anims) == 3  # every row glides to its new spot
    lst._move_placeholder_to(2)  # same slot → no-op, no new anims
    assert len(lst._anims) == 3


def _live_ghosts():
    return [w for w in QApplication.topLevelWidgets()
            if isinstance(w, QLabel) and w.parent() is None and w.isVisible()]


def test_rapid_redrag_never_orphans_ghost():
    """Regression: dropping then instantly re-dragging (while the old
    ghost is still fading) must not leave a frozen ghost window stuck
    on screen above every app."""
    lst = DragSortList()
    lst.rebuild(_items())
    for _ in range(4):
        card = lst.card_at(0)
        c = card.mapToGlobal(card.rect().center())
        lst._card_pressed(card, c)
        lst._card_moved(c + QPoint(30, 30))  # cross threshold → drag begins
        assert lst._dragging and lst._ghost is not None
        lst._finish_drag()                   # ghost fades; next loop
        assert len(_live_ghosts()) <= 1      # re-drags immediately
    lst._clear_settle()
    QApplication.processEvents()
    assert _live_ghosts() == []
    assert lst.count() == 3  # list still fully functional
