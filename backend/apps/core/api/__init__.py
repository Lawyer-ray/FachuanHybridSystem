"""
Core API 模块

提供系统配置的 API 接口.
"""

from collections import defaultdict
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.repositories.system_config_repository import SystemConfigRepository
from apps.core.security.auth import JWTOrSessionAuth

router = Router(tags=["系统配置"], auth=JWTOrSessionAuth())

_repository = SystemConfigRepository()


# ─── Schemas ────────────────────────────────────────────────────────────────────


class SystemConfigItemOut(Schema):
    key: str
    value: str
    category: str
    description: str
    is_secret: bool
    is_active: bool


class SystemConfigGroupOut(Schema):
    category: str
    items: list[SystemConfigItemOut]


class SystemConfigListOut(Schema):
    groups: list[SystemConfigGroupOut]


class SystemConfigUpdateIn(Schema):
    category: str
    updates: dict[str, str]


class SystemConfigUpdateOut(Schema):
    success: bool
    updated_count: int


# ─── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/system-configs", response=SystemConfigListOut)
def list_system_configs(request: HttpRequest) -> dict[str, Any]:
    """返回所有启用的系统配置，按 category 分组。secret 字段的 value 返回 '******'。"""
    configs = _repository.get_all_active()
    grouped: dict[str, list[SystemConfigItemOut]] = defaultdict(list)
    for cfg in configs:
        display_value = "******" if cfg.is_secret else cfg.value
        grouped[cfg.category].append(
            SystemConfigItemOut(
                key=cfg.key,
                value=display_value,
                category=cfg.category,
                description=cfg.description,
                is_secret=cfg.is_secret,
                is_active=cfg.is_active,
            )
        )
    groups = [
        SystemConfigGroupOut(category=cat, items=items)
        for cat, items in grouped.items()
    ]
    return {"groups": groups}


@router.put("/system-configs", response=SystemConfigUpdateOut)
def update_system_configs(request: HttpRequest, payload: SystemConfigUpdateIn) -> dict[str, bool | int]:
    """批量更新系统配置项。已有的 key 更新值，不存在的 key 自动创建。"""
    from apps.core.services.system_config_service import SystemConfigService

    service = SystemConfigService()
    updated = 0
    for key, value in payload.updates.items():
        existing = _repository.get_by_key(key)
        if existing is not None:
            service.set_value(
                key=key,
                value=value,
                category=existing.category,
                description=existing.description,
                is_secret=existing.is_secret,
            )
        else:
            # 不存在的 key：自动创建，默认非敏感
            service.set_value(
                key=key,
                value=value,
                category=payload.category,
                description="",
                is_secret=False,
            )
        updated += 1
    return {"success": True, "updated_count": updated}
