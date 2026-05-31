"""归档文书占位符覆盖值 CRUD 服务。"""

from __future__ import annotations

from typing import Any

from apps.contracts.models.archive_override import ArchivePlaceholderOverride

def get_override(contract_id: int, template_subtype: str) -> ArchivePlaceholderOverride | None:
    """获取归档占位符覆盖值，不存在返回 None。"""
    return ArchivePlaceholderOverride.objects.filter(
        contract_id=contract_id,
        template_subtype=template_subtype,
    ).first()

def save_override(
    contract_id: int, template_subtype: str, overrides: dict[str, str]
) -> tuple[ArchivePlaceholderOverride, bool]:
    """保存（创建或更新）归档占位符覆盖值。"""
    return ArchivePlaceholderOverride.objects.update_or_create(
        contract_id=contract_id,
        template_subtype=template_subtype,
        defaults={"overrides": overrides},
    )

def delete_override(contract_id: int, template_subtype: str) -> int:
    """删除归档占位符覆盖值，返回删除数量。"""
    deleted_count, _ = ArchivePlaceholderOverride.objects.filter(
        contract_id=contract_id,
        template_subtype=template_subtype,
    ).delete()
    return deleted_count
