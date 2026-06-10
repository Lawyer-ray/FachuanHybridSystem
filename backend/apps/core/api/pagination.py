"""集中式分页工具

提供通用分页 Schema 和 queryset 分页辅助函数，
避免各 app 重复实现分页逻辑。
"""

from __future__ import annotations

import math
from typing import Any

from django.db.models import QuerySet
from ninja import Schema


class PageParams(Schema):
    """通用分页请求参数"""

    page: int = 1
    page_size: int = 20


class PaginatedOut(Schema):
    """通用分页响应 Schema

    使用方式:
        class MyListOut(PaginatedOut):
            items: list[MyItemOut]

        或在 API 端点中:
            @router.get("/list", response=MyListOut)
            def list_items(request, page: int = 1, page_size: int = 20):  # pragma: no cover
                result = paginate_queryset(qs, page=page, page_size=page_size)
                return result
    """

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate_queryset(
    qs: QuerySet,
    *,
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
) -> dict[str, Any]:
    """对 queryset 执行分页，返回分页元数据和数据切片。

    Args:
        qs: 要分页的 QuerySet
        page: 页码（从 1 开始，小于 1 时修正为 1）
        page_size: 每页条数（限制在 1 ~ max_page_size）
        max_page_size: 最大每页条数

    Returns:
        dict 包含 items, total, page, page_size, total_pages
    """
    page = max(1, page)
    page_size = max(1, min(page_size, max_page_size))

    total = qs.count()
    total_pages = max(1, math.ceil(total / page_size))
    offset = (page - 1) * page_size

    items = list(qs[offset : offset + page_size])

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
