import uuid
from pathlib import Path

from dataclasses import dataclass

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

import fitz
from docx import Document
from rapidocr_onnxruntime import RapidOCR


def get_doc_config():
    """获取文档处理配置"""
    from django.conf import settings
    
    # 尝试使用统一配置管理器
    try:
        if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
            get_unified_config = getattr(settings, 'get_unified_config', None)
            if get_unified_config:
                return {
                    'DEFAULT_TEXT_LIMIT': get_unified_config('features.document_processing.default_text_limit', 1500),
                    'DEFAULT_PREVIEW_PAGE': get_unified_config('features.document_processing.default_preview_page', 1),
                    'MAX_TEXT_LIMIT': get_unified_config('features.document_processing.max_text_limit', 10000),
                    'MAX_PREVIEW_PAGES': get_unified_config('features.document_processing.max_preview_pages', 5),
                }
    except Exception:
        pass  # 回退到传统方式
    
    # 回退到传统配置方式
    return getattr(settings, 'DOCUMENT_PROCESSING', {
        'DEFAULT_TEXT_LIMIT': 1500,
        'DEFAULT_PREVIEW_PAGE': 1,
        'MAX_TEXT_LIMIT': 10000,
        'MAX_PREVIEW_PAGES': 5,
    })


def extract_text_from_image_with_rapidocr(file_path: str) -> str:
    """
    使用RapidOCR从图片中提取文字
    """
    ocr = RapidOCR()
    result, _ = ocr(file_path)
    if result:
        # 将识别结果按行合并
        text_lines = [item[1] for item in result]
        return "\n".join(text_lines)
    return ""


def render_pdf_page_to_image(file_path: str, page_num: int = 0) -> str:
    """
    将PDF指定页面渲染为图片
    
    Args:
        file_path: PDF文件路径
        page_num: 页码（从0开始），默认为0（第一页）
    
    Returns:
        图片URL
    """
    config = get_doc_config()
    
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
        limit = config['DEFAULT_TEXT_LIMIT']
    
    # 限制最大值
    config = get_doc_config()
    if limit > config['MAX_TEXT_LIMIT']:
        limit = config['MAX_TEXT_LIMIT']
    
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
        return text[:int(limit)]
    return text


def extract_pdf_text(file_path: str, limit: int | None = None) -> str:
    # 如果没有指定限制，使用配置的默认值
    if limit is None:
        config = get_doc_config()
        limit = config['DEFAULT_TEXT_LIMIT']
    
    # 限制最大值
    config = get_doc_config()
    if limit > config['MAX_TEXT_LIMIT']:
        limit = config['MAX_TEXT_LIMIT']
    
    p = Path(file_path)
    parts: list[str] = []
    with fitz.open(p) as doc:
        for i in range(doc.page_count):
            page = doc.load_page(i)
            t = page.get_text()
            if t:
                parts.append(t)
            if limit is not None and sum(len(x) for x in parts) >= int(limit):
                break
    text = "".join(parts)
    if limit is not None:
        return text[:int(limit)]
    return text


def process_pdf(file_path: str, limit: int | None = None, preview_page: int = None) -> tuple[str | None, str | None]:
    """
    处理PDF文件：
    1. 先尝试直接提取文字
    2. 如果提取失败，将指定页转为图片并用RapidOCR处理
    3. 如果OCR也失败，返回预览图
    
    Args:
        file_path: PDF文件路径
        limit: 文字提取限制，None时使用配置默认值
        preview_page: 预览页码（从1开始），None时使用配置默认值
    
    Returns:
        (image_url, text) 元组，其中一个为None
    """
    config = get_doc_config()
    
    # 设置默认值
    if limit is None:
        limit = config['DEFAULT_TEXT_LIMIT']
    if preview_page is None:
        preview_page = config['DEFAULT_PREVIEW_PAGE']
    
    # 限制范围
    if limit > config['MAX_TEXT_LIMIT']:
        limit = config['MAX_TEXT_LIMIT']
    if preview_page > config['MAX_PREVIEW_PAGES']:
        preview_page = config['MAX_PREVIEW_PAGES']
    
    # 先尝试直接提取文字
    text = extract_pdf_text(file_path, limit)
    if text.strip():
        return None, text
    
    # 直接提取失败，使用RapidOCR处理指定页面
    try:
        # 将指定页面渲染为临时图片文件
        p = Path(file_path)
        with fitz.open(p) as doc:
            # 转换为0基页码
            page_num = preview_page - 1
            if page_num >= doc.page_count:
                page_num = doc.page_count - 1
            if page_num < 0:
                page_num = 0
                
            page = doc.load_page(page_num)
            pix = page.get_pixmap()
            
            # 保存临时图片文件
            temp_dir = Path(settings.MEDIA_ROOT) / "automation" / "processed"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_name = f"temp_{uuid.uuid4().hex}_page{page_num + 1}.png"
            temp_path = temp_dir / temp_name
            pix.save(temp_path.as_posix())
            
            # 使用RapidOCR识别
            ocr_text = extract_text_from_image_with_rapidocr(temp_path.as_posix())
            
            # 删除临时文件
            temp_path.unlink(missing_ok=True)
            
            if ocr_text.strip():
                if limit is not None:
                    ocr_text = ocr_text[:int(limit)]
                return None, ocr_text
    except Exception as e:
        print(f"RapidOCR处理PDF失败: {e}")
    
    # 如果RapidOCR也失败，返回指定页的预览图
    image_url = render_pdf_page_to_image(file_path, preview_page - 1)
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


def extract_document_content(file_path: str, limit: int | None = None, preview_page: int = None) -> DocumentExtraction:
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
            limit = config['DEFAULT_TEXT_LIMIT']
        if limit > get_doc_config()['MAX_TEXT_LIMIT']:
            limit = get_doc_config()['MAX_TEXT_LIMIT']
            
        if limit is not None:
            text = text[:int(limit)]
        return DocumentExtraction(file_path=file_path, text=text, image_url=None, kind="image")
    
    raise ValueError(
        f"不支持的文件类型 {ext}，支持的格式：PDF、DOCX、图片({', '.join(supported_image_exts)})"
    )


def process_uploaded_document(upload: UploadedFile, limit: int | None = None, preview_page: int = None) -> DocumentExtraction:
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
