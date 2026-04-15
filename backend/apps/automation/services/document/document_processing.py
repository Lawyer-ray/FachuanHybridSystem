import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import fitz
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from docx import Document


def get_doc_config() -> dict[str, int]:
    """获取文档处理配置"""
    from django.conf import settings

    # 尝试使用统一配置管理器
    try:
        if getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
            get_unified_config = getattr(settings, "get_unified_config", None)
            if get_unified_config:
                return {
                    "DEFAULT_TEXT_LIMIT": get_unified_config("features.document_processing.default_text_limit", 1500),
                    "DEFAULT_PREVIEW_PAGE": get_unified_config("features.document_processing.default_preview_page", 1),
                    "MAX_TEXT_LIMIT": get_unified_config("features.document_processing.max_text_limit", 10000),
                    "MAX_PREVIEW_PAGES": get_unified_config("features.document_processing.max_preview_pages", 5),
                }
    except Exception:
        pass  # 回退到传统方式

    # 回退到传统配置方式
    return getattr(
        settings,
        "DOCUMENT_PROCESSING",
        {
            "DEFAULT_TEXT_LIMIT": 1500,
            "DEFAULT_PREVIEW_PAGE": 1,
            "MAX_TEXT_LIMIT": 10000,
            "MAX_PREVIEW_PAGES": 5,
        },
    )


def extract_text_from_image_with_rapidocr(file_path: str) -> str:
    """
    使用 OCR 从图片中提取文字

    自动根据 SystemConfig 中的 OCR_PROVIDER 配置选择本地 RapidOCR 或 PaddleOCR API。
    """
    from apps.automation.services.ocr.ocr_service import OCRService

    ocr_service = OCRService()
    return ocr_service.recognize(file_path)


def render_pdf_page_to_image(file_path: str, page_num: int = 0) -> str:
    """
    将PDF指定页面渲染为图片

    Args:
        file_path: PDF文件路径
        page_num: 页码（从0开始），默认为0（第一页）

    Returns:
        图片URL
    """
    # 验证页码范围
    if page_num < 0:
        page_num = 0

    p = Path(file_path)
    with fitz.open(p) as doc:
        # 检查页码是否超出范围
        if page_num >= doc.page_count:
            page_num = min(page_num, doc.page_count - 1)

        page = doc.load_page(page_num)
        pix = page.get_pixmap()
        out_dir = Path(settings.MEDIA_ROOT) / "automation" / "processed"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{uuid.uuid4().hex}_page{page_num + 1}.png"
        out_path = out_dir / out_name
        pix.save(out_path.as_posix())
        return f"{settings.MEDIA_URL}automation/processed/{out_name}"


def render_pdf_first_page_to_image(file_path: str) -> str:
    """保持向后兼容性的函数"""
    return render_pdf_page_to_image(file_path, page_num=0)


def extract_docx_text(file_path: str, limit: int | None = None) -> str:
    """提取 .docx 文件的文本"""
    # 如果没有指定限制，使用配置的默认值
    if limit is None:
        config = get_doc_config()
        limit = config["DEFAULT_TEXT_LIMIT"]

    # 限制最大值
    config = get_doc_config()
    if limit > config["MAX_TEXT_LIMIT"]:
        limit = config["MAX_TEXT_LIMIT"]

    p = Path(file_path)
    d = Document(p.as_posix())
    parts = []
    for para in d.paragraphs:
        if para.text:
            parts.append(para.text)
        if limit is not None and sum(len(x) for x in parts) >= int(limit):
            break
    text = "\n".join(parts)
    if limit is not None:
        return text[: int(limit)]
    return text


def extract_pdf_text(file_path: str, limit: int | None = None, max_pages: int | None = None) -> str:
    # 如果没有指定限制，使用配置的默认值
    if limit is None:
        config = get_doc_config()
        limit = config["DEFAULT_TEXT_LIMIT"]

    # 限制最大值
    config = get_doc_config()
    if limit > config["MAX_TEXT_LIMIT"]:
        limit = config["MAX_TEXT_LIMIT"]

    p = Path(file_path)
    parts: list[str] = []
    with fitz.open(p) as doc:
        for i in range(doc.page_count):
            if max_pages is not None and max_pages > 0 and i >= max_pages:
                break
            page = doc.load_page(i)
            t = page.get_text()
            if t:
                parts.append(t)
            if limit is not None and sum(len(x) for x in parts) >= int(limit):
                break
    text = "".join(parts)
    if limit is not None:
        return text[: int(limit)]
    return text


