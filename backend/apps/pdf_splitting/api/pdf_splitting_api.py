from __future__ import annotations

from typing import Any
from uuid import UUID

import pymupdf as fitz
from django.http import FileResponse, HttpResponse
from ninja import File, Form, Router
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.core.exceptions import ValidationException
from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.split.export_utils import export_segment_pdf
from apps.pdf_splitting.services.storage import PdfSplitStorage

router = Router(tags=["PDF 拆解"])


def _request_user(request: Any) -> Any:
    """提取请求用户（JWT 场景 request.user 已由认证器写入，兜底读 request.auth）。"""
    from apps.core.security.admin_access import get_request_user

    return get_request_user(request)


def _require_admin(request: Any) -> None:
    """提交服务器本地路径（source_path）属于跨租户读取面，收敛为管理员专用。"""
    from apps.core.security.admin_access import ensure_admin_request

    ensure_admin_request(request, message="无权限提交服务器本地路径", code="PERMISSION_DENIED")


class PositionedRectOut(BaseModel):
    """块在原页上的归一化矩形（0–1）。前端直接 ``left: x*100%`` 就能画。"""

    x: float
    y: float
    w: float
    h: float
    # True = 推出来的近似框（如 Office 整页框），不是原样量出来的
    approx: bool = False


class PositionedBlockOut(BaseModel):
    """可定位的正文块（识别定位用）。"""

    page: int
    type: str
    text: str
    rect: PositionedRectOut
    # Office 附带的结构定位（段落序 / 行列），对定位是确定的，矩形只是近似
    locator: dict[str, Any] | None = None


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
    # 该段正文的 Markdown 重建（版面块优先 / 纯文本兜底）；旧任务无产物时为空串
    content_md: str
    # 该段正文块 + 坐标（原文坐标索引对照）；无坐标的后端 / 旧任务为空列表
    positioned: list[PositionedBlockOut] = []
    # 该段的识别质量提示（跨页一致性校对命中的疑似错字等）。只是提示，不阻塞流程；
    # 旧任务无该产物时为空列表，前端整块不渲染。
    quality_flags: list[str] = []


class PdfSplitJobOut(BaseModel):
    """任务详情响应。

    命名必须带 PdfSplit 前缀：OpenAPI 组件按类名注册，与 doc_converter.JobOut
    同名会互相覆盖（后注册者胜出），导致该端点在快照里挂上错误 schema。
    """

    job_id: str
    status: str
    split_mode: str
    ocr_profile: str
    # 版面策略：fast_text（默认，不调云端）/ layout（电子页也上云端拿坐标与表格）
    layout_mode: str = "fast_text"
    # 解析平台：auto（优先+容灾）/ mineru / textin（锁定，失败不降级）
    cloud_backend: str = "auto"
    progress: int
    total_pages: int
    processed_pages: int
    current_page: int
    summary: dict[str, Any]
    segments: list[SegmentOut]
    download_url: str = ""
    pdf_url: str = ""
    error_message: str = ""
    # 存活信号（见 services/job_recovery.py）。
    # stale_seconds 为 null：非 processing 态，无需判活；
    # 为正整数：已静默这么多秒，前端可据此提示「可能已中断」。
    heartbeat_at: str | None = None
    updated_at: str | None = None
    stale_seconds: int | None = None


class PdfSplitJobSubmitOut(BaseModel):
    """任务提交响应（同上，避免与 doc_converter.JobSubmitOut 同名互踩）"""

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


@router.post("/extract-pages")
def extract_pdf_pages(
    request: Any,
    file: UploadedFile = File(...),
    page_start: int = Form(...),
    page_end: int = Form(...),
) -> HttpResponse:
    """从上传的 PDF 里按页范围切出一份小 PDF，回字节流。

    归案（材料包 → 案件材料）用：后端 CaseMaterial 只认「附件 + 类型名」，
    整包上传会让每份材料都指向同一份完整卷宗（164 页），律师开庭时翻不到
    具体材料。所以先在这里按分段切页，前端再把切好的小 PDF 上传成附件。

    入参：file（PDF 上传）+ page_start + page_end（1 起，含两端）。
    出参：application/pdf。
    """
    if page_start < 1:
        raise ValidationException(message="起始页必须从 1 开始", errors={"page_start": page_start})
    if page_end < page_start:
        raise ValidationException(message="结束页不能小于起始页", errors={"page_end": page_end})
    # 大小口径与 /jobs 共用 PdfSplitJobService.MAX_FILE_SIZE，避免两处上限漂移
    file_size = int(file.size or 0)
    if file_size <= 0:
        raise ValidationException(message="上传文件为空", errors={"file": "文件不能为空"})
    if file_size > PdfSplitJobService.MAX_FILE_SIZE:
        limit_mb = PdfSplitJobService.MAX_FILE_SIZE // 1024 // 1024
        raise ValidationException(message="文件大小超过限制", errors={"file": f"文件大小不能超过 {limit_mb}MB"})

    try:
        with fitz.open(stream=file.read(), filetype="pdf") as source_doc:
            total_pages = int(source_doc.page_count)
            if page_end > total_pages:
                raise ValidationException(
                    message="页范围超出文件页数",
                    errors={"page_end": page_end, "total_pages": total_pages},
                )
            # 切页逻辑只此一份（export_utils），本端点不重写
            pdf_bytes = export_segment_pdf(source_doc, page_start, page_end)
    except ValidationException:
        raise
    except (RuntimeError, ValueError):
        raise ValidationException(message="PDF 无法打开", errors={"file": "PDF 文件损坏或格式不正确"}) from None

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="pages_{page_start}-{page_end}.pdf"'
    return response


