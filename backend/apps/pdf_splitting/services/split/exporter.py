"""导出 / 下载 / 预览打包：整包导出、单段 pdf、单段 md、多选 zip、预览图渲染。

从 ``split/service.py``（原 1196 行）外移的一整块：这些函数只读「任务 + 段 + 存储目录」，
不持有 ``PdfSplitService`` 的实例状态，因此下沉为模块级函数；``PdfSplitService`` 上的
同名方法保留为一行委托，既有调用方（``tasks.py`` / API 层 / 单测）按方法名照旧可用。
本模块不 import ``service``，依赖方向单向：``service → exporter``。
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

import pymupdf as fitz
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import sanitize_upload_filename
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSegment
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_default_filename

from .export_utils import deduplicate_filename, export_segment_pdf
from .markdown_builder import load_segment_markdown_map
from .output_rotation import apply_page_rotations, parse_page_rotations

logger = logging.getLogger("apps.pdf_splitting")

#: 段 PDF 渲染函数（``export_utils.export_segment_pdf``）。作为入参透传而不是直接闭包，
#: 是为了保住 ``split.service.export_segment_pdf`` 这个打桩接缝：单测按它统计「实际渲了几段」。
SegmentPdfRenderer = Callable[[fitz.Document, int, int], bytes]


#: 段文件名里的旧扩展名（.pdf / .md）—— 打包时名字统一由本模块重生，
#: 两种后缀都得先剥掉，否则同一个段会落成 ``01_起诉状.pdf.pdf``。
_SEGMENT_SUFFIX_RE = re.compile(r"\.(?:pdf|md)$", re.IGNORECASE)


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """条目列表 → zip 字节。

    集中一处是为了让「整包 / 多选 / 导出任务落盘」三条路径的压缩参数
    （deflate、平铺、不写目录项）只有一个口径：任何一条路径单独变化，
    律师拿到的包结构就会和界面上看到的段列表对不上。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in entries:
            archive.writestr(filename, content)
    return buffer.getvalue()


# ==================================================================
# 后台导出任务
# ==================================================================


def export_job(job: PdfSplitJob, *, render_pdf: SegmentPdfRenderer = export_segment_pdf) -> None:  # pragma: no cover
    """后台导出任务：把整包写到 ``exports/split_result.zip``（供旧调用方直接取文件）。

    包内现在也带 md（与 ``build_download_zip`` 用同一套条目构造），否则
    「后台导出出来的包」与「端点下载的包」内容不一致——同一份卷宗两个下载
    入口给不一样的东西，用户无法判断哪个是完整的。

    进度与取消保留在原位：整包渲 93 页虽然只需秒级，但几十段的导出仍可能
    放在慢盘上，律师点「取消」必须能停。
    """
    storage = PdfSplitStorage(job.id)
    storage.ensure_dirs()
    segments = _download_segments(job=job, segment_ids=None)
    if not segments:
        # 后台任务没有「空响应」这条路：它就是失败，任务会被标 failed 并写明原因，
        # 不能像下载端点那样静默回 404。
        raise ValueError("没有可导出的片段")

    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.EXPORTING,
        progress=0,
        error_message="",
    )

    entries: list[tuple[str, bytes]] = []
    markdown_by_order = load_segment_markdown_map(storage.segments_md_path)
    with fitz.open(storage.source_pdf_path) as source_doc:
        total = len(segments)
        seen_names: set[str] = set()
        ordinals = _ordinals_in_job(job)
        for index, segment in enumerate(segments, start=1):
            job.refresh_from_db(fields=["cancel_requested"])
            if job.cancel_requested:
                PdfSplitJob.objects.filter(id=job.id).update(
                    status=PdfSplitJobStatus.CANCELLED,
                    finished_at=timezone.now(),
                )
                return

            entries.extend(
                _segment_zip_entries(
                    source_doc,
                    segment,
                    seq=ordinals.get(segment.id, index),
                    markdown_by_order=markdown_by_order,
                    seen_names=seen_names,
                    render_pdf=render_pdf,
                )
            )

            progress = int(index * 100 / total)
            PdfSplitJob.objects.filter(id=job.id).update(progress=progress)

    storage.save_overwrite(storage.export_zip_path, ContentFile(_zip_bytes(entries)))


