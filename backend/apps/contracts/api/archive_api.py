"""归档材料管理 API 端点"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _
from ninja import Router, Schema

from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial
from apps.contracts.services.archive.checklist.checklist_query import get_checklist_with_status

logger = logging.getLogger("apps.contracts.api")
router = Router()


# ── Schemas ──


class ReorderIn(Schema):
    orders: dict[str, list[int]]


class MoveIn(Schema):
    target_code: str


class SuccessOut(Schema):
    success: bool = True


class ClearAllOut(Schema):
    success: bool = True
    deleted_count: int = 0


class GenerateArchiveFolderOut(Schema):
    """生成归档文件夹输出"""
    success: bool = True
    generated_docs: list[str] = []
    archive_dir: str = ""
    errors: list[str] = []


class ChecklistItemOut(Schema):
    """检查清单项输出"""
    code: str
    name: str
    template: str | None = None
    required: bool
    auto_detect: str | None = None
    source: str
    completed: bool = False
    material_ids: list[int] = []
    materials: list[dict[str, Any]] = []
    has_case_material: bool = False


class ChecklistOut(Schema):
    """检查清单输出"""
    archive_category: str
    archive_category_label: str
    compact_archive: bool = False
    items: list[ChecklistItemOut]
    completed_count: int = 0
    total_count: int = 0
    required_completed_count: int = 0
    required_total_count: int = 0
    completion_percentage: float = 0.0


# ── Endpoints ──


@router.get("/{contract_id}/archive/checklist", response=ChecklistOut)
def get_archive_checklist(request: HttpRequest, contract_id: int) -> Any:
    """获取合同的归档检查清单及各项完成状态"""
    contract = Contract.objects.filter(pk=contract_id).first()
    if not contract:
        return HttpResponse(status=404)

    result = get_checklist_with_status(contract)
    result["archive_category_label"] = str(result["archive_category_label"])
    return ChecklistOut(**result)


@router.post("/{contract_id}/archive/generate-folder", response=GenerateArchiveFolderOut)
def generate_archive_folder(request: HttpRequest, contract_id: int) -> Any:
    """生成归档文件夹：模板文书 + 合并 PDF"""
    contract = Contract.objects.filter(pk=contract_id).first()
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        binding = contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        binding = None

    if not binding or not binding.folder_path:
        return GenerateArchiveFolderOut(
            success=False, errors=["请先在「文档与提醒」中绑定文件夹"],
        )

    from apps.contracts.services.archive import ArchiveGenerationService

    gen_service = ArchiveGenerationService()
    result = gen_service.generate_archive_folder(contract)

    if not result["success"]:
        return GenerateArchiveFolderOut(
            success=False, errors=[result.get("error", "未知错误")],
        )

    return GenerateArchiveFolderOut(
        success=True,
        generated_docs=result.get("generated_docs", []),
        archive_dir=result.get("archive_dir", ""),
        errors=result.get("errors", []),
    )


@router.post("/{contract_id}/archive/reorder", response=SuccessOut)
def reorder_archive_materials(request: HttpRequest, contract_id: int, body: ReorderIn) -> Any:
    """按归档清单项分组排序子项"""
    for code, material_ids in body.orders.items():
        for i, pk in enumerate(material_ids):
            FinalizedMaterial.objects.filter(
                pk=pk,
                contract_id=contract_id,
                archive_item_code=code,
            ).update(order=i)

    logger.info("归档材料排序已保存: contract_id=%s", contract_id)
    return SuccessOut()


@router.post("/{contract_id}/archive/materials/{material_id}/move", response=SuccessOut)
def move_archive_material(request: HttpRequest, contract_id: int, material_id: int, body: MoveIn) -> Any:
    """移动归档材料到另一个清单项"""
    material = FinalizedMaterial.objects.filter(
        pk=material_id,
        contract_id=contract_id,
    ).first()

    if not material:
        return HttpResponse(status=404)

    old_code = material.archive_item_code
    material.archive_item_code = body.target_code
    max_order = (
        FinalizedMaterial.objects.filter(
            contract_id=contract_id,
            archive_item_code=body.target_code,
        )
        .order_by("-order")
        .values_list("order", flat=True)
        .first()
        or 0
    )
    material.order = (max_order or 0) + 1
    material.save(update_fields=["archive_item_code", "order"])

    logger.info(
        "归档材料已移动: material_id=%s, %s → %s, contract_id=%s",
        material_id,
        old_code,
        body.target_code,
        contract_id,
    )
    return SuccessOut()


@router.get("/{contract_id}/archive/materials/{material_id}/preview")
def preview_archive_material(request: HttpRequest, contract_id: int, material_id: int) -> Any:
    """预览单个归档材料"""
    material = FinalizedMaterial.objects.filter(
        pk=material_id,
        contract_id=contract_id,
    ).first()

    if not material:
        return HttpResponse(status=404)

    file_path = Path(material.file_path)
    if not file_path.is_absolute():
        file_path = Path(django_settings.MEDIA_ROOT) / file_path

    if not file_path.exists():
        return HttpResponse(status=404)

    content = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        content_type = "application/pdf"
    elif suffix == ".docx":
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif suffix in (".jpg", ".jpeg"):
        content_type = "image/jpeg"
    elif suffix == ".png":
        content_type = "image/png"
    else:
        content_type = "application/octet-stream"

    import urllib.parse

    response = HttpResponse(content, content_type=content_type)
    encoded_filename = urllib.parse.quote(material.original_filename.encode("utf-8"))
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{encoded_filename}"
    return response


@router.post("/{contract_id}/archive/clear-all", response=ClearAllOut)
def clear_all_archive_materials(request: HttpRequest, contract_id: int) -> Any:
    """清空全部归档材料"""
    materials = FinalizedMaterial.objects.filter(contract_id=contract_id)
    deleted_count = 0
    for material in materials:
        if material.file_path:
            abs_file = Path(django_settings.MEDIA_ROOT) / material.file_path
            if abs_file.exists():
                try:
                    abs_file.unlink()
                except OSError as e:
                    logger.warning("删除归档文件失败: %s: %s", material.file_path, e)
        material.delete()
        deleted_count += 1

    logger.info("已清空全部归档材料: contract_id=%s, count=%s", contract_id, deleted_count)
    return ClearAllOut(deleted_count=deleted_count)
