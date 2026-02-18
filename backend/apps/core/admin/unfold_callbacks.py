"""
Django Unfold 回调函数

提供 Unfold Admin 主题所需的回调函数。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def environment_callback(request: HttpRequest) -> tuple[str, str] | None:
    """
    返回当前环境标识，用于 Unfold 顶部显示环境标签。

    Returns:
        tuple: (环境名称, 颜色类型) 或 None
    """
    if settings.DEBUG:
        return ("开发环境", "warning")
    return ("生产环境", "success")
