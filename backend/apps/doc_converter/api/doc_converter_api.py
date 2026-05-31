from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.http import FileResponse
from ninja import File, Router
from ninja.files import UploadedFile

from apps.doc_converter.schemas import HealthOut, JobProgressOut, JobSubmitOut, SaveToDirIn, SaveToDirOut
from apps.doc_converter.services.converter_service import DocConverterService
from apps.doc_converter.services.engine import find_libreoffice

logger = logging.getLogger("apps.doc_converter")

router = Router(tags=["DOC 转 DOCX"])

_service = DocConverterService()

@router.post("/jobs", response=JobSubmitOut, summary="创建转换任务")
def create_conversion_job(
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

@router.get("/jobs/{job_id}", response=JobProgressOut, summary="查询转换进度")
def get_conversion_progress(request: Any, job_id: UUID) -> dict[str, Any]:
    """轮询转换进度。"""
    job, items = _service.get_job_progress(job_id)
    return {
        "job": _service.build_job_payload(job),
        "items": [_service.build_item_payload(item) for item in items],
    }

@router.post("/jobs/{job_id}/cancel", summary="取消转换任务")
def cancel_conversion_job(request: Any, job_id: UUID) -> dict[str, str]:
    """取消转换任务。"""
    job = _service.request_cancel(job_id=job_id)
    return {"status": job.status}

@router.get("/jobs/{job_id}/download", summary="下载转换结果")
def download_converted_files(request: Any, job_id: UUID) -> FileResponse:
    """下载转换完成的 ZIP 包。"""
    job = _service.get_job(job_id)
    if not job.output_zip:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(message="转换结果不存在", code="ZIP_NOT_FOUND", errors={})

    return FileResponse(
        job.output_zip.open("rb"),
        as_attachment=True,
        filename=f"doc_converter_{job_id}.zip",
        content_type="application/zip",
    )

@router.delete("/jobs/{job_id}", summary="删除转换任务")
def delete_conversion_job(request: Any, job_id: UUID) -> dict[str, str]:
    """删除任务及其所有文件。"""
    job = _service.get_job(job_id)
    job.delete()
    return {"status": "deleted"}

@router.get("/health", response=HealthOut, summary="检查 LibreOffice 可用性")
def health_check(request: Any) -> dict[str, Any]:
    path = find_libreoffice()
    return {
        "libreoffice_available": path is not None,
        "libreoffice_path": path,
    }

@router.post("/jobs/{job_id}/save-to-dir", response=SaveToDirOut, summary="保存到指定目录")
def save_to_directory(request: Any, job_id: UUID, payload: SaveToDirIn) -> dict[str, Any]:
    return _service.save_job_to_directory(job_id=job_id, target_dir=payload.target_dir)
