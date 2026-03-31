"""
存储类重导出

从 apps.core.storage 导入并重导出,保持向后兼容性.
"""

from apps.core.filesystem.storage import KeepOriginalNameStorage

__all__: list[str] = ["KeepOriginalNameStorage"]
