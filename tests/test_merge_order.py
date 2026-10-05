"""Order-preservation tests (RM §11). Run: python -m pytest tests/ -v"""
import os
import tempfile

from pypdf import PdfReader, PdfWriter

from src.merge_engine import merge_pdfs_ordered
from src.models import PDFItem
from src.validator import probe_pdf


def _make_pdf(path: str, pages: int):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(612, 792)
    with open(path, "wb") as fh:
        w.write(fh)


def _items(paths: list[str]) -> list[PDFItem]:
    out = []
    for i, p in enumerate(paths, start=1):
        pages, st, err = probe_pdf(p)
        it = PDFItem.from_path(p, page_count=pages, status=st, error=err)
        it.position = i
        out.append(it)
    return out


def test_normal_merge_order():
    with tempfile.TemporaryDirectory() as d:
        paths = [os.path.join(d, n) for n in ("a.pdf", "b.pdf", "c.pdf")]
        for p, n in zip(paths, (2, 3, 1)):
            _make_pdf(p, n)
        items = _items(paths)  # PDF1=a(2), PDF2=b(3), PDF3=c(1)
        out = os.path.join(d, "out.pdf")
        res = merge_pdfs_ordered(items, out)
        assert res.ok, res.message
        assert res.total_pages == 6
        assert res.page_map[0][2:] == (1, 2)    # PDF1 owns pages 1-2
        assert res.page_map[1][2:] == (3, 5)    # PDF2 owns pages 3-5
        assert res.page_map[2][2:] == (6, 6)    # PDF3 owns page 6
        assert len(PdfReader(out).pages) == 6


def test_reordered_merge_is_source_of_truth():
    """Arrange PDF3, PDF1, PDF2 → output must follow exactly that."""
    with tempfile.TemporaryDirectory() as d:
        pa, pb, pc = (os.path.join(d, n) for n in ("a.pdf", "b.pdf", "c.pdf"))
        _make_pdf(pa, 5)
        _make_pdf(pb, 10)
        _make_pdf(pc, 7)
        items = _items([pc, pa, pb])  # user order: C, A, B
        for i, it in enumerate(items, start=1):
            it.position = i
        out = os.path.join(d, "out.pdf")
        res = merge_pdfs_ordered(items, out)
        assert res.ok, res.message
        assert res.total_pages == 22
        assert res.page_map[0][2:] == (1, 7)    # C first
        assert res.page_map[1][2:] == (8, 12)   # then A
        assert res.page_map[2][2:] == (13, 22)  # then B


def test_remove_middle_renumbers():
    with tempfile.TemporaryDirectory() as d:
        paths = [os.path.join(d, f"{n}.pdf") for n in ("1", "2", "3")]
        for p in paths:
            _make_pdf(p, 1)
        items = _items(paths)
        items.pop(1)  # remove middle (PDF2)
        for i, it in enumerate(items, start=1):
            it.position = i
        assert [it.position for it in items] == [1, 2]
        out = os.path.join(d, "out.pdf")
        res = merge_pdfs_ordered(items, out)
        assert res.ok and res.total_pages == 2
