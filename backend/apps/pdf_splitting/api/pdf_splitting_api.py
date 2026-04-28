from __future__ import annotations

from typing import Any
from uuid import UUID

from django.http import FileResponse, HttpResponse
from ninja import File, Form, Router
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.storage import PdfSplitStorage

router = Router(tags=["PDF 拆解"])


class SegmentOut(BaseModel):
    id: int
    order: int
    page_start: int
    page_end: int
    segment_type: str
    segment_label: str
    filename: str
    confidence: float
    review_flag: str
    review_flag_label: str
    source_method: str


class JobOut(BaseModel):
    job_id: str
    status: str
    split_mode: str
    ocr_profile: str
    progress: int
    total_pages: int
    processed_pages: int
    current_page: int
    summary: dict[str, Any]
    segments: list[SegmentOut]
    download_url: str = ""
    pdf_url: str = ""
    error_message: str = ""


class JobSubmitOut(BaseModel):
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="状态")


class ConfirmSegmentIn(BaseModel):
    id: int | None = None
    order: int | None = None
    page_start: int
    page_end: int
    segment_type: str
    filename: str
    confidence: float | None = 0.0
    review_flag: str | None = None
    source_method: str | None = None


class ConfirmRequestIn(BaseModel):
    segments: list[ConfirmSegmentIn]


@router.post("/jobs", response=JobSubmitOut)
def create_pdf_split_job(
    request: Any,
    file: UploadedFile | None = File(None),
    source_path: str | None = Form(None),
    template_key: str = Form("filing_materials_v1"),
    split_mode: str = Form("content_analysis"),
    ocr_profile: str = Form("balanced"),
) -> JobSubmitOut:
    job = PdfSplitJobService().create_job(
        file=file,
        source_path=source_path,
        template_key=template_key,
        split_mode=split_mode,
        ocr_profile=ocr_profile,
        created_by=getattr(request, "user", None),
    )
    return JobSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/jobs/{job_id}", response=JobOut)
def get_pdf_split_job(request: Any, job_id: UUID) -> JobOut:
    job = PdfSplitJobService().get_job(job_id)
    payload = PdfSplitJobService().build_job_payload(job)
    return JobOut(**payload)


@router.get("/jobs/{job_id}/pages/{page_no}/preview")
def get_pdf_split_preview(request: Any, job_id: UUID, page_no: int) -> HttpResponse:
    job = PdfSplitJobService().get_job(job_id)
    preview_path = PdfSplitService().render_preview(job, page_no)
    return FileResponse(preview_path.open("rb"), content_type="image/png", filename=preview_path.name)  # type: ignore[return-value]


@router.post("/jobs/{job_id}/confirm", response=JobSubmitOut)
def confirm_pdf_split_job(request: Any, job_id: UUID, payload: ConfirmRequestIn) -> JobSubmitOut:
    job = PdfSplitJobService().confirm_segments(job_id=job_id, items=[item.model_dump() for item in payload.segments])
    return JobSubmitOut(job_id=str(job.id), status=job.status)


@router.post("/jobs/{job_id}/cancel", response=JobSubmitOut)
def cancel_pdf_split_job(request: Any, job_id: UUID) -> JobSubmitOut:
    job = PdfSplitJobService().request_cancel(job_id=job_id)
    return JobSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/jobs/{job_id}/download")
def get_pdf_split_download(request: Any, job_id: UUID) -> HttpResponse:
    job = PdfSplitJobService().get_job(job_id)
    storage = PdfSplitStorage(job.id)
    if not storage.export_zip_path.exists():
        return HttpResponse(status=404)
    return FileResponse(storage.export_zip_path.open("rb"), content_type="application/zip", filename="split_result.zip")  # type: ignore[return-value]


@router.get("/jobs/{job_id}/pdf")
def get_pdf_split_raw(request: Any, job_id: UUID) -> HttpResponse:
    """获取原始 PDF 二进制流，供 PDF.js 在浏览器中渲染"""
    job = PdfSplitJobService().get_job(job_id)
    storage = PdfSplitStorage(job.id)
    if not storage.source_pdf_path.exists():
        return HttpResponse(status=404)
    return FileResponse(  # type: ignore[return-value]
        storage.source_pdf_path.open("rb"),
        content_type="application/pdf",
        filename=job.source_original_name or "document.pdf",
    )


@router.get("/jobs/{job_id}/preview-page")
def get_pdf_preview_page(
    request: Any,
    job_id: UUID,
    start_page: int = 1,
    end_page: int = 1,
    filename: str = "片段",
) -> HttpResponse:
    """返回PDF预览页面（HTML）"""
    from django.shortcuts import render

    job = PdfSplitJobService().get_job(job_id)
    storage = PdfSplitStorage(job.id)
    pdf_url = f"/api/v1/pdf-splitting/jobs/{job_id}/pdf"

    return render(
        request,
        "admin/pdf_splitting/pdf_preview.html",
        {
            "pdf_url": pdf_url,
            "start_page": start_page,
            "end_page": end_page,
            "filename": filename,
        },
    )
