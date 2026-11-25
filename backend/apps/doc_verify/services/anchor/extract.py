"""把一份字节流提取成 :class:`Inbound`：页数 + 逐页指纹 + 文本层。

## 指纹口径不在本模块定

分辨率、块大小、二值化阈值全部沿用
:mod:`apps.pdf_splitting.services.split.page_fingerprint`（100dpi / 8×8 块），
这里只按页调它的公开函数，一个参数都不改。基线侧与回传件侧必须落在同一坐标系里，
否则「同一页」的 0.03 容差就成了一句没有意义的话。

## 基线侧永不 OCR

扫描件（无文本层）的 ``text`` 一律是空串，只留页指纹。基线侧做 OCR 的后果不是
「多花点时间」，而是两侧各带一套互不相同的识别噪声，任何字都可能差一格，
误报率平方级上升。

## 失败要吵，但别把「未知格式」当失败

已知格式（PDF / DOCX）解析失败抛 ``ValueError``（中文说明 + 文件名），**不返回空基线**：
空基线会让以后每一次核对都「无法核对」，而用户看不到「当初就没捕获成功」。
未知格式（图片等）走「能算则算」：文本层留空，MuPDF 能解码就给页指纹，
不能解码就只留字节 SHA-256（字节相同仍是硬证据）。
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pymupdf

from apps.doc_verify.domain.contracts import Inbound
from apps.pdf_splitting.services.split.page_fingerprint import page_signature

logger = logging.getLogger(__name__)

#: 文件类型判定结果，决定走哪条提取路径
KIND_PDF = "pdf"
KIND_DOCX = "docx"
KIND_IMAGE = "image"
KIND_OTHER = "other"

#: 页与页之间的分隔符。保持「split 后第 i 段 == 第 i 页」，
#: 按页比对的断言（页序 / 缺页 / 整页替换）全靠这条对应关系
PAGE_TEXT_SEPARATOR = "\f"

_PDF_MAGIC = b"%PDF-"

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"})

#: PyMuPDF 打开 / 渲染 / 取字时可能抛的异常。
#: pymupdf 2.x 的 ``FileDataError`` 继承 **RuntimeError** 而不是 ValueError——
#: 只列 ValueError 会让坏 PDF 穿透成 500（同一条事实见 apps/core/services/pdf_utils.py:52）
_PYMUPDF_ERRORS = (RuntimeError, ValueError, OSError)


def sha256_hex(data: bytes) -> str:
    """字节的 SHA-256 十六进制串：基线与回传件「是不是同一份纸」的判定从它开始。"""
    return hashlib.sha256(data).hexdigest()


def detect_document_kind(data: bytes, file_name: str = "") -> str:
    """按魔数优先、扩展名兜底判定文件类型。

    魔数优先的理由：出站件常被改名（``起诉状(1)``、``未命名``），
    但 PDF 头改不掉；扩展名优先的理由：docx / 图片只能用扩展名区分。
    """
    suffix = Path(file_name or "").suffix.lower()
    if data.startswith(_PDF_MAGIC) or suffix == ".pdf":
        return KIND_PDF
    if suffix == ".docx":
        return KIND_DOCX
    if suffix in _IMAGE_SUFFIXES:
        return KIND_IMAGE
    return KIND_OTHER


def extract_document(data: bytes, file_name: str = "") -> Inbound:
    """把字节流提取成 :class:`Inbound`（sha256 / 页数 / 逐页指纹 / 文本层）。

    - PDF：逐页 ``page.get_text("text")``，页间用 ``\\f`` 拼接，逐页指纹；
    - DOCX：段落 + 表格单元格文本，页数未知（0），无指纹（docx 不渲染，算不出图像指纹）；
    - 图片 / 其它：文本层留空，能算指纹就算。
    """
    if not data:
        raise ValueError(f"文件字节为空，无法提取（文件：{_display_name(file_name)}）")
    extractor = _EXTRACTORS[detect_document_kind(data, file_name)]
    return extractor(data, file_name)


def _display_name(file_name: str) -> str:
    return file_name or "未命名"


def _extract_pdf(data: bytes, file_name: str) -> Inbound:
    document = _open_pdf(data, file_name)
    try:
        page_count = int(document.page_count)
        page_texts: list[str] = []
        signatures: list[tuple[float, ...]] = []
        for page_index in range(page_count):
            page = document.load_page(page_index)
            page_texts.append(_page_text(page, page_index, file_name))
            signatures.append(_page_signature(page, page_index, file_name))
    finally:
        document.close()
    return Inbound(
        sha256=sha256_hex(data),
        page_count=page_count,
        page_signatures=tuple(signatures),
        text=_join_page_texts(page_texts, file_name),
        file_name=file_name,
    )


def _open_pdf(data: bytes, file_name: str) -> pymupdf.Document:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except _PYMUPDF_ERRORS as exc:
        raise ValueError(f"PDF 无法打开（文件：{_display_name(file_name)}），文件可能已损坏") from exc
    if getattr(document, "needs_pass", False):
        document.close()
        raise ValueError(f"PDF 已加密，无法捕获基线（文件：{_display_name(file_name)}）")
    if int(document.page_count) <= 0:
        document.close()
        raise ValueError(f"PDF 没有页面，无法捕获基线（文件：{_display_name(file_name)}）")
    return document


def _page_text(page: pymupdf.Page, page_index: int, file_name: str) -> str:
    try:
        return page.get_text("text") or ""
    except _PYMUPDF_ERRORS as exc:
        raise ValueError(f"PDF 第 {page_index + 1} 页取文本层失败（文件：{_display_name(file_name)}）") from exc


def _page_signature(page: pymupdf.Page, page_index: int, file_name: str) -> tuple[float, ...]:
    try:
        return tuple(page_signature(page))
    except _PYMUPDF_ERRORS as exc:
        raise ValueError(f"PDF 第 {page_index + 1} 页渲染失败（文件：{_display_name(file_name)}）") from exc


def _join_page_texts(page_texts: Sequence[str], file_name: str) -> str:
    text = PAGE_TEXT_SEPARATOR.join(page_texts)
    if not text.strip():
        logger.info(
            "出站件没有文本层，基线正文留空（基线侧不做 OCR）：文件=%s 页数=%d",
            _display_name(file_name),
            len(page_texts),
        )
        return ""
    return text


def _extract_docx(data: bytes, file_name: str) -> Inbound:
    from docx import Document as DocxDocument
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = DocxDocument(io.BytesIO(data))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise ValueError(f"Word 文档无法打开（文件：{_display_name(file_name)}），文件可能已损坏") from exc
    text = "\n".join(_docx_lines(document))
    if not text:
        logger.info("Word 文档没有可用文本（基线正文留空）：文件=%s", _display_name(file_name))
    # docx 不渲染，页数与图像指纹都无从谈起：宁可留空，也不拿「按段落数猜页数」去冒充
    return Inbound(sha256=sha256_hex(data), page_count=0, page_signatures=(), text=text, file_name=file_name)


def _docx_lines(document: Any) -> list[str]:
    """段落文本 + 表格单元格文本。

    ``python-docx`` 的 ``paragraphs`` **不包含表格单元格文字**，而签署页
    （甲乙方、日期、盖章）几乎总在表格里——只取段落会丢掉落款
    （同一事实见 apps/contracts/services/contract/intake/document_snapshot.py:6）。
    """
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        lines.extend(_docx_table_lines(table))
    return [line for line in lines if line.strip()]


def _docx_table_lines(table: Any) -> list[str]:
    cell_texts = (_docx_cell_text(cell) for row in table.rows for cell in row.cells)
    return [text for text in cell_texts if text]


def _docx_cell_text(cell: Any) -> str:
    return "\n".join(paragraph.text for paragraph in cell.paragraphs).strip()


def _extract_visual(data: bytes, file_name: str) -> Inbound:
    """图片与其它格式：没有文本层，只给页指纹（MuPDF 能解码才算）。"""
    sha256 = sha256_hex(data)
    try:
        document = pymupdf.open(stream=data)
    except _PYMUPDF_ERRORS as exc:
        logger.info(
            "该文件 MuPDF 无法解码，基线只保留字节 SHA-256：文件=%s 原因=%s",
            _display_name(file_name),
            exc,
        )
        return Inbound(sha256=sha256, page_count=0, page_signatures=(), text="", file_name=file_name)

    try:
        page_count = int(document.page_count)
        signatures = tuple(
            _best_effort_page_signature(document.load_page(index), page_index=index, file_name=file_name)
            for index in range(page_count)
        )
    finally:
        document.close()
    logger.info(
        "非 PDF/DOCX 文件，基线不含文本层（不做 OCR）：文件=%s 页数=%d 指纹页数=%d",
        _display_name(file_name),
        page_count,
        len(signatures),
    )
    return Inbound(
        sha256=sha256,
        page_count=page_count,
        page_signatures=signatures,
        text="",
        file_name=file_name,
    )


def _best_effort_page_signature(page: pymupdf.Page, *, page_index: int, file_name: str) -> tuple[float, ...]:
    """图片/未知格式的指纹：算不出就给空 tuple。

    空 tuple 是**占位**而不是「跳过」：第 i 个元素必须永远对应第 i 页，
    否则后面几页的指纹会整体错位一页，比对时静默对错页。
    空指纹与任何指纹的长度都不同，未识别的页因此必然判「完全不同」而不是「相同」。
    取不到指纹不值得整份失败：字节 SHA-256 仍能证明「原样回传」。
    """
    try:
        return tuple(page_signature(page))
    except _PYMUPDF_ERRORS as exc:
        logger.info(
            "该文件第 %d 页无法渲染出指纹，按空指纹占位：文件=%s 原因=%s",
            page_index + 1,
            _display_name(file_name),
            exc,
        )
        return ()


_EXTRACTORS: dict[str, Callable[[bytes, str], Inbound]] = {
    KIND_PDF: _extract_pdf,
    KIND_DOCX: _extract_docx,
    KIND_IMAGE: _extract_visual,
    KIND_OTHER: _extract_visual,
}
