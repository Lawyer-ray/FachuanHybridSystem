"""文档解析异常类测试"""

import pytest

from apps.core.exceptions import ExternalServiceError
from apps.document_parsing.exceptions import (
    DocumentParsingError,
    FileFormatNotSupportedError,
    MineruAPIError,
    ParsingTimeoutError,
    TextinAPIError,
)


class TestExceptionHierarchy:
    """异常继承链测试"""

    def test_document_parsing_error_is_external_service_error(self) -> None:
        assert issubclass(DocumentParsingError, ExternalServiceError)

    def test_mineru_api_error_is_document_parsing_error(self) -> None:
        assert issubclass(MineruAPIError, DocumentParsingError)

    def test_textin_api_error_is_document_parsing_error(self) -> None:
        assert issubclass(TextinAPIError, DocumentParsingError)

    def test_file_format_not_supported_is_document_parsing_error(self) -> None:
        assert issubclass(FileFormatNotSupportedError, DocumentParsingError)

    def test_parsing_timeout_is_document_parsing_error(self) -> None:
        assert issubclass(ParsingTimeoutError, DocumentParsingError)


class TestMineruAPIError:
    def test_message(self) -> None:
        err = MineruAPIError("something broke")
        assert "something broke" in str(err)

    def test_catch_as_document_parsing_error(self) -> None:
        with pytest.raises(DocumentParsingError):
            raise MineruAPIError("oops")

    def test_catch_as_external_service_error(self) -> None:
        with pytest.raises(ExternalServiceError):
            raise MineruAPIError("oops")


class TestOtherExceptions:
    def test_file_format_error_message(self) -> None:
        err = FileFormatNotSupportedError("xyz not supported")
        assert "xyz" in str(err)

    def test_timeout_error_message(self) -> None:
        err = ParsingTimeoutError("timed out after 300s")
        assert "300" in str(err)


class TestTextinAPIError:
    def test_message(self) -> None:
        err = TextinAPIError("textin broke")
        assert "textin broke" in str(err)

    def test_is_document_parsing_error(self) -> None:
        assert issubclass(TextinAPIError, DocumentParsingError)

    def test_catch_as_document_parsing_error(self) -> None:
        with pytest.raises(DocumentParsingError):
            raise TextinAPIError("oops")

    def test_catch_as_external_service_error(self) -> None:
        with pytest.raises(ExternalServiceError):
            raise TextinAPIError("oops")
