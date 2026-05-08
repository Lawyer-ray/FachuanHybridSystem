"""模板上下文处理器。"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest


def tool_favorites(request: HttpRequest) -> dict[str, Any]:
    """向所有 admin 模板注入用户工具收藏 URL 列表（JSON）。"""
    # 仅对已登录用户注入
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"fav_urls_json": "[]"}

    from apps.core.models import ToolFavorite

    urls = list(
        ToolFavorite.objects.filter(user=request.user).values_list("tool_url", flat=True)
    )
    return {"fav_urls_json": json.dumps(urls)}