# ==================================================================
# 下载产物（单段 pdf / 单段 md / 整包与多选 zip）
# ==================================================================


def build_download_pdf(job: PdfSplitJob, segment_id: int, *, rotations: str = "") -> tuple[bytes, str]:
    """单段 PDF：返回 ``(pdf 字节, 安全文件名)``。

    文件名只由「数据库里的段名 → sanitize → 本模块重生扩展名」构成，
    不接受任何客户端拼串（否则 ``../`` 与引号就能穿进 Content-Disposition）。
    """
    segment = _get_segment(job=job, segment_id=segment_id)
    storage = PdfSplitStorage(job.id)
    if not storage.source_pdf_path.exists():
        raise NotFoundError(
            message="原始 PDF 不存在，无法切出该分段",
            code="PDF_SPLIT_SOURCE_MISSING",
            errors={"segment_id": segment_id},
        )
    with fitz.open(storage.source_pdf_path) as source_doc:
        # 人工转正先烧进页对象再切：insert_pdf 复制页对象，/Rotate 跟着走
        apply_page_rotations(source_doc, parse_page_rotations(rotations))
        pdf_bytes = export_segment_pdf(source_doc, segment.page_start, segment.page_end)
    return pdf_bytes, f"{_segment_stem(segment)}.pdf"


def build_download_markdown(job: PdfSplitJob, segment_id: int) -> tuple[str, str]:
    """单段 Markdown：返回 ``(markdown 文本, 安全文件名)``。

    正文取 ``segments_md.json`` 里那一段——即律师在界面上看到的 ``content_md``
    本人，不是现场重算的近似物。该段没有 md 产物（旧任务 / 该段没取到字）时
    404 而不是回空文件：空 md 看起来像「下载成功但内容是空的」，比明确报错
    更难排查。
    """
    segment = _get_segment(job=job, segment_id=segment_id)
    markdown_by_order = load_segment_markdown_map(PdfSplitStorage(job.id).segments_md_path)
    markdown = markdown_by_order.get(segment.order) or ""
    if not markdown.strip():
        raise NotFoundError(
            message="该分段没有 Markdown 产物",
            code="PDF_SPLIT_SEGMENT_MD_NOT_FOUND",
            errors={"segment_id": segment_id, "order": segment.order},
        )
    return markdown, f"{_segment_stem(segment)}.md"


def build_download_zip(
    job: PdfSplitJob,
    *,
    segment_ids: list[int] | None = None,
    rotations: str = "",
    render_pdf: SegmentPdfRenderer = export_segment_pdf,
) -> tuple[bytes, str] | None:
    """整包 / 多选打包：返回 ``(zip 字节, zip 文件名)``，包内**平铺**且每段配同名 md。

    ``segment_ids`` 为 ``None`` 时是整包（与既有 ``/download`` 语义一致，只是
    包里多了 md）；给值时只渲选中的段——未选中的段**不渲**，否则多选下载的耗时
    与整包一样，勾 3 段要等 93 页。

    返回 ``None`` 而不是抛异常表示「没有可打包的段」：旧 ``/download`` 对
    「产物缺失」的契约是 **404 + 空响应体**（不能把半个包发给律师），API 层据此
    直接回空 404 即可，不必为它写 try/except。
    """
    segments = _download_segments(job=job, segment_ids=segment_ids)
    if not segments:
        return None
    storage = PdfSplitStorage(job.id)
    if not storage.source_pdf_path.exists():
        return _fallback_archive(job=job, storage=storage, segment_ids=segment_ids)

    markdown_by_order = load_segment_markdown_map(storage.segments_md_path)
    ordinals = _ordinals_in_job(job)
    entries: list[tuple[str, bytes]] = []
    seen_names: set[str] = set()
    with fitz.open(storage.source_pdf_path) as source_doc:
        # 包内所有段共用这一份源文档：角度一次 apply 到位（页级属性，与段无关）
        apply_page_rotations(source_doc, parse_page_rotations(rotations))
        for segment in segments:
            entries.extend(
                _segment_zip_entries(
                    source_doc,
                    segment,
                    seq=ordinals.get(segment.id, 1),
                    markdown_by_order=markdown_by_order,
                    seen_names=seen_names,
                    render_pdf=render_pdf,
                )
            )
    return _zip_bytes(entries), _zip_filename(segment_ids)


