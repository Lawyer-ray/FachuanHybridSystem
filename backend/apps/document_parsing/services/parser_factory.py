"""文档解析器工厂"""

import logging
from typing import Any

from apps.core.services.system_config_service import SystemConfigService
from apps.document_parsing.protocols.document_parser_protocol import IDocumentParserProtocol

logger = logging.getLogger(__name__)
_config_service = SystemConfigService()


class ParserFactory:
    """文档解析器工厂

    根据配置或参数创建对应的解析器后端。
    """

    @staticmethod
    def create_parser(
        backend: str = "auto",
        **kwargs: Any,
    ) -> IDocumentParserProtocol:
        """创建解析器

        Args:
            backend: 后端类型
                - "mineru": MinerU API（云端）
                - "local": 本地 PyMuPDF + OCR
                - "paddleocr": PaddleOCR API
                - "auto": 根据 SystemConfig 自动选择
            **kwargs: 传递给后端的参数

        Returns:
            IDocumentParserProtocol 解析器实例
        """
        if backend == "auto":
            backend = _config_service.get_value_internal("DOCUMENT_PARSING_BACKEND", "mineru")

        if backend == "mineru":
            return ParserFactory._create_mineru_backend(**kwargs)

        elif backend == "local":
            return ParserFactory._create_local_backend(**kwargs)

        elif backend == "paddleocr":
            return ParserFactory._create_paddleocr_backend(**kwargs)

        else:
            raise ValueError(f"未知的后端类型: {backend}")

    @staticmethod
    def _create_mineru_backend(**kwargs: Any) -> IDocumentParserProtocol:
        """创建 MinerU 后端

        API Key 会从 SystemConfig 自动读取，不需要传入。
        """
        from apps.document_parsing.services.backends.mineru_backend import MineruBackend

        # 只传递 timeout 参数（如果有的话）
        timeout = kwargs.get("timeout")
        if timeout:
            return MineruBackend(timeout=timeout)
        else:
            return MineruBackend()

    @staticmethod
    def _create_local_backend(**kwargs: Any) -> IDocumentParserProtocol:
        """创建本地后端（PyMuPDF + OCR）"""
        from apps.document_parsing.services.backends.local_backend import LocalBackend

        return LocalBackend(**kwargs)

    @staticmethod
    def _create_paddleocr_backend(**kwargs: Any) -> IDocumentParserProtocol:
        """创建 PaddleOCR 后端"""
        # TODO: 实现 PaddleOCR 后端
        raise NotImplementedError("PaddleOCR 后端暂未实现")