def _apply_pdf_limits(limit: int | None, preview_page: int | None, config: dict[str, Any]) -> tuple[int, int]:
    """应用配置默认值和范围限制"""
    lim = limit if limit is not None else config["DEFAULT_TEXT_LIMIT"]
    page = preview_page if preview_page is not None else config["DEFAULT_PREVIEW_PAGE"]
    lim = min(lim, config["MAX_TEXT_LIMIT"])
    page = min(page, config["MAX_PREVIEW_PAGES"])
    return lim, page


def _ocr_pdf_page(file_path: str, page_num_1based: int, limit: int) -> str | None:
    """将 PDF 指定页 OCR，返回文字或 None"""
    try:
        p = Path(file_path)
        with fitz.open(p) as doc:
            page_num = min(max(page_num_1based - 1, 0), doc.page_count - 1)
            page = doc.load_page(page_num)
            pix = page.get_pixmap()

            temp_dir = Path(settings.MEDIA_ROOT) / "automation" / "processed"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / f"temp_{uuid.uuid4().hex}_page{page_num + 1}.png"
            pix.save(temp_path.as_posix())

            ocr_text = extract_text_from_image_with_rapidocr(temp_path.as_posix())
            temp_path.relative_to(Path(settings.MEDIA_ROOT))  # 边界检查
            temp_path.unlink(missing_ok=True)

            if ocr_text.strip():
                return ocr_text[:limit]
    except Exception as e:
        logger.info(f"OCR处理PDF失败: {e}")
    return None


def process_pdf(
    file_path: str, limit: int | None = None, preview_page: int | None = None
) -> tuple[str | None, str | None]:
    """处理PDF文件：先提取文字，失败则 OCR，再失败则返回预览图"""
    config = get_doc_config()
    lim, page = _apply_pdf_limits(limit, preview_page, config)

    text = extract_pdf_text(file_path, lim)
    if text.strip():
        return None, text

    ocr_text = _ocr_pdf_page(file_path, page, lim)
    if ocr_text:
        return None, ocr_text

    image_url = render_pdf_page_to_image(file_path, page - 1)
    return image_url, None


@dataclass
class DocumentExtraction:
    file_path: str
    text: str | None
    image_url: str | None
    kind: str


def save_uploaded_document(upload: UploadedFile) -> Path:
    out_dir = Path(settings.MEDIA_ROOT) / "automation" / "uploads"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}_{upload.name}"
    dest = out_dir / fname
    with dest.open("wb") as w:
        for chunk in upload.chunks():
            w.write(chunk)
    return dest


def extract_document_content(
    file_path: str, limit: int | None = None, preview_page: int | None = None
) -> DocumentExtraction:
    """
    提取文档内容

    Args:
        file_path: 文件路径
        limit: 文字提取限制，None时使用配置默认值
        preview_page: PDF预览页码，None时使用配置默认值

    Returns:
        DocumentExtraction对象
    """
    ext = Path(file_path).suffix.lower()
    supported_image_exts = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]

    if ext == ".pdf":
        image_url, text = process_pdf(file_path, limit, preview_page)
        return DocumentExtraction(file_path=file_path, text=text, image_url=image_url, kind="pdf")

    if ext == ".docx":
        text = extract_docx_text(file_path, limit=limit)
        return DocumentExtraction(file_path=file_path, text=text, image_url=None, kind="docx")

    # 支持图片格式
    if ext in supported_image_exts:
        text = extract_text_from_image_with_rapidocr(file_path)

        # 应用限制
        if limit is None:
            config = get_doc_config()
            limit = config["DEFAULT_TEXT_LIMIT"]
        if limit > get_doc_config()["MAX_TEXT_LIMIT"]:
            limit = get_doc_config()["MAX_TEXT_LIMIT"]

        if limit is not None:
            text = text[: int(limit)]
        return DocumentExtraction(file_path=file_path, text=text, image_url=None, kind="image")

    raise ValueError(f"不支持的文件类型 {ext}，支持的格式：PDF、DOCX、图片({', '.join(supported_image_exts)})")


def process_uploaded_document(
    upload: UploadedFile, limit: int | None = None, preview_page: int | None = None
) -> DocumentExtraction:
    """
    统一的上传文件处理接口：
    1. 保存上传文件
    2. 抽取可用文本 / 首图
    3. 返回 DocumentExtraction 结果

    Args:
        upload: 上传的文件对象
        limit: 文字提取限制，None时使用配置默认值
        preview_page: PDF预览页码，None时使用配置默认值

    Returns:
        DocumentExtraction对象
    """
    dest = save_uploaded_document(upload)
    extraction = extract_document_content(dest.as_posix(), limit=limit, preview_page=preview_page)
    return extraction
