"""文档解析器工厂"""

import logging
from typing import Any

from apps.core.services.document_parse_provider_service import ParseProviderService
from apps.document_parsing.protocols.document_parser_protocol import IDocumentParserProtocol

logger = logging.getLogger(__name__)


class ParserFactory:
    """文档解析器工厂

    根据配置或参数创建对应的解析器后端。

    新增后端只需在 _BACKEND_REGISTRY 注册一行，无需改 create_parser 逻辑：
        _BACKEND_REGISTRY["xxx"] = "apps.document_parsing.services.backends.xxx_backend.XxxBackend"
    """

    # 后端注册表：backend name → 后端类路径（延迟 import，避免循环依赖）
    # 每个后端类必须支持 timeout 关键字参数（云端）或 **kwargs（本地）
    _BACKEND_REGISTRY: dict[str, str] = {
        "mineru": "apps.document_parsing.services.backends.mineru_backend.MineruBackend",
        "textin": "apps.document_parsing.services.backends.textin_backend.TextinBackend",
        "local": "apps.document_parsing.services.backends.local_backend.LocalBackend",
    }

    @staticmethod
    def create_parser(
        backend: str = "auto",
        **kwargs: Any,
    ) -> IDocumentParserProtocol:
        """创建解析器

        Args:
            backend: 后端类型
                - "mineru": MinerU API（云端）
                - "textin": TextinParse API（云端，xparse-client SDK）
                - "local": 本地 PyMuPDF + OCR
                - "auto": 根据「解析平台」管理页按优先级自动选择
            **kwargs: 传递给后端的参数（如 timeout、provider）

        Returns:
            IDocumentParserProtocol 解析器实例
        """
        if backend in (None, "", "auto"):
            backend = ParserFactory._resolve_auto_backend()

        class_path = ParserFactory._BACKEND_REGISTRY.get(backend)
        if class_path is None:
            raise ValueError(f"未知的后端类型: {backend}")

        backend_cls = ParserFactory._load_backend_class(class_path)
        return ParserFactory._instantiate(backend_cls, **kwargs)

    @staticmethod
    def _resolve_auto_backend() -> str:
        """auto 模式：选择优先级最高的启用解析平台；未配置任何平台时回退 local。

        DocumentParseProvider.provider_type 与 _BACKEND_REGISTRY 的键一致
        （textin / mineru），无需额外映射。
        """
        providers = ParseProviderService.get_providers()
        if not providers:
            logger.info("未配置任何解析平台，auto 回退到 local")
            return "local"
        providers = sorted(providers, key=lambda p: (p.priority, p.pk))
        best = str(providers[0].provider_type)
        logger.info("auto 选择解析平台: %s (%s)", providers[0].name, best)
        return best

    @staticmethod
    def _load_backend_class(class_path: str) -> type:
        """从完整路径加载后端类（延迟 import）"""
        module_path, class_name = class_path.rsplit(".", 1)
        import importlib

        module = importlib.import_module(module_path)
        backend_cls: type = getattr(module, class_name)
        return backend_cls

    @staticmethod
    def _instantiate(backend_cls: type, **kwargs: Any) -> IDocumentParserProtocol:
        """实例化后端，透传所有 kwargs（timeout、显式凭证、provider 等）。"""
        return backend_cls(**kwargs)  # type: ignore[call-arg]
