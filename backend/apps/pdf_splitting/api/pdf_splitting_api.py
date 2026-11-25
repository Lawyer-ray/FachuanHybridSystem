from __future__ import annotations

from typing import Any
from uuid import UUID

import pymupdf as fitz
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from ninja import File, Form, Router
from ninja.files import UploadedFile
from pydantic import BaseModel, Field

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.http.download import build_download_response
from apps.core.security import get_request_access_context
from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.split.export_utils import export_segment_pdf
from apps.pdf_splitting.services.split.output_rotation import (
    apply_page_rotations,
    merge_page_rotations,
    parse_page_rotations,
)
from apps.pdf_splitting.services.split.page_fingerprint import page_signature as _page_signature
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


def _parse_segment_ids(raw: str) -> list[int] | None:
    """解析 ``?ids=12,15`` → ``[12, 15]``；空串/缺省返回 None（＝整包）。

    只接受 ASCII 数字 token。为什么这么严：这个值直通 ``id`` 过滤，放宽成
    「任意字符塞进去再由 ORM 容错」等于把查询拼接权交给调用方；其次空 token
    （``ids=1,,2`` / 尾逗号）也当场拒——静默丢掉一个空段，与静默跳过不存在的
    id 是同一种错：律师只会看到「选中的都打进去了」的错觉。
    """
    text = (raw or "").strip()
    if not text:
        return None
    tokens = [token.strip() for token in text.split(",")]
    invalid = [token for token in tokens if not (token.isascii() and token.isdigit())]
    if invalid:
        raise ValidationException(
            message=f"ids 参数不合法：{', '.join(repr(token) for token in invalid)}",
            errors={"ids": invalid},
        )
    return [int(token) for token in tokens]


def _segment_pdf_and_signatures(
    source_doc: fitz.Document, segment: ArchiveSegmentIn, *, index: int, total_pages: int
) -> tuple[bytes, list[list[float]]]:
    """按页区间切一份 PDF，并逐页算指纹（副本判定的入参）。

    页区间必须在这里校验：越界在 ``export_segment_pdf`` 里只会静默切出空页，
    归档后就变成「一份只有封面的起诉状」，比 400 难查得多。
    """
    if segment.page_start < 1 or segment.page_end < segment.page_start:
        raise ValidationException(
            message=f"第 {index + 1} 段页区间不合法",
            errors={"segments": f"[{index}] {segment.page_start}-{segment.page_end}"},
        )
    if segment.page_end > total_pages:
        raise ValidationException(
            message=f"第 {index + 1} 段页区间超出文件页数",
            errors={"segments": f"[{index}] {segment.page_end} > {total_pages}"},
        )
    # 切页只有一份实现（export_utils）——归档不能有第二套页边界口径
    content = export_segment_pdf(source_doc, segment.page_start, segment.page_end)
    signatures = [
        _page_signature(source_doc[page_no - 1]) for page_no in range(segment.page_start, segment.page_end + 1)
    ]
    return content, signatures


class PositionedRectOut(BaseModel):
    """块在原页上的归一化矩形（0–1）。前端直接 ``left: x*100%`` 就能画。"""

    x: float
    y: float
    w: float
    h: float
    # True = 推出来的近似框（如 Office 整页框），不是原样量出来的
    approx: bool = False
    # 精度等级：三档而不是单一布尔。
    #
    # 为什么 ``approx`` 不够：它同时表示「整页近似」（整张表没拆，坐标基本无意义）
    # 与「半格误差」（表格均分出来的格/行，左右列对齐、纵向行高不均）——两者可信度
    # 差一个数量级，前端却只能画同一种虚线。拆成三档后视觉才能分开：
    #   exact = 引擎真实返回的 bbox（可信，实线）
    #   cell  = 表格拆分的推算框（半格误差，虚线 + ≈）
    #   page  = 整页近似（更淡的虚线）
    # ``approx`` 保留是为了向后兼容（老前端只读它）。
    precision: str = "exact"


class PositionedBlockOut(BaseModel):
    """可定位的正文块（识别定位用）。"""

    page: int
    type: str
    text: str
    rect: PositionedRectOut
    # Office 附带的结构定位（段落序 / 行列），对定位是确定的，矩形只是近似
    locator: dict[str, Any] | None = None
    # 整表未拆时透出的结构信息：前端据此告诉律师「这是一张 52 行的表」，
    # 而不是让他以为点中的是某一行。已拆分的块不带这两个字段。
    table_rows: int | None = None
    table_cols: int | None = None


