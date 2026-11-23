"""归档材料查询与 CRUD 服务。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial
from apps.core.models.enums import CaseStatus
from apps.core.services.storage_service import delete_media_file

logger = logging.getLogger("apps.contracts.services.archive")


def get_contract_or_none(contract_id: int) -> Contract | None:  # pragma: no cover
    """获取合同，不存在返回 None。"""
    return Contract.objects.filter(pk=contract_id).first()


def get_material_or_none(material_id: int, contract_id: int) -> FinalizedMaterial | None:  # pragma: no cover
    """获取归档材料，不存在返回 None。"""
    return FinalizedMaterial.objects.filter(pk=material_id, contract_id=contract_id).first()


def delete_material(material: FinalizedMaterial) -> None:  # pragma: no cover
    """删除归档材料（含文件清理）。

    S22-03（2026-11-23 二轮审计）：原实现「先删磁盘文件、再删行」——行删除抛错或
    事务回滚时文件已不可恢复（`delete_media_file` 无回收站），留下悬空记录。现在
    DB 是权威、文件是派生：先删行，提交成功后再删文件（`delete_media_file` 自身
    失败只留痕，不回滚数据）。
    """
    file_path = material.file_path
    material.delete()
    if file_path:
        delete_media_file(file_path)


def delete_all_materials(contract_id: int) -> int:
    """清空合同下全部归档材料，返回删除的材料条数。

    S22-03（2026-11-23 二轮审计）：原实现由 API 层逐条调 ``delete_material``，每条
    各自一个事务，中途抛错就停在「前面删了、后面还在」且不可回滚的半清空状态。
    现在整批行删除在同一事务内完成，物理文件推迟到提交之后（行回滚不会丢文件）。
    """
    with transaction.atomic():
        materials = list(FinalizedMaterial.objects.filter(contract_id=contract_id))
        file_paths = [m.file_path for m in materials if m.file_path]
        if materials:
            FinalizedMaterial.objects.filter(pk__in=[m.pk for m in materials]).delete()

    deleted_count = len(materials)
    for file_path in file_paths:
        delete_media_file(file_path)

    return deleted_count


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
    """获取合同的所有归档材料。

    **必须返回已求值的 list**（2026-11-23 二轮审计 G16）：返回 lazy QuerySet 时，
    真正触发 SQL 的会是 async 上下文里的迭代，生产环境没有
    `DJANGO_ALLOW_ASYNC_UNSAFE` → `SynchronousOnlyOperation` → 端点必然 500。
    """
    return list(FinalizedMaterial.objects.filter(contract_id=contract_id))


def confirm_archive(contract_id: int) -> bool:
    """确认归档：合同置已归档 + 关联案件结案，两步在同一事务内提交。

    任一写入失败即整体回滚，不会留下「合同已归档但案件未结案」的脏状态。
    已是 ``closed`` 的案件不重复写入。合同不存在返回 False（无写入、无事务）。
    """
    from apps.cases.models import Case

    with transaction.atomic():
        updated = Contract.objects.filter(pk=contract_id).update(status="archived")
        if not updated:
            logger.warning("确认归档失败，合同不存在: contract_id=%s", contract_id)
            return False

        Case.objects.filter(contract_id=contract_id).exclude(status=CaseStatus.CLOSED).update(status=CaseStatus.CLOSED)

    logger.info("合同已归档: contract_id=%s", contract_id)
    return True


def toggle_compact_archive(contract: Contract) -> bool:
    """切换精简视图状态并落库，返回切换后的值。"""
    contract.compact_archive = not contract.compact_archive
    contract.save(update_fields=["compact_archive"])
    logger.info(
        "切换精简视图状态: contract_id=%s, compact_archive=%s",
        contract.id,
        contract.compact_archive,
    )
    return bool(contract.compact_archive)


def get_folder_binding_or_none(contract: Contract) -> Any:
    """安全取合同文件夹绑定，未绑定返回 None（避免 API 层捕获 DoesNotExist）。"""
    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        return contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        return None


def validate_upload_file_or_error(uploaded_file: Any) -> str | None:
    """校验上传文件，合法返回 None，否则返回错误文案（供 API 直接回 400）。"""
    from apps.core.services.storage_service import validate_file

    try:
        validate_file(uploaded_file)
    except Exception as exc:
        return str(exc)
    return None


def resolve_archive_preview_file(material: FinalizedMaterial, contract_id: int) -> Path | None:
    """归档材料预览路径收敛（安全审计：material.file_path 不得直读任意路径）。

    统一经 to_media_abs 收敛到 MEDIA_ROOT 内，再校验位于本合同的归档材料目录
    （contracts/finalized/{contract_id}，所有写入方的唯一落盘根）。非法路径、
    越界、不存在一律返回 None，由调用方按 404 处理。
    """
    from django.conf import settings as django_settings

    from apps.core.exceptions import ValidationException
    from apps.core.filesystem.upload_paths import MediaEntity
    from apps.core.services.storage_service import to_media_abs

    if not material.file_path:
        return None

    try:
        file_path = to_media_abs(material.file_path)
    except ValidationException:
        logger.warning(
            "归档材料预览拒绝非法路径: material_id=%s contract_id=%s",
            material.id,
            contract_id,
        )
        return None

    contract_finalized_dir = (
        Path(django_settings.MEDIA_ROOT) / MediaEntity.CONTRACT_FINALIZED / str(contract_id)
    ).resolve()
    if not file_path.is_relative_to(contract_finalized_dir):
        logger.warning(
            "归档材料预览路径越界（不在合同归档目录内）: material_id=%s contract_id=%s",
            material.id,
            contract_id,
        )
        return None

    if not file_path.exists():
        return None
    return file_path
