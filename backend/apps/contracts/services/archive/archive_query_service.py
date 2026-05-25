"""归档材料查询与 CRUD 服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings as django_settings

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial


def get_contract_or_none(contract_id: int) -> Contract | None:
    """获取合同，不存在返回 None。"""
    return Contract.objects.filter(pk=contract_id).first()


def get_material_or_none(material_id: int, contract_id: int) -> FinalizedMaterial | None:
    """获取归档材料，不存在返回 None。"""
    return FinalizedMaterial.objects.filter(pk=material_id, contract_id=contract_id).first()


def delete_material(material: FinalizedMaterial) -> None:
    """删除归档材料（含文件清理）。"""
    if material.file_path:
        abs_file = Path(django_settings.MEDIA_ROOT) / material.file_path
        if abs_file.exists():
            try:
                abs_file.unlink()
            except OSError:
                pass
    material.delete()


def reorder_materials(contract_id: int, orders: dict[str, list[int]]) -> None:
    """按归档清单项分组排序子项。"""
    for code, material_ids in orders.items():
        for i, pk in enumerate(material_ids):
            FinalizedMaterial.objects.filter(
                pk=pk,
                contract_id=contract_id,
                archive_item_code=code,
            ).update(order=i)


def move_material(material: FinalizedMaterial, target_code: str) -> None:
    """移动归档材料到另一个清单项。"""
    max_order = (
        FinalizedMaterial.objects.filter(
            contract_id=material.contract_id,
            archive_item_code=target_code,
        )
        .order_by("-order")
        .values_list("order", flat=True)
        .first()
        or 0
    )
    material.archive_item_code = target_code
    material.order = (max_order or 0) + 1
    material.save(update_fields=["archive_item_code", "order"])


def get_materials_for_contract(contract_id: int) -> Any:
    """获取合同的所有归档材料。"""
    return FinalizedMaterial.objects.filter(contract_id=contract_id)
