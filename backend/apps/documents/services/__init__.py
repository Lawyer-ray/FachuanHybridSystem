"""
Documents Services 模块

包含所有文书生成相关的业务逻辑服务.
"""

import importlib
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "FolderTemplateService": ("apps.documents.services.template.folder_service", "FolderTemplateService"),
    "FolderTemplateAdminService": (
        "apps.documents.services.template.folder_template.admin_service",
        "FolderTemplateAdminService",
    ),
    "ContractGenerationService": (
        "apps.documents.services.generation.contract_generation_service",
        "ContractGenerationService",
    ),
    "GenerationService": ("apps.documents.services.generation.generation_service", "GenerationService"),
    "PlaceholderAdminService": (
        "apps.documents.services.placeholders.placeholder_admin_service",
        "PlaceholderAdminService",
    ),
    "PlaceholderService": ("apps.documents.services.placeholders.placeholder_service", "PlaceholderService"),
    "DocumentTemplateService": ("apps.documents.services.template.template_service", "DocumentTemplateService"),
}

# __all__ 由 _LAZY_EXPORTS 派生（单一事实源；静态列举会与 __getattr__ 懒加载脱节）
__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__) | set(_LAZY_EXPORTS.keys()))