def _fallback_archive(
    *, job: PdfSplitJob, storage: PdfSplitStorage, segment_ids: list[int] | None
) -> tuple[bytes, str]:
    """源 PDF 已不在时的降级：整包请求回历史整包，多选请求明确报错。

    为什么整包可以回旧包：``/download`` 以前就是「文件在就给文件」，源 PDF 被
    清理后旧整包仍在的存量任务是真实存在的；把它们从 200 变成 404 是回归。
    但旧包可能没有 md，所以记一条 warning——这是唯一会出现「pdf 配不上 md」
    的入口，日志里必须能查到原因。

    多选做不了同样的降级：历史整包是**整包**，拿它当「只选中几段」返回等于
    把没勾的材料也塞给律师，比报错更糟。
    """
    if segment_ids is None and storage.export_zip_path.exists():
        logger.warning(
            "pdf_split_download_source_missing",
            extra={"job_id": str(job.id), "fallback": "persisted_zip"},
        )
        return storage.export_zip_path.read_bytes(), _zip_filename(None)
    raise NotFoundError(
        message="原始 PDF 不存在，无法重新打包",
        code="PDF_SPLIT_SOURCE_MISSING",
        errors={"job_id": str(job.id)},
    )


def _zip_filename(segment_ids: list[int] | None) -> str:
    """zip 的下载名：整包沿用旧名 ``split_result.zip``，多选另取一个。

    不改整包文件名是为了向后兼容（脚本/旧前端按名字认产物）；多选单独命名
    则让律师在下载目录里能一眼分辨「这是我勾的几段」还是「整包」。
    """
    return "split_result.zip" if segment_ids is None else "split_result_selected.zip"


def _download_segments(*, job: PdfSplitJob, segment_ids: list[int] | None) -> list[PdfSplitSegment]:
    """本次要打包的段（按卷宗顺序）。

    ``ids`` 校验规则：每个 id 都必须是**该任务**的段主键，有一个不合法就整体
    400 并列出是哪些——不静默跳过。律师勾了 12 段、包里只有 10 段时，他无法
    从界面上看出少了哪两段；整包悄悄缺页是这类卷宗工具最坏的失败模式。
    """
    segments = list(job.segments.order_by("order", "id"))
    if segment_ids is None:
        return segments
    # 显式选中但一段也取不到（任务没有段 / ids 是空表）→ 回空表，由调用方决定
    # 怎么反应：下载端点回空 404（旧契约），后台导出任务报失败。同一个「没东西
    # 可打」在两个入口的正确反应不同。
    if not segments:
        return []

    by_id = {segment.id: segment for segment in segments}
    unknown = [segment_id for segment_id in segment_ids if segment_id not in by_id]
    if unknown:
        raise ValidationException(
            message=f"以下分段不属于该任务：{', '.join(str(item) for item in unknown)}",
            errors={"ids": unknown},
        )
    # dict.fromkeys 去重：前端可能把同一段拼接进 ids 两次，同一份材料在包里
    # 出现两遍只会被当成「重复上传」；再按 order 排序，包内顺序恒等于卷宗顺序。
    selected = [by_id[segment_id] for segment_id in dict.fromkeys(segment_ids)]
    return sorted(selected, key=lambda segment: (int(segment.order or 0), int(segment.id or 0)))


