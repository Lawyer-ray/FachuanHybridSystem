from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import FileResponse
from ninja import File, Router
from ninja.files import UploadedFile

from apps.core.exceptions import NotFoundError
from apps.doc_converter.models import DocConverterJobStatus
from apps.doc_converter.schemas import (
    ClipboardCopyOut,
    CopyItemsIn,
    HealthOut,
    JobListOut,
    JobProgressOut,
    JobSubmitOut,
    SaveToDirIn,
    SaveToDirOut,
)
from apps.doc_converter.services.converter_service import DocConverterService
from apps.doc_converter.services.engine import find_libreoffice

logger = logging.getLogger("apps.doc_converter")

router = Router(tags=["DOC 转 DOCX"])

_service = DocConverterService()


def _request_user(request: Any) -> Any:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    return user


@router.post("/jobs", response=JobSubmitOut, summary="创建转换任务")
def create_conversion_job(  # pragma: no cover
    request: Any,
    files: list[UploadedFile] = File(...),
) -> dict[str, Any]:
    """上传多个 .doc 文件，创建异步转换任务。"""
    job = _service.create_job(files=files, created_by=request.user)  # type: ignore[arg-type]
    return {
        "job_id": str(job.id),
        "status": job.status,
        "total_files": job.total_files,
    }


@router.get("/jobs", response=JobListOut, summary="历史转换任务列表")
def list_conversion_jobs(request: Any, page: int = 1, page_size: int = 20) -> dict[str, Any]:  # pragma: no cover
    """分页列出历史转换任务（最新在前），供前端历史弹窗浏览与重新下载。"""
    jobs, count, num_pages = _service.list_jobs(page=page, page_size=page_size, user=_request_user(request))
    return {
        "items": [_service.build_job_payload(job) for job in jobs],
        "count": count,
        "page": page,
        "num_pages": num_pages,
    }


@router.get("/jobs/{job_id}", response=JobProgressOut, summary="查询转换进度")
def get_conversion_progress(request: Any, job_id: UUID) -> dict[str, Any]:  # pragma: no cover
    """轮询转换进度。"""
    job, items = _service.get_job_progress(job_id, user=_request_user(request))
    return {
        "job": _service.build_job_payload(job),
        "items": [_service.build_item_payload(item) for item in items],
    }


@router.post("/jobs/{job_id}/cancel", summary="取消转换任务")
def cancel_conversion_job(request: Any, job_id: UUID) -> dict[str, str]:  # pragma: no cover
    """取消转换任务。"""
    job = _service.request_cancel(job_id=job_id, user=_request_user(request))
    return {"status": job.status}


@router.get("/jobs/{job_id}/download", summary="下载转换结果")
def download_converted_files(request: Any, job_id: UUID) -> FileResponse:  # pragma: no cover
    """下载转换完成的 ZIP 包。"""
    job = _service.get_job(job_id, user=_request_user(request))
    if not job.output_zip:
        raise NotFoundError(message="转换结果不存在", code="ZIP_NOT_FOUND", errors={})

    return FileResponse(
        job.output_zip.open("rb"),
        as_attachment=True,
        filename=f"doc_converter_{job_id}.zip",
        content_type="application/zip",
    )


@router.get("/jobs/{job_id}/items/{item_id}/download", summary="下载单个转换文件")
def download_single_file(request: Any, job_id: UUID, item_id: UUID) -> FileResponse:  # pragma: no cover
    """下载单个已转换的 .docx 文件。"""
    _service.get_job(job_id, user=_request_user(request))  # 安全审计 B-10：校验任务属主
    item = _service.get_item(job_id=job_id, item_id=item_id)
    if item.status != DocConverterJobStatus.COMPLETED or not item.converted_file:
        raise NotFoundError(message="转换文件不存在", code="ITEM_NOT_CONVERTED", errors={})

    filename = Path(item.original_name).stem + ".docx"
    return FileResponse(
        item.converted_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/jobs/{job_id}/items/copy-to-clipboard", response=ClipboardCopyOut, summary="复制转换文件到系统剪贴板")
def copy_items_to_clipboard(  # pragma: no cover
    request: Any, job_id: UUID, payload: CopyItemsIn
) -> dict[str, Any]:
    """把已转换的 .docx 以 file-url 写入 macOS 系统剪贴板（同 Finder ⌘C）。

    浏览器写不了文件类剪贴板；后端与用户同机时由此落板，微信 ⌘V 直接粘出文件。
    产物物理文件是 UUID 命名（下载端点靠响应头改名），粘贴方读的是路径 basename，
    所以先在临时目录按「原名.docx」复制一份再落板。
    非 macOS 后端返回 reason=unsupported，前端降级复制文件名。
    """
    import shutil
    import tempfile

    from apps.core.services.mac_clipboard_service import MacClipboardFileService

    clipboard = MacClipboardFileService()
    if not clipboard.is_available():
        return {"success": False, "copied": 0, "reason": "unsupported"}

    # file-url 是路径引用：粘贴方按路径读文件，临时副本不能删（用固定目录覆盖写，
    # 量小、重启由系统清理；不用 TemporaryDirectory——出 with 即删会导致粘贴 404）
    tmp = Path(tempfile.gettempdir()) / "fachuan_clipboard"
    tmp.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    # 安全审计 B-10：校验任务属主
    _service.get_job(job_id, user=_request_user(request))
    for item_id in payload.item_ids:
        item = _service.get_item(job_id=job_id, item_id=item_id)
        if item.status != DocConverterJobStatus.COMPLETED or not item.converted_file:
            continue
        named = tmp / (Path(item.original_name).stem + ".docx")
        shutil.copyfile(item.converted_file.path, named)
        paths.append(named)

    copied = clipboard.copy_file_paths(paths)
    if copied == 0:
        return {"success": False, "copied": 0, "reason": "转换文件不存在或写入剪贴板失败"}
    return {"success": True, "copied": copied, "reason": None}


@router.delete("/jobs/{job_id}", summary="删除转换任务")
def delete_conversion_job(request: Any, job_id: UUID) -> dict[str, str]:  # pragma: no cover
    """删除任务及其所有文件。"""
    job = _service.get_job(job_id, user=_request_user(request))
    job.delete()
    return {"status": "deleted"}


@router.get("/health", response=HealthOut, summary="检查 LibreOffice 可用性")
def health_check(request: Any) -> dict[str, Any]:  # pragma: no cover
    path = find_libreoffice()
    return {
        "libreoffice_available": path is not None,
        "libreoffice_path": path,
    }


@router.post("/jobs/{job_id}/save-to-dir", response=SaveToDirOut, summary="保存到指定目录")
def save_to_directory(request: Any, job_id: UUID, payload: SaveToDirIn) -> dict[str, Any]:  # pragma: no cover
    _service.get_job(job_id, user=_request_user(request))  # 安全审计 B-10：校验任务属主
    return _service.save_job_to_directory(job_id=job_id, target_dir=payload.target_dir)
