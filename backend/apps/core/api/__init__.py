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


class SystemConfigCreateIn(Schema):
    key: str
    value: str = ""
    category: str = "general"
    description: str = ""
    is_secret: bool = False


class SystemConfigPatchIn(Schema):
    value: str | None = None
    category: str | None = None
    description: str | None = None
    is_secret: bool | None = None
    is_active: bool | None = None


class SystemConfigDeleteOut(Schema):
    success: bool


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
    groups = [SystemConfigGroupOut(category=cat, items=items) for cat, items in grouped.items()]
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


@router.post("/system-configs", response=SystemConfigItemOut)
def create_system_config(request: HttpRequest, payload: SystemConfigCreateIn) -> Any:
    """创建新的系统配置项。"""
    from apps.core.services.system_config_service import SystemConfigService

    existing = _repository.get_by_key(payload.key)
    if existing is not None:
        from ninja.errors import HttpError

        raise HttpError(409, f"配置项 '{payload.key}' 已存在")

    service = SystemConfigService()
    config = service.set_value(
        key=payload.key,
        value=payload.value,
        category=payload.category,
        description=payload.description,
        is_secret=payload.is_secret,
    )
    return SystemConfigItemOut(
        key=config.key,
        value="******" if config.is_secret else config.value,
        category=config.category,
        description=config.description,
        is_secret=config.is_secret,
        is_active=config.is_active,
    )


@router.patch("/system-configs/{key}", response=SystemConfigItemOut)
def patch_system_config(request: HttpRequest, key: str, payload: SystemConfigPatchIn) -> Any:
    """更新单个配置项的属性。"""
    from apps.core.services.system_config_service import SystemConfigService

    config = _repository.get_by_key(key)
    if config is None:
        from ninja.errors import HttpError

        raise HttpError(404, f"配置项 '{key}' 不存在")

    service = SystemConfigService()
    updated = service.update_config(
        config_id=config.id,
        value=payload.value,
        category=payload.category,
        description=payload.description,
        is_secret=payload.is_secret,
        is_active=payload.is_active,
    )
    return SystemConfigItemOut(
        key=updated.key,
        value="******" if updated.is_secret else updated.value,
        category=updated.category,
        description=updated.description,
        is_secret=updated.is_secret,
        is_active=updated.is_active,
    )


@router.delete("/system-configs/{key}", response=SystemConfigDeleteOut)
def delete_system_config(request: HttpRequest, key: str) -> Any:
    """删除指定的系统配置项。"""
    config = _repository.get_by_key(key)
    if config is None:
        from ninja.errors import HttpError

        raise HttpError(404, f"配置项 '{key}' 不存在")

    _repository.delete(config.id)
    return {"success": True}
