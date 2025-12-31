"""
文本提取服务

负责从各种格式的法院文书中提取文字内容。
支持 PDF 直接提取、PDF 降级到 OCR、图片 OCR 三种策略。

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


# 支持的文件扩展名
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_EXTENSIONS = SUPPORTED_PDF_EXTENSIONS | SUPPORTED_IMAGE_EXTENSIONS


def _remove_all_spaces(text: str) -> str:
    """
    删除文本中的所有空格（包括空格、制表符、换行符等）
    
    Args:
        text: 原始文本
        
    Returns:
        删除空格后的文本
    """
    import re
    # 删除所有空白字符：空格、制表符、换行符、回车符等
    return re.sub(r'\s+', '', text) if text else ""


@dataclass
class TextExtractionResult:
    """
    文本提取结果
    
    Attributes:
        text: 提取的文本内容（已删除所有空格）
        extraction_method: 提取方式 ("pdf_direct" | "ocr")
        success: 是否成功提取到文本
    """
    text: str
    extraction_method: str
    success: bool


class TextExtractionService:
    """
    文本提取服务
    
    复用现有 document_processing.py 的 OCR 功能，
    实现 PDF 直接提取、PDF 降级到 OCR、图片 OCR 三种策略。
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """
    
    def __init__(self, text_limit: Optional[int] = None):
        """
        初始化文本提取服务
        
        Args:
            text_limit: 文本提取字数限制，None 表示不限制
        """
        self._text_limit = text_limit
    
    def extract_text(self, file_path: str) -> TextExtractionResult:
        """
        从文件中提取文本
        
        根据文件类型自动选择提取策略：
        - PDF: 先尝试直接提取，失败则降级到 OCR
        - 图片: 直接使用 OCR
        
        Args:
            file_path: 文件路径
            
        Returns:
            TextExtractionResult: 提取结果
            
        Raises:
            ValidationException: 文件格式不支持
            
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        # 验证文件存在
        path = Path(file_path)
        if not path.exists():
            raise ValidationException(
                message="文件不存在",
                code="FILE_NOT_FOUND",
                errors={"file": f"文件 {file_path} 不存在"}
            )
        
        # 验证文件格式
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValidationException(
                message="不支持的文件格式",
                code="UNSUPPORTED_FILE_FORMAT",
                errors={
                    "file": f"不支持 {ext} 格式，请上传 PDF 或图片（jpg, jpeg, png）"
                }
            )
        
        # 根据文件类型选择提取策略
        if ext in SUPPORTED_PDF_EXTENSIONS:
            return self._extract_from_pdf(file_path)
        else:
            return self._extract_from_image(file_path)
    
    def _extract_from_pdf(self, file_path: str) -> TextExtractionResult:
        """
        从 PDF 文件提取文本
        
        策略：
        1. 先尝试直接提取 PDF 中的文字
        2. 如果直接提取失败或文字为空，降级到 OCR
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            TextExtractionResult: 提取结果
            
        Requirements: 3.1, 3.2, 3.3
        """
        # 先尝试直接提取
        text = self._extract_pdf_text_direct(file_path)
        
        if text and text.strip():
            # 删除所有空格后再返回
            cleaned_text = _remove_all_spaces(text)
            logger.info(f"PDF 直接提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
            return TextExtractionResult(
                text=cleaned_text,
                extraction_method="pdf_direct",
                success=True
            )
        
        # 直接提取失败，降级到 OCR
        logger.info(f"PDF 直接提取失败，降级到 OCR: {file_path}")
        return self._extract_pdf_with_ocr(file_path)
    
    def _extract_pdf_text_direct(self, file_path: str) -> str:
        """
        直接从 PDF 提取文字
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            提取的文字，失败返回空字符串
            
        Requirements: 3.1, 3.2
        """
        try:
            from apps.automation.services.document.document_processing import (
                extract_pdf_text
            )
            return extract_pdf_text(file_path, limit=self._text_limit)
        except Exception as e:
            logger.warning(f"PDF 直接提取异常: {e}")
            return ""
    
    def _extract_pdf_with_ocr(self, file_path: str) -> TextExtractionResult:
        """
        使用 OCR 从 PDF 提取文字
        
        将 PDF 页面渲染为图片，然后使用 RapidOCR 识别。
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            TextExtractionResult: 提取结果
            
        Requirements: 3.3
        """
        try:
            text = self._ocr_pdf_pages(file_path)
            
            if text and text.strip():
                # 删除所有空格
                cleaned_text = _remove_all_spaces(text)
                
                # 应用字数限制
                if self._text_limit and len(cleaned_text) > self._text_limit:
                    cleaned_text = cleaned_text[:self._text_limit]
                
                logger.info(f"PDF OCR 提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
                return TextExtractionResult(
                    text=cleaned_text,
                    extraction_method="ocr",
                    success=True
                )
            
            logger.warning(f"PDF OCR 提取失败，无法识别文字: {file_path}")
            return TextExtractionResult(
                text="",
                extraction_method="ocr",
                success=False
            )
        except Exception as e:
            logger.error(f"PDF OCR 提取异常: {e}")
            return TextExtractionResult(
                text="",
                extraction_method="ocr",
                success=False
            )
    
    def _ocr_pdf_pages(self, file_path: str) -> str:
        """
        对 PDF 所有页面进行 OCR
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            识别的文字
        """
        import uuid
        import fitz
        from django.conf import settings
        from apps.automation.services.document.document_processing import (
            extract_text_from_image_with_rapidocr
        )
        
        all_text = []
        temp_files = []
        
        try:
            with fitz.open(file_path) as doc:
                for page_num in range(doc.page_count):
                    # 渲染页面为图片
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap()
                    
                    # 保存临时图片
                    temp_dir = Path(settings.MEDIA_ROOT) / "automation" / "temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_name = f"ocr_temp_{uuid.uuid4().hex}_page{page_num}.png"
                    temp_path = temp_dir / temp_name
                    pix.save(temp_path.as_posix())
                    temp_files.append(temp_path)
                    
                    # OCR 识别
                    page_text = extract_text_from_image_with_rapidocr(
                        temp_path.as_posix()
                    )
                    if page_text:
                        all_text.append(page_text)
                    
                    # 检查是否达到字数限制
                    current_length = sum(len(t) for t in all_text)
                    if self._text_limit and current_length >= self._text_limit:
                        break
            
            return "\n".join(all_text)
        finally:
            # 清理临时文件
            for temp_file in temp_files:
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception:
                    pass
    
    def _extract_from_image(self, file_path: str) -> TextExtractionResult:
        """
        从图片文件提取文本
        
        使用 RapidOCR 识别图片中的文字。
        
        Args:
            file_path: 图片文件路径
            
        Returns:
            TextExtractionResult: 提取结果
            
        Requirements: 3.4, 3.5
        """
        try:
            from apps.automation.services.document.document_processing import (
                extract_text_from_image_with_rapidocr
            )
            
            text = extract_text_from_image_with_rapidocr(file_path)
            
            if text and text.strip():
                # 删除所有空格
                cleaned_text = _remove_all_spaces(text)
                
                # 应用字数限制
                if self._text_limit and len(cleaned_text) > self._text_limit:
                    cleaned_text = cleaned_text[:self._text_limit]
                
                logger.info(f"图片 OCR 提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
                return TextExtractionResult(
                    text=cleaned_text,
                    extraction_method="ocr",
                    success=True
                )
            
            logger.warning(f"图片 OCR 提取失败，无法识别文字: {file_path}")
            return TextExtractionResult(
                text="",
                extraction_method="ocr",
                success=False
            )
        except Exception as e:
            logger.error(f"图片 OCR 提取异常: {e}")
            return TextExtractionResult(
                text="",
                extraction_method="ocr",
                success=False
            )
    
    @staticmethod
    def is_supported_format(file_path: str) -> bool:
        """
        检查文件格式是否支持
        
        Args:
            file_path: 文件路径或文件名
            
        Returns:
            是否支持该格式
        """
        # 如果传入的是扩展名本身（以.开头），直接检查
        if file_path.startswith("."):
            return file_path.lower() in SUPPORTED_EXTENSIONS
        # 否则从路径中提取扩展名
        ext = Path(file_path).suffix.lower()
        return ext in SUPPORTED_EXTENSIONS
    
    @staticmethod
    def get_supported_extensions() -> Tuple[str, ...]:
        """
        获取支持的文件扩展名列表
        
        Returns:
            支持的扩展名元组
        """
        return tuple(SUPPORTED_EXTENSIONS)
