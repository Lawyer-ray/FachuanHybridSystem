"""Ninja Schema 测试"""

from apps.document_parsing.schemas.parsing_schemas import (
    ExtractTextRequest,
    ExtractTextResponse,
    ParseDocumentRequest,
    ParseDocumentResponse,
)


class TestParseDocumentRequest:
    def test_default_values(self) -> None:
        req = ParseDocumentRequest()
        assert req.backend == "auto"
        assert req.extract_tables is True
        assert req.extract_images is False
        assert req.return_markdown is True

    def test_custom_values(self) -> None:
        req = ParseDocumentRequest(
            backend="local",
            extract_tables=False,
            extract_images=True,
            return_markdown=False,
        )
        assert req.backend == "local"
        assert req.extract_tables is False
        assert req.extract_images is True
        assert req.return_markdown is False


class TestExtractTextRequest:
    def test_default_values(self) -> None:
        req = ExtractTextRequest()
        assert req.backend == "auto"
        assert req.max_length is None

    def test_custom_values(self) -> None:
        req = ExtractTextRequest(backend="mineru", max_length=500)
        assert req.backend == "mineru"
        assert req.max_length == 500


class TestParseDocumentResponse:
    def test_success_response(self) -> None:
        resp = ParseDocumentResponse(
            success=True,
            text="body",
            markdown="# md",
            metadata={"k": "v"},
            parse_method="mineru",
        )
        assert resp.success is True
        assert resp.text == "body"
        assert resp.error is None

    def test_error_response(self) -> None:
        resp = ParseDocumentResponse(success=False, error="something broke")
        assert resp.success is False
        assert resp.error == "something broke"
        assert resp.text is None


class TestExtractTextResponse:
    def test_success_response(self) -> None:
        resp = ExtractTextResponse(
            success=True,
            text="extracted",
            method="pymupdf",
            metadata={"pages": 2},
        )
        assert resp.success is True
        assert resp.text == "extracted"

    def test_error_response(self) -> None:
        resp = ExtractTextResponse(success=False, text="", error="fail")
        assert resp.success is False
        assert resp.error == "fail"
