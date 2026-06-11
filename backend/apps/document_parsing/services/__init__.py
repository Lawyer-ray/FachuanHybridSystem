"""文档解析服务"""

from apps.document_parsing.services.document_parser import (
    DocumentParserService,
    get_document_parser,
)
from apps.document_parsing.services.parser_factory import ParserFactory

__all__ = [
    "DocumentParserService",
    "get_document_parser",
    "ParserFactory",
]
