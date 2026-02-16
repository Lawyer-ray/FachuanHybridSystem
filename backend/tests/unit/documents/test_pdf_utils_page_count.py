import builtins

import fitz

from apps.documents.services.pdf_utils import get_pdf_page_count, get_pdf_page_count_with_error


def _make_pdf_bytes(pages: int) -> bytes:
    doc = fitz.open()
    try:
        for _ in range(pages):
            doc.new_page()
        return doc.tobytes()
    finally:
        doc.close()


def test_get_pdf_page_count_with_error_returns_count_for_valid_pdf_bytes():
    data = _make_pdf_bytes(3)
    count, error = get_pdf_page_count_with_error(data, default=1)
    assert count == 3
    assert error is None


def test_get_pdf_page_count_with_error_falls_back_when_pikepdf_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pikepdf":
            raise ModuleNotFoundError("No module named 'pikepdf'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    data = _make_pdf_bytes(2)
    count, error = get_pdf_page_count_with_error(data, default=1)
    assert count == 2
    assert error is None


def test_get_pdf_page_count_with_error_returns_default_for_invalid_bytes():
    count, error = get_pdf_page_count_with_error(b"not a pdf", default=1)
    assert count == 1
    assert error


def test_get_pdf_page_count_returns_int():
    assert get_pdf_page_count(_make_pdf_bytes(1), default=1) == 1
