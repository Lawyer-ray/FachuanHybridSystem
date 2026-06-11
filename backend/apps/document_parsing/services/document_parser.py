"""统一的文档解析服务"""

import logging
from typing import Any, List, Optional

from apps.document_parsing.protocols.document_parser_protocol import (
    IDocumentParserProtocol,
    ParsedDocument,
    TextExtractionResult,
)
from apps.document_parsing.services.parser_factory import ParserFactory

logger = logging.getLogger(__name__)


class DocumentParserService:
    """文档解析服务

    提供统一的文档解析接口，支持多后端切换。
    """

    def __init__(self, backend: str = "auto", **kwargs: Any):
        """初始化文档解析服务

        Args:
            backend: 后端类型（mineru、local、paddleocr、auto）
            **kwargs: 传递给后端的参数
        """
        self._backend_name = backend
        self._kwargs = kwargs
        self._parser: IDocumentParserProtocol | None = None

    def _get_parser(self) -> IDocumentParserProtocol:
        """获取解析器实例（延迟加载）"""
        if self._parser is None:
            self._parser = ParserFactory.create_parser(
                self._backend_name,
                **self._kwargs,
            )
        return self._parser

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """解析文档

        Args:
            file_path: 文件路径
            file_type: 文件类型
            extract_tables: 是否提取表格
            extract_images: 是否提取图片
            return_markdown: 是否返回 Markdown

        Returns:
            ParsedDocument 解析结果
        """
        parser = self._get_parser()
        return parser.parse_document(
            file_path=file_path,
            file_type=file_type,
            extract_tables=extract_tables,
            extract_images=extract_images,
            return_markdown=return_markdown,
            **kwargs,
        )

    def extract_text(
        self,
        file_path: str,
        max_length: int | None = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """提取文档纯文本

        Args:
            file_path: 文件路径
            max_length: 最大文本长度

        Returns:
            TextExtractionResult 提取结果
        """
        parser = self._get_parser()
        return parser.extract_text(
            file_path=file_path,
            max_length=max_length,
            **kwargs,
        )

    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式"""
        parser = self._get_parser()
        return parser.get_supported_formats()


def get_document_parser(
    backend: str = "auto",
    **kwargs: Any,
) -> DocumentParserService:
    """获取文档解析服务的便捷函数

    Args:
        backend: 后端类型
        **kwargs: 传递给后端的参数

    Returns:
        DocumentParserService 实例
    """
    return DocumentParserService(backend=backend, **kwargs)
