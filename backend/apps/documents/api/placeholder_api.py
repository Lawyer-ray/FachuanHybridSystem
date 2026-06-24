"""
替换词 API

提供替换词的 CRUD 接口.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

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
