"""Protocol 数据类测试"""

from apps.document_parsing.protocols.document_parser_protocol import (
    ParsedDocument,
    TextExtractionResult,
)


class TestParsedDocument:
    def test_defaults(self) -> None:
        doc = ParsedDocument(text="hello")
        assert doc.text == "hello"
        assert doc.markdown is None
        assert doc.tables is None
        assert doc.metadata is None
        assert doc.images is None
        assert doc.parse_method == ""
        assert doc.layout is None

    def test_full_init(self) -> None:
        doc = ParsedDocument(
            text="body",
            markdown="# heading",
            tables=[{"rows": 1}],
            metadata={"pages": 5},
            images=["/tmp/a.png"],
            parse_method="mineru",
            layout={"blocks": []},
        )
        assert doc.text == "body"
        assert doc.markdown == "# heading"
        assert doc.tables == [{"rows": 1}]
        assert doc.metadata == {"pages": 5}
        assert doc.images == ["/tmp/a.png"]
        assert doc.parse_method == "mineru"
        assert doc.layout == {"blocks": []}


class TestTextExtractionResult:
    def test_defaults(self) -> None:
        r = TextExtractionResult(text="abc", success=True)
        assert r.text == "abc"
        assert r.success is True
        assert r.method == ""
        assert r.page_count is None
        assert r.metadata is None

    def test_full_init(self) -> None:
        r = TextExtractionResult(
            text="extracted",
            success=True,
            method="mineru",
            page_count=3,
            metadata={"key": "val"},
        )
        assert r.text == "extracted"
        assert r.method == "mineru"
        assert r.page_count == 3
        assert r.metadata == {"key": "val"}

    def test_failure_result(self) -> None:
        r = TextExtractionResult(
            text="",
            success=False,
            method="pymupdf",
            metadata={"error": "bad file"},
        )
        assert r.success is False
        assert r.text == ""
        assert r.metadata["error"] == "bad file"