class SegmentPageSpanOut(BaseModel):
    """一段正文里属于某一页的字符区间（相对 ``content_md``，左闭右开）。

    前端切/并段时按它把正文按页搬运，而不是整段照抄（污染）或整段丢弃（丢失）。
    """

    page: int
    start: int
    end: int


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
    # 该段正文的页锚点（content_md 字符区间 → 页号）；旧任务无该产物时为空列表，
    # 前端按「没有锚点」降级。字段名固定为 page_spans，前端按它映射 pageSpans。
    page_spans: list[SegmentPageSpanOut] = []


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
    # 交叉比对引擎（逗号分隔，如 `mineru,paddleocr_vl`）；空串表示不跑比对。
    # 与 cloud_backend 无关：它不决定取字用谁，只表示「另外再跑哪几个引擎比对」。
    dual_engines: str = ""
    progress: int
    total_pages: int
    processed_pages: int
    current_page: int
    # 当前执行阶段：extract（取字）/ cross_check（交叉比对）/ segment（分段）/ done。
    #
    # 为什么前端必须拿到它：取字做完时 progress 已经是 100、processed_pages 也满了，
    # 之后的交叉比对（十几分钟）与分段（4-8 分钟）全程都是 100——没有 stage，
    # 界面上就是「100% 假死」。默认给 extract 是为了兼容老任务（stage 字段刚加时
    # 存量行都是 extract）。
    stage: str = "extract"
    # 任务起止时间与已耗时（秒）。elapsed_seconds 在终态后**停止增长**，
    # 前端直接显示即可；started_at 缺失时为 None（未开始或老数据）。
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: int | None = None
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


class ArchiveSegmentIn(BaseModel):
    """一段要归到案件文件夹的材料：页区间 + 文书名 + 材料类型。"""

    page_start: int
    page_end: int
    #: 文书名（如「传统起诉状」），进文件名的括号前那一段
    doc_type: str
    #: 材料类型（一般是任务的 segment_type），决定落到案件文件夹的哪一层
    material_type: str
    #: 人工转正角度编码 ``"页码:角度,页码:角度"``（页码=源 PDF 绝对页号，角度=在
    #: 页自身 /Rotate 之上再顺时针多少度）。空串 = 不转；脏 token/越界页忽略并告警。
    rotations: str = ""


class ArchiveToCaseFolderIn(BaseModel):
    case_id: int
    segments: list[ArchiveSegmentIn]
    #: 文件名里的日期段（YYYYMMDD）；null/缺省取今天
    date: str | None = None
    #: False = 副本**不落盘**，但仍出现在响应的 duplicates 里（调用方据此提示
    #: 「另有 N 份未写入」）
    write_duplicates: bool = True


class ArchiveWrittenOut(BaseModel):
    filename: str
    subdir: str
    is_duplicate: bool
    #: 落盘后的绝对路径：前端 toast / 打开目录要用，不参与文件名展示
    absolute_path: str = ""


class ArchiveSkippedOut(BaseModel):
    doc_type: str
    reason: str


class ArchiveToCaseFolderOut(BaseModel):
    root: str
    written: list[ArchiveWrittenOut]
    #: 副本分组：每组的 doc_type 序列（组内第一个是正本）
    duplicates: list[list[str]]
    #: 没落盘的分段与原因（如「未匹配到子目录」）
    skipped: list[ArchiveSkippedOut]
    #: 归档说明文件的绝对路径；没生成时为 null
    notice_path: str | None = None


