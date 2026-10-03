"""
占位符服务包

提供可插拔的占位符生成服务架构.
"""

import importlib
import pkgutil

from .base import BasePlaceholderService
from .context_builder import EnhancedContextBuilder
from .registry import PlaceholderRegistry


def _auto_import_all_services() -> None:
    package_name = __name__
    # 按模块名排序后再注册,保证注册顺序不依赖文件系统目录枚举顺序
    module_infos = sorted(pkgutil.walk_packages(__path__, package_name + "."), key=lambda info: info.name)
    for module_info in module_infos:
        module_name = module_info.name
        if (
            module_name.endswith(".base")
            or module_name.endswith(".registry")
            or module_name.endswith(".context_builder")
        ):
            continue
        importlib.import_module(module_name)


_auto_import_all_services()

__all__ = [
    "BasePlaceholderService",
    "EnhancedContextBuilder",
    "PlaceholderRegistry",
]
