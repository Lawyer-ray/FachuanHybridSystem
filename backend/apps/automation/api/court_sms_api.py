"""
法院短信处理 API
"""

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.http import FileResponse, Http404
from ninja import Form, Router
from ninja.pagination import PageNumberPagination, paginate

from apps.automation.schemas import (
    CourtSMSAssignCaseIn,
    CourtSMSAssignCaseOut,
    CourtSMSBatchDeleteIn,
    CourtSMSBatchDeleteOut,
    CourtSMSDetailOut,
    CourtSMSListOut,
    CourtSMSSubmitIn,
    CourtSMSSubmitOut,
)

router = Router(tags=["法院短信处理"])


def _get_court_sms_service() -> Any:
    from apps.core.dependencies.automation_sms_entry import build_court_sms_service_ctx

    return build_court_sms_service_ctx()


# ============================================================================
# 短信提交接口
# ============================================================================


@router.post("/court-sms", response=CourtSMSSubmitOut)
def submit_sms(request: Any, payload: CourtSMSSubmitIn) -> CourtSMSSubmitOut:  # pragma: no cover
    """
    提交法院短信

    支持短信转发器直接调用，创建记录并触发异步处理
    """
    service = _get_court_sms_service()

    sms = service.submit_sms(content=payload.content, received_at=payload.received_at)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


@router.post("/court-sms/form", response=CourtSMSSubmitOut)
def submit_sms_form(  # pragma: no cover
    request: Any,
    content: str = Form(...),
    received_at: datetime | None = Form(None),
) -> CourtSMSSubmitOut:
    """
    提交法院短信（表单格式）

    支持 form-data 格式提交，便于简单的 HTTP 客户端调用
    """
    service = _get_court_sms_service()

    sms = service.submit_sms(content=content, received_at=received_at)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


# ============================================================================
# 状态查询接口
# ============================================================================


@router.get("/court-sms/{sms_id}", response=CourtSMSDetailOut)
def get_sms_detail(request: Any, sms_id: int) -> CourtSMSDetailOut:  # pragma: no cover
    """
    查询短信处理详情

    返回短信的完整处理状态和关联信息
    """
    service = _get_court_sms_service()

    sms = service.get_sms_detail(sms_id)

    return CourtSMSDetailOut.from_model(sms)


@router.get("/court-sms", response=list[CourtSMSListOut])
@paginate(PageNumberPagination, page_size=20)
def list_sms(  # pragma: no cover
    request: Any,
    status: str | None = None,
    sms_type: str | None = None,
    has_case: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CourtSMSListOut]:
    """
    查询短信列表

    支持按状态、类型、是否关联案件、日期范围筛选
    """
    service = _get_court_sms_service()

    sms_list = service.list_sms(
        status=status, sms_type=sms_type, has_case=has_case, date_from=date_from, date_to=date_to
    )

    return [CourtSMSListOut.from_model(sms) for sms in sms_list]


# ============================================================================
# 手动指定案件接口
# ============================================================================


@router.post("/court-sms/{sms_id}/assign-case", response=CourtSMSAssignCaseOut)
def assign_case(request: Any, sms_id: int, payload: CourtSMSAssignCaseIn) -> CourtSMSAssignCaseOut:  # pragma: no cover
    """
    手动指定案件

    当自动匹配失败时，管理员可以手动指定案件
    """
    service = _get_court_sms_service()

    sms = service.assign_case(sms_id, payload.case_id)

    return CourtSMSAssignCaseOut(
        success=True,
        data={
            "id": sms.id,
            "status": sms.status,
            "case": {"id": sms.case.id, "name": sms.case.name} if sms.case else None,
        },
    )


# ============================================================================
# 重新处理接口
# ============================================================================


@router.post("/court-sms/{sms_id}/retry", response=CourtSMSSubmitOut)
def retry_processing(request: Any, sms_id: int) -> CourtSMSSubmitOut:  # pragma: no cover
    """
    重新处理短信

    重置状态并重新执行完整处理流程
    """
    service = _get_court_sms_service()

    sms = service.retry_processing(sms_id)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


# ============================================================================
# 删除接口
# ============================================================================