@router.post("/extract-pages")
def extract_pdf_pages(
    request: Any,
    file: UploadedFile = File(...),
    page_start: int = Form(...),
    page_end: int = Form(...),
    rotations: str = Form(""),
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
            # 人工转正必须在切页**之前**烧进页对象：insert_pdf 复制的是页对象，
            # /Rotate 跟着走；切完再改已经来不及（切页逻辑只此一份，见 export_utils）
            apply_page_rotations(source_doc, parse_page_rotations(rotations))
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
    dual_engines: str = Form(""),
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
        dual_engines=dual_engines,
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


@router.get("/inflight-job", response=PdfSplitJobOut | None)
def find_inflight_pdf_split_job(
    request: Any, source_name: str, total_pages: int | None = None
) -> PdfSplitJobOut | None:
    """查一份**正在进行中**的拆分任务，供前端接管轮询。

    典型场景：任务是由同事的浏览器、脚本或刷新前那个页面发起的，当前页面毫
    不知情。不查就再建一个，同一份 164 页卷宗会并行跑两遍（钱翻倍），而先前
    那个任务在界面上完全不存在（“幽灵任务”）。

    返回 null 表示没有进行中的（前端照常新建）。
    """
    # S31-02（2026-11-23 二轮审计）：原实现不传 user，服务侧也不按 created_by 过滤，
    # 于是知道对方的文件名 + 页数就能拉到他人任务的 payload（含已落库的 content_md）。
    # 现在与 find_reusable_job / get_job 同口径：只认自己的任务（管理员全量）。
    job = PdfSplitJobService().find_inflight_job(
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


@router.post("/jobs/{job_id}/archive-to-case-folder", response=ArchiveToCaseFolderOut)
def archive_pdf_split_to_case_folder(
    request: Any, job_id: UUID, payload: ArchiveToCaseFolderIn
) -> ArchiveToCaseFolderOut:
    """把拆分结果按段切页，直接写进案件的绑定文件夹（不经浏览器上传往返）。

    与 ``/extract-pages`` + 前端上传的分工：那条链路每份材料都要过一次上传，
    几十段就是几十次往返；这条在服务端切片 + 命名 + 落盘，前端只给「每段用
    哪个文书名 / 材料类型」。命名、版本对齐（docx 是 V4、扫描件也是 V4，不是 V5）、
    副本识别都在 ``apps.cases.services.material`` 侧（见 scan_archive_naming）。

    页指纹随材料一起交给归档服务：副本靠它比对，不能靠文件名——「起诉状_1.pdf」
    与「起诉状(1).pdf」既可能是同一份的两个扫件，也可能是两份不同材料。
    """
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    if not payload.segments:
        raise ValidationException(message="没有可归档的分段", errors={"segments": "至少需要一个分段"})

    # 延迟导入：cases 侧的归档服务是本模块唯一的跨 app 依赖，放在函数内与
    # _request_user / _require_admin 同风格，也让两个 app 的 import 不互相绑架。
    from apps.cases.services.material.case_material_archive_service import ArchiveItem, CaseMaterialArchiveService

    storage = PdfSplitStorage(job.id)
    if not storage.source_pdf_path.exists():
        raise NotFoundError(message="任务缺少原始 PDF，无法归档", errors={"job_id": str(job.id)})

    date = (payload.date or "").strip() or timezone.localdate().strftime("%Y%m%d")
    ctx = get_request_access_context(request)

    items: list[Any] = []
    with fitz.open(storage.source_pdf_path) as source_doc:
        total_pages = int(source_doc.page_count)
        # 一份 source_doc 复用给所有段、且页指纹也在同一份文档上算（page_signature
        # 走 get_pixmap，会吃 /Rotate）。所以角度必须**先合并成一张表、apply 一次**，
        # 再切页与算指纹——逐段 apply 会让先切出的段与后算的指纹方向不一致。
        apply_page_rotations(source_doc, merge_page_rotations(seg.rotations for seg in payload.segments))
        for index, segment in enumerate(payload.segments):
            content, signatures = _segment_pdf_and_signatures(source_doc, segment, index=index, total_pages=total_pages)
            items.append(
                ArchiveItem(
                    doc_type=segment.doc_type,
                    material_type=segment.material_type,
                    content=content,
                    page_signatures=signatures,
                )
            )

    # 案件 ACL、命名、副本分组、落盘全在归档服务内；这里只透传 ctx 与结果
    result = CaseMaterialArchiveService().archive(
        case_id=payload.case_id,
        items=items,
        date=date,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        write_duplicates=payload.write_duplicates,
    )
    return ArchiveToCaseFolderOut(
        root=result.root,
        written=[
            ArchiveWrittenOut(
                filename=item.filename,
                subdir=item.subdir,
                is_duplicate=item.is_duplicate,
                absolute_path=item.absolute_path,
            )
            for item in result.written
        ],
        duplicates=result.duplicates,
        skipped=[ArchiveSkippedOut(**entry) for entry in result.skipped],
        notice_path=result.notice_path,
    )


@router.get("/jobs/{job_id}/segments/{segment_id}/pdf")
def get_pdf_split_segment_pdf(request: Any, job_id: UUID, segment_id: int, rotations: str = "") -> HttpResponse:
    """单段 PDF 下载（Content-Disposition: attachment）。

    单个下载 / 多选下载 / 整包下载共用同一份切页与命名实现（见
    ``PdfSplitService.build_download_*``），否则「单下的那份」与「包里那份」
    会在页边界或文件名上对不上。
    """
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    content, filename = PdfSplitService().build_download_pdf(job, segment_id, rotations=rotations)
    return build_download_response(content, filename, "application/pdf")


@router.get("/jobs/{job_id}/segments/{segment_id}/md")
def get_pdf_split_segment_markdown(request: Any, job_id: UUID, segment_id: int) -> HttpResponse:
    """单段 Markdown 下载：与同一段的 PDF 同名（只差扩展名），律所归案时成对存放。"""
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    content, filename = PdfSplitService().build_download_markdown(job, segment_id)
    return build_download_response(content.encode("utf-8"), filename, "text/markdown; charset=utf-8")


@router.get("/jobs/{job_id}/download")
def get_pdf_split_download(request: Any, job_id: UUID, ids: str = "", rotations: str = "") -> HttpResponse:
    """整包 / 多选打包下载（zip，平铺）：每段一份 pdf + 一份同名 md。

    不带 ``ids`` 就是原来的整包（向后兼容，只是包里多了 md）；带 ``ids``（段
    **主键**，逗号分隔）只打选中的段，非法或不属于本任务的 id 整体 400。
    打包在 Service 现算而不是回读 ``exports/split_result.zip``：那份可能是本次
    上线前导出的（没有 md），直接发出去就是「整包缺 md」——而这次需求的核心恰恰
    是每份 pdf 必须配一份 md。
    """
    job = PdfSplitJobService().get_job(job_id, user=_request_user(request))  # 安全审计第4轮：校验任务属主
    package = PdfSplitService().build_download_zip(job=job, segment_ids=_parse_segment_ids(ids), rotations=rotations)
    if package is None:
        # 没段可打：沿用旧 /download 的契约（404 + 空响应体），不要把半个包发出去。
        return HttpResponse(status=404)
    content, filename = package
    return build_download_response(content, filename, "application/zip")


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