@router.post("/jobs", response=PdfSplitJobSubmitOut)
def create_pdf_split_job(  # pragma: no cover
    request: Any,
    file: UploadedFile | None = File(None),
    source_path: str | None = Form(None),
    template_key: str = Form("filing_materials_v1"),
    split_mode: str = Form("content_analysis"),
    ocr_profile: str = Form("balanced"),
    layout_mode: str = Form("fast_text"),
    cloud_backend: str = Form("auto"),
) -> PdfSplitJobSubmitOut:
    # 安全审计第4轮：source_path 直读服务器本地文件系统，仅管理员可提交；
    # 文件上传（file）仍对登录用户开放。
    if (source_path or "").strip():
        _require_admin(request)
    job = PdfSplitJobService().create_job(
        file=file,
        source_path=source_path,
        template_key=template_key,
        split_mode=split_mode,
        ocr_profile=ocr_profile,
        layout_mode=layout_mode,
        cloud_backend=cloud_backend,
        created_by=getattr(request, "user", None),
    )
    return PdfSplitJobSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/reusable-job", response=PdfSplitJobOut | None)
def find_reusable_pdf_split_job(
    request: Any, source_name: str, total_pages: int | None = None
) -> PdfSplitJobOut | None:  # pragma: no cover
    """查一份已算好的拆分任务，供前端跳过重跑直接复用。

    典型场景：材料包已识别过（后端有 36 段），但 `draft_state` 没回写——
    律师再点「自动识别」会从零重跑 164 页（几分钟 + 几十元）。
    前端打开阅读器时先调这个：命中就直接拉 segments，miss 才建新任务。

    返回 null 表示没有可复用的（前端照常新建）。
    """
    job = PdfSplitJobService().find_reusable_job(
        source_name=source_name,
        total_pages=total_pages,
        user=_request_user(request),
    )
    if job is None:
        return None
    return PdfSplitJobOut(**PdfSplitJobService().build_job_payload(job))


@router.get("/jobs/{job_id}", response=PdfSplitJobOut)
def get_pdf_split_job(request: Any, job_id: UUID) -> PdfSplitJobOut:  # pragma: no cover
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    payload = PdfSplitJobService().build_job_payload(job)
    return PdfSplitJobOut(**payload)


@router.get("/jobs/{job_id}/pages/{page_no}/preview")
def get_pdf_split_preview(request: Any, job_id: UUID, page_no: int) -> HttpResponse:  # pragma: no cover
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    preview_path = PdfSplitService().render_preview(job, page_no)
    return FileResponse(preview_path.open("rb"), content_type="image/png", filename=preview_path.name)  # type: ignore[return-value]


@router.post("/jobs/{job_id}/confirm", response=PdfSplitJobSubmitOut)
def confirm_pdf_split_job(
    request: Any, job_id: UUID, payload: ConfirmRequestIn
) -> PdfSplitJobSubmitOut:  # pragma: no cover
    job = PdfSplitJobService().confirm_segments(
        job_id=job_id, items=[item.model_dump() for item in payload.segments], user=_request_user(request)
    )
    return PdfSplitJobSubmitOut(job_id=str(job.id), status=job.status)


@router.post("/jobs/{job_id}/cancel", response=PdfSplitJobSubmitOut)
def cancel_pdf_split_job(request: Any, job_id: UUID) -> PdfSplitJobSubmitOut:  # pragma: no cover
    job = PdfSplitJobService().request_cancel(job_id=job_id, user=_request_user(request))
    return PdfSplitJobSubmitOut(job_id=str(job.id), status=job.status)


@router.get("/jobs/{job_id}/download")
def get_pdf_split_download(request: Any, job_id: UUID) -> HttpResponse:  # pragma: no cover
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    storage = PdfSplitStorage(job.id)
    if not storage.export_zip_path.exists():
        return HttpResponse(status=404)
    return FileResponse(storage.export_zip_path.open("rb"), content_type="application/zip", filename="split_result.zip")  # type: ignore[return-value]


@router.get("/jobs/{job_id}/pdf")
def get_pdf_split_raw(request: Any, job_id: UUID) -> HttpResponse:  # pragma: no cover
    """获取原始 PDF 二进制流，供 PDF.js 在浏览器中渲染"""
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    storage = PdfSplitStorage(job.id)
    if not storage.source_pdf_path.exists():
        return HttpResponse(status=404)
    return FileResponse(  # type: ignore[return-value]
        storage.source_pdf_path.open("rb"),
        content_type="application/pdf",
        filename=job.source_original_name or "document.pdf",
    )


@router.get("/jobs/{job_id}/preview-page")
def get_pdf_preview_page(  # pragma: no cover
    request: Any,
    job_id: UUID,
    start_page: int = 1,
    end_page: int = 1,
    filename: str = "片段",
) -> HttpResponse:
    """返回PDF预览页面（HTML）"""
    from django.shortcuts import render

    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
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