@router.delete("/court-sms/{sms_id}")
def delete_sms(request: Any, sms_id: int) -> dict[str, bool]:  # pragma: no cover
    """删除单条短信"""
    service = _get_court_sms_service()
    service.delete_sms(sms_id)
    return {"success": True}


@router.post("/court-sms/batch-delete", response=CourtSMSBatchDeleteOut)
def batch_delete_sms(request: Any, payload: CourtSMSBatchDeleteIn) -> CourtSMSBatchDeleteOut:  # pragma: no cover
    """批量删除短信"""
    service = _get_court_sms_service()
    deleted = service.batch_delete_sms(payload.ids)
    return CourtSMSBatchDeleteOut(deleted=deleted)


# ============================================================================
# 文书下载接口
# ============================================================================


@router.get("/court-sms/{sms_id}/documents/{ref_index}/download")
def download_document(request: Any, sms_id: int, ref_index: int) -> FileResponse:  # pragma: no cover
    """下载单个关联文书"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = CourtSMSRepository().get_by_id_or_none(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = CourtSMSDocumentReferenceService().collect(sms)
    if ref_index < 0 or ref_index >= len(references):
        raise Http404("文书索引超出范围")

    file_path = Path(references[ref_index].file_path)
    if not file_path.exists() or not file_path.is_file():
        raise Http404("文书文件不存在")

    return FileResponse(file_path.open("rb"), as_attachment=True, filename=file_path.name)


@router.get("/court-sms/{sms_id}/documents/download-all")
def download_all_documents(request: Any, sms_id: int) -> FileResponse:  # pragma: no cover
    """批量下载关联文书（ZIP）"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = CourtSMSRepository().get_by_id_or_none(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = CourtSMSDocumentReferenceService().collect(sms)
    existing_files: list[Path] = []
    for ref in references:
        p = Path(ref.file_path)
        if p.exists() and p.is_file():
            existing_files.append(p)

    if not existing_files:
        raise Http404("没有可下载的文书文件")

    zip_buffer = io.BytesIO()
    name_count: dict[str, int] = {}
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in existing_files:
            base = fp.name
            if base in name_count:
                name_count[base] += 1
                arcname = f"{fp.stem}_{name_count[base]}{fp.suffix}"
            else:
                name_count[base] = 1
                arcname = base
            zf.write(fp, arcname=arcname)

    zip_buffer.seek(0)
    return FileResponse(zip_buffer, as_attachment=True, filename=f"courtsms_{sms_id}_documents.zip")


@router.post("/court-sms/{sms_id}/documents/{ref_index}/rename")
def rename_document(request: Any, sms_id: int, ref_index: int, payload: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """重命名单个关联文书"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = CourtSMSRepository().get_by_id_or_none(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = CourtSMSDocumentReferenceService().collect(sms)
    if ref_index < 0 or ref_index >= len(references):
        return {"success": False, "error": "文书索引超出范围"}

    ref = references[ref_index]
    file_path = Path(ref.file_path)
    if not file_path.exists() or not file_path.is_file():
        return {"success": False, "error": "文书文件不存在"}

    raw_stem = str(payload.get("new_stem", "") or "").strip()
    if not raw_stem:
        return {"success": False, "error": "文件名不能为空"}
    if "." in raw_stem:
        return {"success": False, "error": "只能修改文件名，不能修改扩展名"}

    new_stem = re.sub(r'[\\/:*?"<>|]', "", raw_stem).strip()
    if not new_stem:
        return {"success": False, "error": "文件名包含非法字符"}

    new_path = file_path.with_name(f"{new_stem}{file_path.suffix}")
    if new_path == file_path:
        return {"success": True, "message": "文件名未变化"}
    if new_path.exists():
        return {"success": False, "error": f"目标文件已存在：{new_path.name}"}

    old_abs = str(file_path.resolve())
    file_path.rename(new_path)
    new_abs = str(new_path.resolve())

    # 同步引用
    from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
    from apps.automation.models import CourtSMS

    admin_instance = CourtSMSAdmin(CourtSMS, None)  # type: ignore[arg-type]
    admin_instance._sync_document_references(sms, old_abs, new_abs, ref.court_document_id)

    return {"success": True, "new_name": new_path.name}
