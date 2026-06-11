"""DocumentParserService 门面测试"""

from unittest.mock import MagicMock, patch

from apps.document_parsing.protocols.document_parser_protocol import (
    ParsedDocument,
    TextExtractionResult,
)
from apps.document_parsing.services.document_parser import (
    DocumentParserService,
    get_document_parser,
)


def _mock_parser() -> MagicMock:
    parser = MagicMock()
    parser.parse_document.return_value = ParsedDocument(
        text="parsed body",
        markdown="# md",
        parse_method="test",
    )
    parser.extract_text.return_value = TextExtractionResult(
        text="extracted",
        success=True,
        method="test",
    )
    parser.get_supported_formats.return_value = ["pdf", "docx"]
    return parser


class TestDocumentParserService:
    def test_lazy_loading(self) -> None:
        """parser 只在首次调用时创建"""
        mock_parser = _mock_parser()
        with patch(
            "apps.document_parsing.services.document_parser.ParserFactory.create_parser",
            return_value=mock_parser,
        ) as mock_factory:
            svc = DocumentParserService(backend="local")
            # 未调用前不创建 parser
            mock_factory.assert_not_called()
            # 首次调用创建
            svc.parse_document(file_path="/tmp/test.pdf")
            mock_factory.assert_called_once_with("local")
            # 第二次调用复用
            svc.parse_document(file_path="/tmp/test2.pdf")
            assert mock_factory.call_count == 1

    def test_parse_document_delegates(self) -> None:
        mock_parser = _mock_parser()
        with patch(
            "apps.document_parsing.services.document_parser.ParserFactory.create_parser",
            return_value=mock_parser,
        ):
            svc = DocumentParserService()
            result = svc.parse_document(
                file_path="/tmp/test.pdf",
                file_type="pdf",
                extract_tables=False,
                extract_images=True,
                return_markdown=True,
            )
        mock_parser.parse_document.assert_called_once_with(
            file_path="/tmp/test.pdf",
            file_type="pdf",
            extract_tables=False,
            extract_images=True,
            return_markdown=True,
        )
        assert result.text == "parsed body"

    def test_extract_text_delegates(self) -> None:
        mock_parser = _mock_parser()
        with patch(
            "apps.document_parsing.services.document_parser.ParserFactory.create_parser",
            return_value=mock_parser,
        ):
            svc = DocumentParserService()
            result = svc.extract_text(file_path="/tmp/test.pdf", max_length=100)
        mock_parser.extract_text.assert_called_once_with(
            file_path="/tmp/test.pdf",
            max_length=100,
        )
        assert result.text == "extracted"

    def test_get_supported_formats_delegates(self) -> None:
        mock_parser = _mock_parser()
        with patch(
            "apps.document_parsing.services.document_parser.ParserFactory.create_parser",
            return_value=mock_parser,
        ):
            svc = DocumentParserService()
            fmts = svc.get_supported_formats()
        assert fmts == ["pdf", "docx"]

    def test_kwargs_passed_to_factory(self) -> None:
        mock_parser = _mock_parser()
        with patch(
            "apps.document_parsing.services.document_parser.ParserFactory.create_parser",
            return_value=mock_parser,
        ) as mock_factory:
            svc = DocumentParserService(backend="mineru", timeout=60)
            svc.get_supported_formats()
        mock_factory.assert_called_once_with("mineru", timeout=60)


class TestGetDocumentParser:
    def test_returns_service_instance(self) -> None:
        svc = get_document_parser(backend="local")
        assert isinstance(svc, DocumentParserService)

    def test_default_backend(self) -> None:
        svc = get_document_parser()
        assert svc._backend_name == "auto"
