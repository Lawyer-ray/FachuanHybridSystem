"""
可插拔插件目录

每个插件是一个独立的 Python 包，可以被动态检测和加载。
插件目录会被添加到 .gitignore，用户需要手动安装。
"""

from typing import Literal

__all__ = ["has_court_filing_api_plugin", "get_plugin_status"]


def has_court_filing_api_plugin() -> bool:
    """
    检测 HTTP 链路立案插件是否已安装。

    Returns:
        bool: 插件存在返回 True，否则返回 False
    """
    try:
        from plugins.court_filing_http import api_service  # noqa: F401

        return True
    except ImportError:
        return False


def get_plugin_status() -> dict[str, Literal["installed", "not_installed"]]:
    """
    获取所有插件的状态。

    Returns:
        dict: 插件名称 -> 状态映射
    """
    return {
        "court_filing_http": "installed" if has_court_filing_api_plugin() else "not_installed",
    }
