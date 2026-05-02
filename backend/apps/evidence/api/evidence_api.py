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

router = Router(tags=["证据管理"], auth=JWTOrSessionAuth())


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


# --- AI 辅助 ---


class AIPurposeRequest(Schema):
    """AI 证明目的建议请求"""

    cause_of_action: str = ""
    evidence_type: str = ""
    evidence_name: str = ""
    content_summary: str = ""


class AIPurposeResponse(Schema):
    """AI 证明目的建议响应"""

    suggestions: list[str]


class AICrossExamRequest(Schema):
    """AI 质证意见请求"""

    cause_of_action: str = ""
    our_claim: str = ""
    evidence_name: str = ""
    content_summary: str = ""


class AICrossExamResponse(Schema):
    """AI 质证意见响应"""

    cross_examination: dict[str, Any]


def _get_ai_service() -> Any:
    from apps.evidence.services.ai.evidence_ai_service import EvidenceAIService

    return EvidenceAIService()


@router.post(
    "/ai/suggest-purpose",
    response=AIPurposeResponse,
    summary="AI 证明目的建议",
)
def ai_suggest_purpose(request: HttpRequest, data: AIPurposeRequest) -> Any:
    svc = _get_ai_service()
    suggestions = svc.suggest_purpose(
        cause_of_action=data.cause_of_action,
        evidence_type=data.evidence_type,
        evidence_name=data.evidence_name,
        content_summary=data.content_summary,
    )
    return AIPurposeResponse(suggestions=suggestions)


@router.post(
    "/ai/generate-cross-examination",
    response=AICrossExamResponse,
    summary="AI 质证意见生成",
)
def ai_generate_cross_examination(request: HttpRequest, data: AICrossExamRequest) -> Any:
    svc = _get_ai_service()
    result = svc.generate_cross_examination(
        cause_of_action=data.cause_of_action,
        our_claim=data.our_claim,
        evidence_name=data.evidence_name,
        content_summary=data.content_summary,
    )
    return AICrossExamResponse(cross_examination=result)
