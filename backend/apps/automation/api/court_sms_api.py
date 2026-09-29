"""
法院短信处理 API
"""

import asyncio
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import FileResponse, Http404
from ninja import Form, Router
from ninja.pagination import PageNumberPagination, paginate

from apps.automation.schemas import (
    CourtSMSAbortOut,
    CourtSMSAssignCaseIn,
    CourtSMSAssignCaseOut,
    CourtSMSBatchDeleteIn,
    CourtSMSBatchDeleteOut,
    CourtSMSCopyDocsIn,
    CourtSMSCopyDocsOut,
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
async def submit_sms(request: Any, payload: CourtSMSSubmitIn) -> CourtSMSSubmitOut:  # pragma: no cover
    """
    提交法院短信

    支持短信转发器直接调用，创建记录并触发异步处理
    """
    service = _get_court_sms_service()

    sms = await sync_to_async(service.submit_sms)(content=payload.content, received_at=payload.received_at)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


@router.post("/court-sms/form", response=CourtSMSSubmitOut)
async def submit_sms_form(  # pragma: no cover
    request: Any,
    content: str = Form(...),
    received_at: datetime | None = Form(None),
) -> CourtSMSSubmitOut:
    """
    提交法院短信（表单格式）

    支持 form-data 格式提交，便于简单的 HTTP 客户端调用
    """
    service = _get_court_sms_service()

    sms = await sync_to_async(service.submit_sms)(content=content, received_at=received_at)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


# ============================================================================
# 状态查询接口
# ============================================================================


@router.get("/court-sms/{sms_id}", response=CourtSMSDetailOut)
async def get_sms_detail(request: Any, sms_id: int) -> CourtSMSDetailOut:  # pragma: no cover
    """
    查询短信处理详情

    返回短信的完整处理状态和关联信息
    """
    service = _get_court_sms_service()

    sms = await sync_to_async(service.get_sms_detail)(sms_id)
    # from_model 内的文书引用聚合会对关联做懒加载查询 + 文件系统 I/O，
    # 必须丢进线程执行，否则在 async 视图里抛 SynchronousOnlyOperation
    return await sync_to_async(CourtSMSDetailOut.from_model)(sms)


@router.get("/court-sms", response=list[CourtSMSListOut])
@paginate(PageNumberPagination, page_size=20)
async def list_sms(  # pragma: no cover
    request: Any,
    status: str | None = None,
    status_group: str | None = None,
    sms_type: str | None = None,
    has_case: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[CourtSMSListOut]:
    """
    查询短信列表

    支持按状态、类型、是否关联案件、日期范围筛选；
    status_group 为前端状态组视图（needs_action / completed），优先于 status。
    """
    service = _get_court_sms_service()

    @sync_to_async
    def _list() -> list[CourtSMSListOut]:
        sms_qs = service.list_sms(
            status=status,
            status_group=status_group,
            sms_type=sms_type,
            has_case=has_case,
            date_from=date_from,
            date_to=date_to,
        )
        return [CourtSMSListOut.from_model(s) for s in sms_qs]

    return await _list()


# ============================================================================
# 手动指定案件接口
# ============================================================================


@router.post("/court-sms/{sms_id}/assign-case", response=CourtSMSAssignCaseOut)
async def assign_case(
    request: Any, sms_id: int, payload: CourtSMSAssignCaseIn
) -> CourtSMSAssignCaseOut:  # pragma: no cover
    """
    手动指定案件

    当自动匹配失败时，管理员可以手动指定案件
    """
    service = _get_court_sms_service()

    sms = await sync_to_async(service.assign_case)(sms_id, payload.case_id)

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
async def retry_processing(request: Any, sms_id: int) -> CourtSMSSubmitOut:  # pragma: no cover
    """
    重新处理短信

    如果短信已手动绑定案件，保留关联，仅重新执行下载/重命名/通知流程。
    否则重置全部状态，重新执行完整处理流程（含匹配）。
    """
    service = _get_court_sms_service()

    sms = await sync_to_async(service.retry_processing)(sms_id)

    return CourtSMSSubmitOut(success=True, data={"id": sms.id, "status": sms.status, "created_at": sms.created_at})


# ============================================================================
# 删除接口
# ============================================================================


@router.delete("/court-sms/{sms_id}")
async def delete_sms(request: Any, sms_id: int) -> dict[str, bool]:  # pragma: no cover
    """删除单条短信"""
    service = _get_court_sms_service()
    await sync_to_async(service.delete_sms)(sms_id)
    return {"success": True}


@router.post("/court-sms/batch-delete", response=CourtSMSBatchDeleteOut)
async def batch_delete_sms(request: Any, payload: CourtSMSBatchDeleteIn) -> CourtSMSBatchDeleteOut:  # pragma: no cover
    """批量删除短信"""
    service = _get_court_sms_service()
    deleted = await sync_to_async(service.batch_delete_sms)(payload.ids)
    return CourtSMSBatchDeleteOut(deleted=deleted)


# ============================================================================
# 终止任务接口
# ============================================================================


@router.post("/court-sms/{sms_id}/abort-and-delete", response=CourtSMSAbortOut)
async def abort_and_delete_sms(request: Any, sms_id: int) -> CourtSMSAbortOut:  # pragma: no cover
    """终止并彻底删除短信处理任务。

    清理 Django-Q 中该短信的重试调度与排队任务（含爬虫下载任务的退避重试），
    删除短信记录与归属的下载任务（下载原件随信号清理；已归档到案件日志的
    复制件不受影响）。用于任务卡住/反复失败时由用户主动放弃。
    """
    from apps.automation.services.sms.court_sms_abort_service import CourtSmsAbortService

    summary = await sync_to_async(CourtSmsAbortService().abort_and_delete)(sms_id)
    return CourtSMSAbortOut(success=True, data=summary)


# ============================================================================
# 文书下载接口
# ============================================================================


@router.get("/court-sms/{sms_id}/documents/{ref_index}/download")
async def download_document(request: Any, sms_id: int, ref_index: int) -> FileResponse:  # pragma: no cover
    """下载单个关联文书"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = await sync_to_async(CourtSMSRepository().get_by_id_or_none)(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = await sync_to_async(CourtSMSDocumentReferenceService().collect)(sms)
    if ref_index < 0 or ref_index >= len(references):
        raise Http404("文书索引超出范围")

    file_path = Path(references[ref_index].file_path)
    if not file_path.exists() or not file_path.is_file():
        raise Http404("文书文件不存在")

    file_obj = await asyncio.to_thread(file_path.open, "rb")
    return FileResponse(file_obj, as_attachment=True, filename=file_path.name)


@router.post("/court-sms/{sms_id}/documents/copy-to-clipboard", response=CourtSMSCopyDocsOut)
async def copy_documents_to_clipboard(  # pragma: no cover
    request: Any, sms_id: int, payload: CourtSMSCopyDocsIn
) -> CourtSMSCopyDocsOut:
    """复制关联文书到**系统**剪贴板（同 Finder ⌘C，微信可直接 ⌘V 粘贴文件）。

    浏览器自身写不了文件类剪贴板（W3C 只保证 text/html、text/plain、image/png），
    后端与律师同机时由 NSPasteboard 直接落板；非 macOS 后端返回 unsupported，
    前端再降级浏览器剪贴板（Safari 可用）。
    """
    from apps.core.services.mac_clipboard_service import MacClipboardFileService

    clipboard = MacClipboardFileService()
    if not clipboard.is_available():
        return CourtSMSCopyDocsOut(success=False, copied=0, reason="unsupported")

    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = await sync_to_async(CourtSMSRepository().get_by_id_or_none)(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = await sync_to_async(CourtSMSDocumentReferenceService().collect)(sms)
    valid_indexes = [i for i in payload.indexes if 0 <= i < len(references)]
    if not valid_indexes:
        return CourtSMSCopyDocsOut(success=False, copied=0, reason="没有可复制的文书文件")

    paths = [Path(references[i].file_path) for i in valid_indexes]
    copied = await sync_to_async(clipboard.copy_file_paths)(paths)
    if copied == 0:
        return CourtSMSCopyDocsOut(success=False, copied=0, reason="文书文件不存在或写入剪贴板失败")
    return CourtSMSCopyDocsOut(success=True, copied=copied, reason=None)


@router.get("/court-sms/{sms_id}/documents/download-all")
async def download_all_documents(request: Any, sms_id: int) -> FileResponse:  # pragma: no cover
    """批量下载关联文书（ZIP）"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = await sync_to_async(CourtSMSRepository().get_by_id_or_none)(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = await sync_to_async(CourtSMSDocumentReferenceService().collect)(sms)
    existing_files: list[Path] = []
    for ref in references:
        p = Path(ref.file_path)
        if p.exists() and p.is_file():
            existing_files.append(p)

    if not existing_files:
        raise Http404("没有可下载的文书文件")

    def _build_zip() -> io.BytesIO:
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
        return zip_buffer

    zip_buffer = await asyncio.to_thread(_build_zip)
    return FileResponse(zip_buffer, as_attachment=True, filename=f"courtsms_{sms_id}_documents.zip")


@router.post("/court-sms/{sms_id}/documents/{ref_index}/rename")
async def rename_document(
    request: Any, sms_id: int, ref_index: int, payload: dict[str, Any]
) -> dict[str, Any]:  # pragma: no cover
    """重命名单个关联文书"""
    from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository

    sms = await sync_to_async(CourtSMSRepository().get_by_id_or_none)(sms_id=sms_id)
    if sms is None:
        raise Http404("短信记录不存在")

    references = await sync_to_async(CourtSMSDocumentReferenceService().collect)(sms)
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
    await asyncio.to_thread(file_path.rename, new_path)
    new_abs = str(new_path.resolve())

    # 同步引用
    from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
    from apps.automation.models import CourtSMS

    admin_instance = CourtSMSAdmin(CourtSMS, None)  # type: ignore[arg-type]
    await sync_to_async(admin_instance._sync_document_references)(sms, old_abs, new_abs, ref.court_document_id)

    return {"success": True, "new_name": new_path.name}
