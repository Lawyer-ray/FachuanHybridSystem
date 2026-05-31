"""归档材料管理 API 端点"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings
from django.http import HttpRequest, HttpResponse

from ninja import Router, Schema

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

class ToggleCompactOut(Schema):
    """精简视图切换输出"""

    success: bool = True
    compact_archive: bool = False

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

class UploadArchiveItemOut(Schema):
    """上传归档材料输出"""

    id: int = 0
    filename: str = ""

class ConfirmArchiveOut(Schema):
    """确认归档输出"""

    success: bool = True
    message: str = ""

class SyncCaseMaterialsOut(Schema):
    """同步案件材料输出"""

    success: bool = True
    synced_count: int = 0
    message: str = ""

class ScaleToA4Out(Schema):
    """A4缩放输出"""

    success: bool = True
    scaled_count: int = 0
    message: str = ""

class LearnRulesOut(Schema):
    """学习分类规则输出"""

    success: bool = True
    learned: int = 0
    updated: int = 0
    skipped: int = 0
    message: str = ""

# ── Endpoints ──

@router.post("/archive/learn-rules", response=LearnRulesOut)
def learn_archive_rules(request: HttpRequest) -> Any:
    """从已归档材料中学习分类规则（全局操作）"""
    from apps.contracts.services.archive.learning_service import ArchiveLearningService

    try:
        service = ArchiveLearningService()
        result = service.learn_from_archived_materials()
        return LearnRulesOut(
            success=True,
            learned=result.get("learned", 0),
            updated=result.get("updated", 0),
            skipped=result.get("skipped", 0),
            message=f"学习完成：新增 {result['learned']} 条，更新 {result['updated']} 条，跳过 {result['skipped']} 条",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("archive_learning_failed")
        return LearnRulesOut(success=False, message=str(exc))

@router.get("/{contract_id}/archive/download-item/{archive_item_code}")
def download_archive_item(request: HttpRequest, contract_id: int, archive_item_code: str) -> Any:
    """下载归档检查项材料（多文件自动合并为 PDF）"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.services.archive import ArchiveGenerationService

    gen_service = ArchiveGenerationService()
    result = gen_service.download_archive_item(contract, archive_item_code)

    if result.get("error"):
        return HttpResponse(status=404)

    import urllib.parse

    response = HttpResponse(result["content"], content_type=result["content_type"])
    encoded_filename = urllib.parse.quote(result["filename"].encode("utf-8"))
    disposition = "inline" if request.GET.get("preview") == "1" else "attachment"
    response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded_filename}"
    return response

@router.get("/{contract_id}/archive/checklist", response=ChecklistOut)
def get_archive_checklist(request: HttpRequest, contract_id: int) -> Any:
    """获取合同的归档检查清单及各项完成状态"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    result = get_checklist_with_status(contract)
    result["archive_category_label"] = str(result["archive_category_label"])
    return ChecklistOut(**result)

@router.post("/{contract_id}/archive/generate-folder", response=GenerateArchiveFolderOut)
def generate_archive_folder(request: HttpRequest, contract_id: int) -> Any:
    """生成归档文件夹：模板文书 + 合并 PDF"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.models.folder_binding import ContractFolderBinding

    try:
        binding = contract.folder_binding
    except ContractFolderBinding.DoesNotExist:
        binding = None

    if not binding or not binding.folder_path:
        return GenerateArchiveFolderOut(
            success=False,
            errors=["请先在「文档与提醒」中绑定文件夹"],
        )

    from apps.contracts.services.archive import ArchiveGenerationService

    gen_service = ArchiveGenerationService()
    result = gen_service.generate_archive_folder(contract)

    if not result["success"]:
        return GenerateArchiveFolderOut(
            success=False,
            errors=[result.get("error", "未知错误")],
        )

    return GenerateArchiveFolderOut(
        success=True,
        generated_docs=result.get("generated_docs", []),
        archive_dir=result.get("archive_dir", ""),
        errors=result.get("errors", []),
    )

@router.post("/{contract_id}/archive/toggle-compact", response=ToggleCompactOut)
def toggle_compact_archive(request: HttpRequest, contract_id: int) -> Any:
    """切换精简视图状态"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    contract.compact_archive = not contract.compact_archive
    contract.save(update_fields=["compact_archive"])
    logger.info(
        "切换精简视图状态: contract_id=%s, compact_archive=%s",
        contract_id,
        contract.compact_archive,
    )
    return ToggleCompactOut(success=True, compact_archive=contract.compact_archive)

@router.post("/{contract_id}/archive/sync-case-materials", response=SyncCaseMaterialsOut)
def sync_case_materials(request: HttpRequest, contract_id: int) -> Any:
    """从案件材料同步到归档"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.services.archive.wiring import build_archive_checklist_service

    checklist_service = build_archive_checklist_service()
    result = checklist_service.sync_case_materials_to_archive(contract)

    synced_count = len(result.get("synced", []))
    return SyncCaseMaterialsOut(
        success=True,
        synced_count=synced_count,
        message=f"同步完成，{synced_count} 个文件",
    )

