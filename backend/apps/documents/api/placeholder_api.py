"""
替换词 API

提供替换词的 CRUD 接口和总览接口.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, datetime
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth
from apps.documents.schemas import PlaceholderIn, PlaceholderOut, PlaceholderPreviewOut, PlaceholderUpdate
from apps.documents.services.placeholders import EnhancedContextBuilder
from apps.documents.services.placeholders.placeholder_service import PlaceholderService

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


def _get_placeholder_service() -> PlaceholderService:
    """工厂函数:创建 PlaceholderService 实例"""
    return PlaceholderService()


def _safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(v) for v in value]
    return str(value)


@router.get("/placeholders", response=list[PlaceholderOut])
async def list_placeholders(request: Any, is_active: bool | None = None) -> Any:  # pragma: no cover
    """
    获取替换词列表

    Args:
        is_active: 启用状态过滤
    """
    service = _get_placeholder_service()

    def _do() -> Any:
        return service.list_placeholders(is_active=is_active)

    return await sync_to_async(_do)()


@router.get("/placeholders/{placeholder_id}", response=PlaceholderOut)
async def get_placeholder(request: Any, placeholder_id: int) -> Any:  # pragma: no cover
    """获取替换词详情"""
    service = _get_placeholder_service()

    def _do() -> Any:
        return service.get_placeholder_by_id(placeholder_id)

    return await sync_to_async(_do)()


@router.get("/placeholders/by-key/{key}", response=PlaceholderOut)
async def get_placeholder_by_key(request: Any, key: str) -> Any:  # pragma: no cover
    """根据键获取替换词"""
    service = _get_placeholder_service()

    def _do() -> Any:
        return service.get_placeholder_by_key(key)

    return await sync_to_async(_do)()


@router.post("/placeholders", response=PlaceholderOut)
async def create_placeholder(request: Any, payload: PlaceholderIn) -> Any:  # pragma: no cover
    """创建替换词"""
    service = _get_placeholder_service()

    def _do() -> Any:
        return service.create_placeholder(
            key=payload.key,
            display_name=payload.display_name,
            example_value=payload.example_value,
            description=payload.description,
            is_active=payload.is_active,
        )

    return await sync_to_async(_do)()


@router.put("/placeholders/{placeholder_id}", response=PlaceholderOut)
async def update_placeholder(request: Any, placeholder_id: int, payload: PlaceholderUpdate) -> Any:  # pragma: no cover
    """更新替换词"""
    service = _get_placeholder_service()

    def _do() -> Any:
        return service.update_placeholder(
            placeholder_id=placeholder_id,
            key=payload.key,
            display_name=payload.display_name,
            example_value=payload.example_value,
            description=payload.description,
            is_active=payload.is_active,
        )

    return await sync_to_async(_do)()


@router.delete("/placeholders/{placeholder_id}", response=dict[str, Any])
async def delete_placeholder(request: Any, placeholder_id: int) -> Any:  # pragma: no cover
    """删除替换词(软删除)"""
    service = _get_placeholder_service()
    await sync_to_async(service.delete_placeholder)(placeholder_id)
    return {"success": True, "message": "替换词已删除"}


@router.get("/placeholders/preview/{contract_id}", response=PlaceholderPreviewOut)
async def preview_placeholders(request: Any, contract_id: int) -> Any:  # pragma: no cover
    builder = EnhancedContextBuilder()
    context = await sync_to_async(builder.build_contract_context)(contract_id)

    keys = request.GET.get("keys")
    required_keys: list[str] | None = None
    if keys:
        required_keys = [k.strip() for k in keys.split(",") if k.strip()]

    if required_keys is None:
        values = {k: _safe_value(v) for k, v in context.items()}
        missing_keys: list[str] = []
    else:
        values = {k: _safe_value(context.get(k)) for k in required_keys if k in context}
        missing_keys = [k for k in required_keys if k not in context]

    return {
        "contract_id": contract_id,
        "values": values,
        "missing_keys": missing_keys,
    }


# ============================================================
# 替换词总览
# ============================================================


class PlaceholderDefinitionOut(Schema):
    """单个替换词定义"""

    key: str
    source: str = ""
    category: str = ""
    display_name: str = ""
    description: str = ""
    example_value: str = ""


class PlaceholderCategoryGroupOut(Schema):
    """按分类分组的替换词"""

    category: str
    label: str
    count: int
    items: list[PlaceholderDefinitionOut]


class PlaceholderOverviewOut(Schema):
    """替换词总览响应"""

    total: int
    groups: list[PlaceholderCategoryGroupOut]


CATEGORY_LABELS: dict[str, str] = {
    "basic": "基础信息",
    "party": "当事人信息",
    "contract": "合同信息",
    "lawyer": "律师信息",
    "litigation": "诉讼文书",
    "supplementary": "补充协议",
    "supplementary_agreement": "补充协议",
    "authorization_materials": "授权材料",
    "authorization_material": "授权材料",
    "case": "案件信息",
    "evidence": "证据清单",
    "archive": "归档",
    "generated": "代码扫描",
    "general": "通用",
}


def _get_catalog_service() -> Any:
    from apps.documents.services.code_placeholders.catalog_service import CodePlaceholderCatalogService

    return CodePlaceholderCatalogService()


@router.get("/placeholders/overview", response=PlaceholderOverviewOut)
async def placeholder_overview(request: Any, q: str | None = None) -> Any:  # pragma: no cover
    """
    替换词总览

    返回系统支持的所有替换词，按分类分组。
    支持 q 参数搜索（匹配 key / display_name / description / source）。
    """

    def _do() -> Any:
        catalog = _get_catalog_service()
        definitions = catalog.list_definitions()

        if q:
            q_lower = q.lower()
            definitions = [
                d
                for d in definitions
                if q_lower in d.key.lower()
                or q_lower in (d.display_name or "").lower()
                or q_lower in (d.description or "").lower()
                or q_lower in (d.source or "").lower()
            ]

        grouped: OrderedDict[str, list[Any]] = OrderedDict()
        for d in definitions:
            grouped.setdefault(d.category or "general", []).append(d)

        groups: list[dict[str, Any]] = []
        for cat, items in grouped.items():
            groups.append(
                {
                    "category": cat,
                    "label": CATEGORY_LABELS.get(cat, cat),
                    "count": len(items),
                    "items": [
                        {
                            "key": d.key,
                            "source": d.source or "",
                            "category": d.category or "",
                            "display_name": d.display_name or "",
                            "description": d.description or "",
                            "example_value": d.example_value or "",
                        }
                        for d in items
                    ],
                }
            )

        return {"total": len(definitions), "groups": groups}

    return await sync_to_async(_do)()
