"""归档材料查询与 CRUD 服务。"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial
from apps.core.services.storage_service import delete_media_file


def get_contract_or_none(contract_id: int) -> Contract | None:  # pragma: no cover
    """获取合同，不存在返回 None。"""
    return Contract.objects.filter(pk=contract_id).first()


def get_material_or_none(material_id: int, contract_id: int) -> FinalizedMaterial | None:  # pragma: no cover
    """获取归档材料，不存在返回 None。"""
    return FinalizedMaterial.objects.filter(pk=material_id, contract_id=contract_id).first()


def delete_material(material: FinalizedMaterial) -> None:  # pragma: no cover
    """删除归档材料（含文件清理）。"""
    if material.file_path:
        delete_media_file(material.file_path)
    material.delete()


def reorder_materials(contract_id: int, orders: dict[str, list[int]]) -> None:
    """按归档清单项分组排序子项（整体事务 + 批量更新）。"""
    all_ids = [pk for ids in orders.values() for pk in ids]
    if not all_ids:
        return
    with transaction.atomic():
        mats = {m.pk: m for m in FinalizedMaterial.objects.filter(pk__in=all_ids, contract_id=contract_id)}
        to_update: list[FinalizedMaterial] = []
        for code, material_ids in orders.items():
            for i, pk in enumerate(material_ids):
                mat = mats.get(pk)
                if not mat:
                    continue
                mat.order = i + 1
                # 动态映射的材料（如合同正本）数据库中 archive_item_code 为空，
                # 需要同步写入，否则 get_checklist_with_status 加载顺序会错乱。
                if not mat.archive_item_code:
                    mat.archive_item_code = code
                to_update.append(mat)
        # FinalizedMaterial 无 post_save 信号依赖，bulk_update 安全
        if to_update:
            FinalizedMaterial.objects.bulk_update(to_update, ["order", "archive_item_code"])


def move_material(material: FinalizedMaterial, target_code: str) -> None:
    """移动归档材料到另一个清单项。"""
    with transaction.atomic():
        # 锁合同行串行化同合同的材料移动/排序，避免并发取 Max 时顺序重复
        Contract.objects.select_for_update().get(pk=material.contract_id)
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


def get_materials_for_contract(contract_id: int) -> Any:  # pragma: no cover
    """获取合同的所有归档材料。"""
    return FinalizedMaterial.objects.filter(contract_id=contract_id)
