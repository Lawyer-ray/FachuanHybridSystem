"""文档解析 Protocol 接口"""

from apps.document_parsing.protocols.document_parser_protocol import (
    IDocumentParserProtocol,
    ParsedDocument,
    TextExtractionResult,
)

__all__ = [
    "IDocumentParserProtocol",
    "ParsedDocument",
    "TextExtractionResult",
]