@router.post("/{contract_id}/archive/reset-and-resync", response=SyncCaseMaterialsOut)
def reset_and_resync_case_materials(request: HttpRequest, contract_id: int) -> Any:
    """重置并重新同步案件材料到归档"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.services.archive.wiring import build_archive_checklist_service

    checklist_service = build_archive_checklist_service()
    result = checklist_service.reset_and_resync_case_materials(contract)

    sync_result = result.get("sync_result", {})
    synced_count = len(sync_result.get("synced", []))
    return SyncCaseMaterialsOut(
        success=True,
        synced_count=synced_count,
        message=f"重置并重新同步完成，{synced_count} 个文件",
    )

@router.post("/{contract_id}/archive/scale-to-a4", response=ScaleToA4Out)
def scale_to_a4(request: HttpRequest, contract_id: int) -> Any:
    """将所有非A4尺寸的PDF页面缩放为A4大小"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    from apps.contracts.services.archive import ArchiveGenerationService

    gen_service = ArchiveGenerationService()
    result = gen_service.scale_pages_to_a4(contract)

    return ScaleToA4Out(
        success=result.get("success", False),
        scaled_count=result.get("scaled_count", 0),
        message=result.get("message", ""),
    )

@router.post("/{contract_id}/archive/confirm", response=ConfirmArchiveOut)
def confirm_archive(request: HttpRequest, contract_id: int) -> Any:
    """确认归档：将合同状态改为已归档，并自动结案关联案件"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    contract.status = "archived"
    contract.save(update_fields=["status"])

    # 自动结案关联案件
    for case in contract.cases.all():
        if case.status != "closed":
            case.status = "closed"
            case.save(update_fields=["status"])

    logger.info("合同已归档: contract_id=%s", contract_id)
    return ConfirmArchiveOut(success=True, message="归档确认成功")

@router.post("/{contract_id}/archive/upload", response=UploadArchiveItemOut)
def upload_archive_item(request: HttpRequest, contract_id: int) -> Any:
    """上传文件到归档检查清单项"""
    from apps.contracts.services.archive.archive_query_service import get_contract_or_none

    contract = get_contract_or_none(contract_id)
    if not contract:
        return HttpResponse(status=404)

    uploaded_file = request.FILES.get("file")
    category = request.POST.get("category", "")
    if not uploaded_file:
        return HttpResponse(status=400)

    from apps.core.services.file_upload_service import FileUploadService

    try:
        FileUploadService().validate_file(uploaded_file)  # type: ignore[arg-type]
    except Exception as exc:
        return HttpResponse(str(exc), status=400)

    from apps.contracts.services.archive.wiring import build_archive_checklist_service

    checklist_service = build_archive_checklist_service()
    material = checklist_service.upload_material_to_archive_item(
        contract=contract,
        archive_item_code=category,
        uploaded_file=uploaded_file,
    )

    return UploadArchiveItemOut(id=material.id, filename=material.original_filename)

@router.delete("/{contract_id}/archive/materials/{material_id}", response=SuccessOut)
def delete_archive_material(request: HttpRequest, contract_id: int, material_id: int) -> Any:
    """删除归档材料"""
    from apps.contracts.services.archive.archive_query_service import delete_material, get_material_or_none

    material = get_material_or_none(material_id, contract_id)

    if not material:
        return HttpResponse(status=404)

    delete_material(material)
    logger.info("已删除归档材料: material_id=%s, contract_id=%s", material_id, contract_id)
    return SuccessOut()

@router.post("/{contract_id}/archive/reorder", response=SuccessOut)
def reorder_archive_materials(request: HttpRequest, contract_id: int, body: ReorderIn) -> Any:
    """按归档清单项分组排序子项"""
    from apps.contracts.services.archive.archive_query_service import reorder_materials

    reorder_materials(contract_id, body.orders)

    logger.info("归档材料排序已保存: contract_id=%s", contract_id)
    return SuccessOut()

@router.post("/{contract_id}/archive/materials/{material_id}/move", response=SuccessOut)
def move_archive_material(request: HttpRequest, contract_id: int, material_id: int, body: MoveIn) -> Any:
    """移动归档材料到另一个清单项"""
    from apps.contracts.services.archive.archive_query_service import get_material_or_none, move_material

    material = get_material_or_none(material_id, contract_id)

    if not material:
        return HttpResponse(status=404)

    old_code = material.archive_item_code
    move_material(material, body.target_code)

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
    from apps.contracts.services.archive.archive_query_service import get_material_or_none

    material = get_material_or_none(material_id, contract_id)

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
    from apps.contracts.services.archive.archive_query_service import delete_material, get_materials_for_contract

    materials = get_materials_for_contract(contract_id)
    deleted_count = 0
    for material in materials:
        delete_material(material)
        deleted_count += 1

    logger.info("已清空全部归档材料: contract_id=%s, count=%s", contract_id, deleted_count)
    return ClearAllOut(deleted_count=deleted_count)
