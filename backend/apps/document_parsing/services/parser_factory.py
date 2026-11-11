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
        # Office（docx/xlsx/xls）：本地读 OOXML，毫秒级，无需云服务/DS
        "office": "apps.document_parsing.services.backends.office_backend.OfficeBackend",
    }


# ↓↓ 由 ParserFactory 下沉的模块级纯函数（四层架构静态方法棘轮）
def _load_backend_class(class_path: str) -> type:
    """从完整路径加载后端类（延迟 import）"""
    module_path, class_name = class_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    backend_cls: type = getattr(module, class_name)
    return backend_cls


# ↓↓ 由 ParserFactory 下沉的模块级纯函数（四层架构静态方法棘轮）
def _instantiate(backend_cls: type, **kwargs: Any) -> IDocumentParserProtocol:
    """实例化后端，透传所有 kwargs（timeout、显式凭证、provider 等）。"""
    return backend_cls(**kwargs)  # type: ignore[no-any-return]


# ↓↓ 由 ParserFactory 下沉的模块级纯函数（四层架构静态方法棘轮）
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
        backend = _resolve_auto_backend()

    class_path = ParserFactory._BACKEND_REGISTRY.get(backend)
    if class_path is None:
        raise ValueError(f"未知的后端类型: {backend}")

    backend_cls = _load_backend_class(class_path)
    return _instantiate(backend_cls, **kwargs)


#: 可显式锁定的云端平台（与 _BACKEND_REGISTRY 的键一致）
CLOUD_BACKEND_CHOICES: tuple[str, ...] = ("mineru", "textin")

#: 自动模式：按优先级挑，失败可切下一个
AUTO_BACKEND = "auto"


# ↓↓ 由 ParserFactory 下沉的模块级纯函数（四层架构静态方法棘轮）
def resolve_cloud_backends(cloud_backend: str | None = None) -> list[str]:
    """给出**按尝试顺序**排列的云端平台列表。

    这是「容灾」与「锁定」两种意图的统一入口：

    · ``auto``（默认）：按优先级排序的全部可用平台。调用方从第一个开始试，
      失败再试下一个 —— 这就是容灾。
    · ``mineru`` / ``textin``（锁定）：**只返回这一个**。锁定意味着可预期：
      若允许它偷偷降级到另一个平台，用户拿它做的比对/复核就失去意义，
      而且计费也会落到他没选的平台上。所以锁定时不提供备选。
    · 调用方传入的平台若未配置，返回空表 —— 让上层明确报"该平台不可用"，
      而不是悄悄换成别的（同样是为了可预期）。

    Args:
        cloud_backend: ``auto`` / ``mineru`` / ``textin``；None 视同 auto。

    Returns:
        平台类型名列表（按尝试顺序）；空表表示没有可用平台。
    """
    want = str(cloud_backend or AUTO_BACKEND).strip().lower()

    providers = ParseProviderService.get_providers()
    if not providers:
        return []
    ordered = sorted(providers, key=lambda p: (p.priority, p.pk))

    if want and want != AUTO_BACKEND:
        if want not in CLOUD_BACKEND_CHOICES:
            # 未知值：按 auto 处理而不是静默失败——调用方传脏值时仍能出结果
            logger.warning("未知的 cloud_backend=%r，按 auto 处理", cloud_backend)
            want = AUTO_BACKEND
        else:
            picked = [str(p.provider_type) for p in ordered if str(p.provider_type) == want]
            if picked:
                logger.info("锁定解析平台: %s", want)
            else:
                logger.warning("指定的解析平台未启用: %s", want)
            return picked

    # auto：全部已启用平台，按优先级；去重（同类型配多个平台时只留最先的）
    seen: set[str] = set()
    out: list[str] = []
    for provider in ordered:
        pt = str(provider.provider_type)
        if pt in seen:
            continue
        seen.add(pt)
        out.append(pt)
    logger.info("auto 解析平台尝试顺序: %s", " -> ".join(out) or "(无)")
    return out


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
