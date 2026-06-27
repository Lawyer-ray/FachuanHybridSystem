"""PDF 工具函数 — 跨 app 共享

提供三类功能：
1. 页数读取（pikepdf → fitz → pdfplumber 三级降级）
2. PDF 页面操作工具（渲染、文本提取、合并）
3. 源数据读取（支持 bytes/Path/str/Django FieldFile 等多种输入）
"""

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.core.pdf_utils")


# ── 页数读取（三级降级）──────────────────────────────────────────


def get_pdf_page_count_with_error(source: Any, default: int = 1) -> tuple[int, str | None]:  # pragma: no cover
    """读取 PDF 页数，失败时返回 (default, error_message)。

    降级策略: pikepdf → fitz → pdfplumber
    """
    data = read_source_bytes(source)
    last_error: Exception | None = None

    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages), None
    except Exception as e:
        logger.debug("pikepdf 读取页数失败: %s", e)
        last_error = e

    try:
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            return int(doc.page_count), None
        finally:
            doc.close()
    except (TypeError, ValueError) as e:
        logger.debug("fitz 读取页数失败: %s", e)
        last_error = e

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages), None
    except (TypeError, ValueError) as e:
        logger.debug("pdfplumber 读取页数失败: %s", e)
        last_error = e

    error_text = str(last_error) if last_error else "unknown error"
    logger.warning("PDF 页数识别失败: %s", error_text)
    return default, error_text


def get_pdf_page_count(source: Any, default: int = 1) -> int:
    """读取 PDF 页数，失败返回 default。"""
    count, _ = get_pdf_page_count_with_error(source, default=default)
    return count


# ── PDF 页面操作工具 ──────────────────────────────────────────────


def render_page_to_image(
    pdf_path_or_bytes: str | Path | bytes,
    page_no: int = 0,
    dpi: int = 200,
    fmt: str = "png",
) -> bytes:  # pragma: no cover
    """将 PDF 指定页面渲染为图片字节。

    Args:
        pdf_path_or_bytes: PDF 文件路径或字节数据
        page_no: 页码（0-based）
        dpi: 渲染分辨率
        fmt: 输出格式（"png" / "jpeg"）

    Returns:
        图片字节数据
    """
    import fitz

    if isinstance(pdf_path_or_bytes, bytes):
        doc = fitz.open(stream=pdf_path_or_bytes, filetype="pdf")
    else:
        doc = fitz.open(str(pdf_path_or_bytes))
    try:
        page = doc.load_page(page_no)
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=matrix)
        return pix.tobytes(fmt)  # type: ignore[no-any-return]
    finally:
        doc.close()


def extract_text(
    pdf_path_or_bytes: str | Path | bytes,
    max_pages: int | None = None,
    char_limit: int | None = None,
) -> str:  # pragma: no cover
    """从 PDF 提取纯文本。

    Args:
        pdf_path_or_bytes: PDF 文件路径或字节数据
        max_pages: 最大处理页数（None = 全部）
        char_limit: 字符数上限（None = 不限）

    Returns:
        提取的文本内容
    """
    import fitz

    if isinstance(pdf_path_or_bytes, bytes):
        doc = fitz.open(stream=pdf_path_or_bytes, filetype="pdf")
    else:
        doc = fitz.open(str(pdf_path_or_bytes))
    try:
        parts: list[str] = []
        total_chars = 0
        page_count = doc.page_count
        limit = min(page_count, max_pages) if max_pages else page_count

        for i in range(limit):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            if text.strip():
                parts.append(text.strip())
                total_chars += len(text.strip())
            if char_limit and total_chars >= char_limit:
                break

        result = "\n".join(parts)
        if char_limit and len(result) > char_limit:
            result = result[:char_limit]
        return result
    finally:
        doc.close()


def merge_pdfs(
    sources: list[str | Path | bytes],
    output: str | Path | None = None,
) -> bytes:  # pragma: no cover
    """合并多个 PDF 为一个。

    Args:
        sources: PDF 文件路径或字节数据列表
        output: 输出文件路径（None = 返回字节数据）

    Returns:
        合并后的 PDF 字节数据
    """
    import fitz

    merged = fitz.open()
    try:
        for src in sources:
            if isinstance(src, bytes):
                doc = fitz.open(stream=src, filetype="pdf")
            else:
                doc = fitz.open(str(src))
            merged.insert_pdf(doc)
            doc.close()

        if output:
            merged.save(str(output))

        buf = io.BytesIO()
        merged.save(buf)
        buf.seek(0)
        return buf.getvalue()
    finally:
        merged.close()


# ── 源数据读取 ───────────────────────────────────────────────────


def read_source_bytes(source: Any) -> bytes:  # pragma: no cover
    """从各种来源读取 PDF 字节数据。

    支持: bytes / Path / str / Django FieldFile / file-like object
    """
    if source is None:
        raise ValueError("source is None")

    if isinstance(source, (bytes, bytearray)):
        return bytes(source)

    if isinstance(source, Path):
        return source.read_bytes()

    if isinstance(source, str):
        return Path(source).read_bytes()

    # 尝试各种读取策略
    for reader in [_read_django_field_file, _read_file_like, _read_from_path_attr]:
        result = reader(source)
        if result is not None:
            return result

    raise TypeError(f"Unsupported source type: {type(source)}")


async def aread_source_bytes(source: Any) -> bytes:  # pragma: no cover
    """Async version of read_source_bytes — delegates blocking I/O to thread pool."""
    import asyncio

    if source is None:
        raise ValueError("source is None")

    # bytes/bytearray are already in memory, no I/O needed
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)

    return await asyncio.to_thread(read_source_bytes, source)


def _read_django_field_file(source: Any) -> bytes | None:  # pragma: no cover
    """读取 Django FieldFile 或 InMemoryUploadedFile"""
    if not (hasattr(source, "open") and hasattr(source, "read")):
        return None
    try:
        source.seek(0)
    except Exception:
        with contextlib.suppress(Exception):
            source.open("rb")
    try:
        data = source.read()
        with contextlib.suppress(Exception):
            source.seek(0)
        return data  # type: ignore[no-any-return]
    except Exception:
        logger.debug("读取 Django FieldFile 失败", exc_info=True)
        return None


def _read_file_like(source: Any) -> bytes | None:
    """读取类文件对象"""
    if not hasattr(source, "read"):
        return None
    pos = None
    if hasattr(source, "tell"):
        with contextlib.suppress(Exception):
            pos = source.tell()
    if hasattr(source, "seek"):
        with contextlib.suppress(Exception):
            source.seek(0)
    try:
        data = source.read()
    except Exception:
        logger.debug("读取 file-like 对象失败", exc_info=True)
        return None
    if hasattr(source, "seek"):
        with contextlib.suppress(Exception):
            source.seek(pos if pos is not None else 0)
    return data  # type: ignore[no-any-return]


def _read_from_path_attr(source: Any) -> bytes | None:  # pragma: no cover
    """通过 path 属性读取（已保存到磁盘的文件）"""
    if hasattr(source, "path"):
        return Path(source.path).read_bytes()
    return None