def _get_segment(*, job: PdfSplitJob, segment_id: int) -> PdfSplitSegment:
    """取本任务的某一段；不存在（含其他任务的段）一律 404。

    走 ``job.segments`` 而不是 ``PdfSplitSegment.objects``：段归属由任务关系定，
    拿别人的段主键来试本来就该按「不存在」处理，不该泄露它是否存在。
    """
    segment = job.segments.filter(id=segment_id).first()
    if segment is None:
        raise NotFoundError(
            message="分段不存在",
            code="PDF_SPLIT_SEGMENT_NOT_FOUND",
            errors={"segment_id": segment_id},
        )
    return segment


def _ordinals_in_job(job: PdfSplitJob) -> dict[int, int]:
    """段主键 → 该段在**整卷**里的 1 起序号（与是否多选无关）。

    为什么不直接用 ``segment.order``：它的起始值取决于写入侧（实测真实任务从 0
    起），补零后包内会出现 ``00_`` —— 律师看到会以为编号错乱。也不按「包内第几个」
    编号：勾了第 1、3 段时，``01_起诉状`` / ``03_证据目录`` 比 ``01_`` / ``02_``
    多保住一个信息——这两份在整卷里是第几段。卷宗顺序由排序保证，与下载顺序无关。
    """
    ordered = job.segments.order_by("order", "id").values_list("id", flat=True)
    return {segment_id: index for index, segment_id in enumerate(ordered, start=1)}


def _segment_zip_entries(
    source_doc: fitz.Document,
    segment: PdfSplitSegment,
    *,
    seq: int,
    markdown_by_order: dict[int, str],
    seen_names: set[str],
    render_pdf: SegmentPdfRenderer = export_segment_pdf,
) -> list[tuple[str, bytes]]:
    """一段 → zip 条目列表（``[pdf]`` 或 ``[pdf, md]``）。

    缺 md 时降级为只放 pdf + 一条 warning，绝不因此让整包失败：md 是这次
    新加的产物，旧任务/未取到字的段本来就没有；因为一个副产物让律师拿不到
    已经切好的 pdf，是把主产物赔给附属产物。
    """
    # 前缀取**本次导出集合内**的 1 起序号，不取 ``segment.order``：后者的起始值
    # 取决于写入侧（实测真实任务从 0 起），直接拿来补零会让包内出现 ``00_`` 前缀，
    # 律师看到会以为是编号错乱。这个名字只用于包内排序，与卷宗顺序由入参保证。
    pdf_name = deduplicate_filename(f"{seq:02d}_{_segment_stem(segment)}.pdf", seen_names)
    entries: list[tuple[str, bytes]] = [(pdf_name, render_pdf(source_doc, segment.page_start, segment.page_end))]
    markdown = markdown_by_order.get(segment.order) or ""
    if not markdown.strip():
        logger.warning(
            "pdf_split_export_markdown_missing",
            extra={"job_id": str(segment.job_id), "segment_id": segment.id, "order": segment.order},
        )
        return entries
    # md 名跟 pdf 名同 stem（含去重后的 ``_2`` 尾巴）：一个 pdf 配一个同名 md
    # 是这次需求的核心，两边各算一次名字迟早会劈叉。
    entries.append((Path(pdf_name).with_suffix(".md").name, markdown.encode("utf-8")))
    return entries


def _segment_stem(segment: PdfSplitSegment) -> str:
    """段的展示名 stem（去扩展名、已安全化）。

    名字只来自数据库字段 + ``sanitize_upload_filename``，任何客户端输入都不参与
    ——pdf/md 的下载名与 zip 条目名都从这里出。
    """
    safe = sanitize_upload_filename(segment.filename or get_default_filename(segment.segment_type))
    stem = _SEGMENT_SUFFIX_RE.sub("", safe).strip(" .")
    return stem or "片段"


def render_preview(job: PdfSplitJob, page_no: int, *, dpi: int) -> Path:  # pragma: no cover
    storage = PdfSplitStorage(job.id)
    preview_path = storage.preview_path(page_no)
    if preview_path.exists():
        return preview_path

    with fitz.open(storage.source_pdf_path) as doc:
        if page_no < 1 or page_no > doc.page_count:
            raise ValueError("页码超出范围")
        page = doc.load_page(page_no - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        storage.save_overwrite(preview_path, ContentFile(pix.tobytes("png")))
    return preview_path
