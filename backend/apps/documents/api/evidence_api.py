"""
证据清单 API

提供证据清单的排序等 API 端点.

Requirements: 4.2, 4.3, 12.1
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

router = Router(tags=["证据清单"], auth=JWTOrSessionAuth())


def _get_evidence_service() -> Any:
    """工厂函数获取证据服务"""
    from apps.evidence.services.wiring import get_evidence_service

    return get_evidence_service()


class ReorderItemsRequest(Schema):
    """重新排序请求"""

    item_ids: list[int]


class ReorderItemsResponse(Schema):
    """重新排序响应"""

    success: bool
    message: str = ""


@router.post(
    "/evidence-lists/{list_id}/reorder",
    response=ReorderItemsResponse,
    summary="重新排序证据明细",
)
def reorder_evidence_items(request: HttpRequest, list_id: int, data: ReorderItemsRequest) -> Any:
    """
    重新排序证据明细

    Args:
        list_id: 证据清单 ID
        data: 包含新顺序的明细 ID 列表

    Returns:
        操作结果

    Requirements: 4.2, 4.3
    """
    service = _get_evidence_service()
    service.reorder_items(list_id, data.item_ids)
    return ReorderItemsResponse(success=True, message="排序成功")
