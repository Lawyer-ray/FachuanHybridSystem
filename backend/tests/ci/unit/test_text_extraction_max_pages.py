from __future__ import annotations

from apps.automation.services.document import document_processing
from apps.document_recognition.services.text_extraction_service import TextExtractionService


def test_text_extraction_service_prefers_constructor_max_pages(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    called: dict[str, int | None] = {}

    def fake_extract_pdf_text(file_path: str, limit: int | None = None, max_pages: int | None = None) -> str:
        called["max_pages"] = max_pages
        return "合同正文"

    monkeypatch.setattr(document_processing, "extract_pdf_text", fake_extract_pdf_text)

    service = TextExtractionService(text_limit=500, max_pages=3)
    result = service.extract_text(str(pdf_path))

    assert result.success is True
    assert result.extraction_method == "pdf_direct"
    assert called.get("max_pages") == 3


def test_text_extraction_service_extract_text_can_override_max_pages(tmp_path, monkeypatch):
    pdf_path = tmp_path / "override.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    called: dict[str, int | None] = {}

    def fake_extract_pdf_text(file_path: str, limit: int | None = None, max_pages: int | None = None) -> str:
        called["max_pages"] = max_pages
        return "合同正文"

    monkeypatch.setattr(document_processing, "extract_pdf_text", fake_extract_pdf_text)

    service = TextExtractionService(text_limit=500, max_pages=3)
    service.extract_text(str(pdf_path), max_pages=1)

    assert called.get("max_pages") == 1


def test_document_processing_extract_pdf_text_respects_max_pages(monkeypatch):
    loaded_pages: list[int] = []

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_text(self) -> str:
            return self._text

    class FakeDoc:
        page_count = 5

        def __enter__(self) -> "FakeDoc":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def load_page(self, index: int) -> FakePage:
            loaded_pages.append(index)
            return FakePage(f"P{index}")

    monkeypatch.setattr(document_processing.fitz, "open", lambda path: FakeDoc())

    text = document_processing.extract_pdf_text("/tmp/not-used.pdf", limit=1000, max_pages=2)

    assert loaded_pages == [0, 1]
    assert text == "P0P1"
