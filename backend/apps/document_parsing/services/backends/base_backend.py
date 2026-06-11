"""文档解析后端基类"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult


class BaseDocumentParser(ABC):
    """文档解析后端抽象基类

    所有解析器后端都应继承此类。
    """

    @abstractmethod
    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """解析文档"""
        ...

    @abstractmethod
    def extract_text(
        self,
        file_path: str,
        max_length: Optional[int] = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """提取纯文本"""
        ...

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式"""
        ...
