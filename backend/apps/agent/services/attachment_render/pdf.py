"""PDF 页图渲染：页粒度文字层判断 + dpi 降档 + 长边/字节双限。"""

from __future__ import annotations

import io
import logging
from typing import Any

from .cache import _cache_lookup, _cache_store
from .types import MAX_EDGE_PX, MAX_PAGE_BYTES, RenderedPage, RenderError, RenderStrategy

logger = logging.getLogger(__name__)

#: 降 dpi 的档位（从高到低）。300 是印刷件细节底线，72 是「能看出有这页」的底线。
DPI_LADDER = (300, 200, 150, 120, 96, 72)
#: 页文字层判定阈值：短于这个字符数的页当作扫描页。
#: 取 50 是因为真实电子页几乎不会只有几十字（标题页例外，但标题页用图也无害，
#: 而无文字层的扫描页渲染出来才对模型有价值——宁可多渲染一页，不可漏页）。
MIN_TEXT_CHARS = 50


def render_pdf_pages(
    file_bytes: bytes,
    pages: list[int],
    *,
    attachment_id: str = "",
    dpi: int = 200,
    fmt: str = "png",
    use_cache: bool = True,
    size_limit: int = MAX_PAGE_BYTES,
    edge_limit: int = MAX_EDGE_PX,
    ladder: tuple[int, ...] = DPI_LADDER,
) -> list[RenderedPage]:
    """把 PDF 指定页渲染为图片，逐页返回（含失败页）。

    流程：打开 → 页粒度文字层判断 → 需要图的页按 ``dpi`` 渲染 → 超长边等比
    降采样 → 超字节上限按 ``ladder`` 逐档降 dpi 重渲染 → 仍超限标 ``too_large``。
    """
    doc = _open_pdf(file_bytes)
    if isinstance(doc, RenderedPage):
        # 整份打不开（加密/损坏）：每一页都带上同样的原因，页数不丢
        return [
            RenderedPage(page_no=p, strategy=RenderStrategy.PAGE_IMAGE, error=doc.error, detail=doc.detail)
            for p in pages
        ]

    try:
        results: list[RenderedPage] = []
        for page_no in pages:
            if page_no > doc.page_count:
                results.append(
                    RenderedPage(
                        page_no=page_no,
                        strategy=RenderStrategy.PAGE_IMAGE,
                        error=RenderError.PAGE_OUT_OF_RANGE,
                        detail=f"文档只有 {doc.page_count} 页",
                    )
                )
                continue
            results.append(
                _render_one_pdf_page(
                    doc,
                    page_no,
                    attachment_id=attachment_id,
                    dpi=dpi,
                    fmt=fmt,
                    use_cache=use_cache,
                    size_limit=size_limit,
                    edge_limit=edge_limit,
                    ladder=ladder,
                )
            )
        return results
    finally:
        doc.close()


def _open_pdf(file_bytes: bytes) -> Any:
    """打开 PDF；打不开或加密未解密时返回一个「只带错误」的 ``RenderedPage`` 作哨兵。"""
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("PDF 打开失败: %s", exc)
        return RenderedPage(
            page_no=0,
            strategy=RenderStrategy.PAGE_IMAGE,
            error=RenderError.UNSUPPORTED_MIME,
            detail=f"不是可解析的 PDF：{exc}",
        )
    if not doc.needs_pass:
        return doc

    # 无口令的「权限加密」PDF 很常见（下载站批量化加水印），authenticate("") 能过。
    # 空串都过不了说明真需要口令——不要尝试爆破，直接告诉用户原因。
    if doc.authenticate(""):
        return doc
    doc.close()
    return RenderedPage(
        page_no=0,
        strategy=RenderStrategy.PAGE_IMAGE,
        error=RenderError.ENCRYPTED,
        detail="PDF 需要打开口令，未解密无法读取内容",
    )


def _render_one_pdf_page(
    doc: Any,
    page_no: int,
    *,
    attachment_id: str,
    dpi: int,
    fmt: str,
    use_cache: bool,
    size_limit: int,
    edge_limit: int,
    ladder: tuple[int, ...],
) -> RenderedPage:
    page = doc.load_page(page_no - 1)
    text = (page.get_text() or "").strip()
    if len(text) >= MIN_TEXT_CHARS:
        # 有文字层：模型读文本比读图更快更准（且不烧视觉 token）
        return RenderedPage(page_no=page_no, strategy=RenderStrategy.TEXT, text=text)

    tried: list[int] = []
    # 首轮用调用方要求的 dpi，其后按阶梯降档；阶梯里比要求值更高的档跳过
    # （用户选了 150 就没必要先用 300 渲染一遍）。
    candidates = [int(dpi)] + [d for d in ladder if d < int(dpi)]
    for candidate in candidates:
        tried.append(candidate)
        cached = _cache_lookup(attachment_id, page_no, candidate, fmt) if use_cache else None
        if cached is not None:
            return _page_from_image(
                page_no,
                cached[0],
                cached[1],
                cached[2],
                mime=_fmt_mime(fmt),
                dpi=candidate,
                cached=True,
            )

        image_bytes, width, height = _rasterize(page, candidate, fmt, edge_limit)
        if len(image_bytes) > size_limit:
            continue
        if use_cache and attachment_id:
            _cache_store(attachment_id, page_no, candidate, fmt, image_bytes, width, height)
        return _page_from_image(page_no, image_bytes, width, height, mime=_fmt_mime(fmt), dpi=candidate, cached=False)

    return RenderedPage(
        page_no=page_no,
        strategy=RenderStrategy.PAGE_IMAGE,
        dpi=tried[-1] if tried else 0,
        error=RenderError.TOO_LARGE,
        detail=f"该页在 dpi={tried} 各档下均超过 {size_limit // 1024}KB 上限",
    )


def _rasterize(page: Any, dpi: int, fmt: str, edge_limit: int) -> tuple[bytes, int, int]:
    """渲染一页并按长边上限等比降采样，返回 ``(bytes, width, height)``。

    降采样用 Pillow 的 LANCZOS：PyMuPDF 直接按更小 dpi 重渲染在文字上更锐利，
    但「已经是最高档 dpi 还超长边」时只能后缩（否则要反向猜一个正好 1568 的 dpi），
    两者在视觉上对模型等价。
    """
    pix = page.get_pixmap(dpi=dpi)
    width, height = pix.width, pix.height
    if max(width, height) <= edge_limit:
        return pix.tobytes(fmt), width, height

    from PIL import Image

    scale = edge_limit / max(width, height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image = Image.frombytes("RGB", (width, height), pix.samples).resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG" if fmt == "jpeg" else "PNG", **({"quality": 85} if fmt == "jpeg" else {}))
    return buf.getvalue(), new_size[0], new_size[1]


def _page_from_image(
    page_no: int,
    image_bytes: bytes,
    width: int,
    height: int,
    *,
    mime: str,
    dpi: int,
    cached: bool,
) -> RenderedPage:
    return RenderedPage(
        page_no=page_no,
        strategy=RenderStrategy.PAGE_IMAGE,
        mime=mime,
        image_bytes=image_bytes,
        width=width,
        height=height,
        dpi=dpi,
        cached=cached,
    )


def _fmt_mime(fmt: str) -> str:
    return "image/jpeg" if fmt == "jpeg" else "image/png"
