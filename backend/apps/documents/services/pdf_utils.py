"""Business logic services."""

import contextlib
import io
import logging
from typing import Any

from apps.core.path import Path

logger = logging.getLogger("apps.documents")


def get_pdf_page_count_with_error(source: Any, default: int = 1) -> tuple[int, str | None]:
    data = _read_source_bytes(source)
    last_error: Exception | None = None

    try:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages), None
    except Exception as e:
        logger.exception("操作失败")
        last_error = e

    try:
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            return int(doc.page_count), None
        finally:
            doc.close()
    except Exception as e:
        logger.exception("操作失败")
        last_error = e

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages), None
    except Exception as e:
        logger.exception("操作失败")
        last_error = e

    error_text = str(last_error) if last_error else "unknown error"
    logger.warning(f"PDF 页数识别失败: {error_text}")
    return default, error_text


def get_pdf_page_count(source: Any, default: int = 1) -> int:
    count, _ = get_pdf_page_count_with_error(source, default=default)
    return count


def _read_source_bytes(source: Any) -> Any:
    if source is None:
        raise ValueError("source is None")

    if isinstance(source, (bytes, bytearray)):
        return bytes(source)

    if isinstance(source, Path):
        return source.read_bytes()

    if isinstance(source, str):
        return Path(source).read_bytes()

    # 尝试各种读取策略
    readers: list[tuple[str, Any]] = [
        ("django_field_file", _read_django_field_file),
        ("file_like", _read_file_like),
        ("path_attr", _read_from_path_attr),
    ]
    for _name, reader in readers:
        result = reader(source)
        if result is not None:
            return result

    raise TypeError(f"Unsupported source type: {type(source)}")


def _read_django_field_file(source: Any) -> Any:
    """读取 Django FieldFile 或 InMemoryUploadedFile"""
    if not (hasattr(source, "open") and hasattr(source, "read")):
        return None
    try:
        source.seek(0)
    except Exception:
        logger.exception("操作失败")

        with contextlib.suppress(Exception):
            source.open("rb")
    try:
        data = source.read()
        with contextlib.suppress(Exception):
            source.seek(0)
        return data
    except Exception:
        logger.exception("操作失败")

        return None


def _read_file_like(source: Any) -> Any:
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
        logger.exception("操作失败")

        return None
    if hasattr(source, "seek"):
        with contextlib.suppress(Exception):
            source.seek(pos if pos is not None else 0)
    return data


def _read_from_path_attr(source: Any) -> Any:
    """通过 path 属性读取(已保存到磁盘的文件)"""
    if hasattr(source, "path"):
        return Path(source.path).read_bytes()
    return None
