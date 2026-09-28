"""
文本提取服务

负责从各种格式的法院文书中提取文字内容。提取阶梯（每档失败自动降级，
任务不会因某一引擎挂掉而失败）：
1. 文本 PDF：直接提取（pdf_direct）；
2. 扫描 PDF / 图片：VLM 视觉转写（vlm，AI 平台配置 vision_model 时启用）；
3. 本地 OCR（ocr）：macOS Vision（darwin）→ RapidOCR（跨平台兜底）。

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path

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
    return re.sub(r"\s+", "", text) if text else ""


@dataclass
class TextExtractionResult:
    """
    文本提取结果

    Attributes:
        text: 提取的文本内容（已删除所有空格）
        extraction_method: 提取方式 ("pdf_direct" | "vlm" | "ocr")
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

    def __init__(self, text_limit: int | None = None, max_pages: int | None = None):
        """
        初始化文本提取服务

        Args:
            text_limit: 文本提取字数限制，None 表示不限制
            max_pages: 最大提取页数限制，None 表示不限制
        """
        self._text_limit = text_limit
        self._max_pages = max_pages

    def extract_text(self, file_path: str, max_pages: int | None = None) -> TextExtractionResult:
        """
        从文件中提取文本

        根据文件类型自动选择提取策略：
        - PDF: 先尝试直接提取，失败则降级到 OCR
        - 图片: 直接使用 OCR

        Args:
            file_path: 文件路径
            max_pages: 最大提取页数限制，None 时使用构造函数配置

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
                message="文件不存在", code="FILE_NOT_FOUND", errors={"file": f"文件 {file_path} 不存在"}
            )

        # 验证文件格式
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValidationException(
                message="不支持的文件格式",
                code="UNSUPPORTED_FILE_FORMAT",
                errors={"file": f"不支持 {ext} 格式，请上传 PDF 或图片（jpg, jpeg, png）"},
            )

        effective_max_pages = self._max_pages if max_pages is None else max_pages

        # 根据文件类型选择提取策略
        if ext in SUPPORTED_PDF_EXTENSIONS:
            return self._extract_from_pdf(file_path, max_pages=effective_max_pages)
        else:
            return self._extract_from_image(file_path)

    def _extract_from_pdf(self, file_path: str, max_pages: int | None = None) -> TextExtractionResult:
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
        text = self._extract_pdf_text_direct(file_path, max_pages=max_pages)

        if text and text.strip():
            # 删除所有空格后再返回
            cleaned_text = _remove_all_spaces(text)
            logger.info(f"PDF 直接提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
            return TextExtractionResult(text=cleaned_text, extraction_method="pdf_direct", success=True)

        # 直接提取失败：先 VLM 视觉转写（vision_model 已配置时），失败再本地 OCR
        vlm_result = self._extract_pdf_with_vlm(file_path, max_pages=max_pages)
        if vlm_result.success:
            return vlm_result
        logger.info(f"PDF 视觉转写不可用或失败，降级到本地 OCR: {file_path}")
        return self._extract_pdf_with_ocr(file_path, max_pages=max_pages)

    def _extract_pdf_text_direct(self, file_path: str, max_pages: int | None = None) -> str:
        """
        直接从 PDF 提取文字

        Args:
            file_path: PDF 文件路径

        Returns:
            提取的文字，失败返回空字符串

        Requirements: 3.1, 3.2
        """
        try:
            from apps.automation.services.document.document_processing import extract_pdf_text

            return extract_pdf_text(file_path, limit=self._text_limit, max_pages=max_pages)
        except Exception as e:
            logger.warning(f"PDF 直接提取异常: {e}")
            return ""

    def _extract_pdf_with_vlm(self, file_path: str, max_pages: int | None = None) -> TextExtractionResult:
        """
        使用 VLM 视觉转写从扫描 PDF 提取文字

        vision_model 未配置时直接返回失败（调用方降级本地 OCR），调用异常
        同样返回失败——视觉档绝不阻断任务。

        Requirements: 3.3
        """
        from apps.document_recognition.services.vlm_ocr_service import VLMTranscriptionService

        if not VLMTranscriptionService.is_available():
            return TextExtractionResult(text="", extraction_method="vlm", success=False)

        try:
            text = VLMTranscriptionService().transcribe_pdf(file_path, max_pages=max_pages)
            if text and text.strip():
                cleaned_text = _remove_all_spaces(text)
                if self._text_limit and len(cleaned_text) > self._text_limit:
                    cleaned_text = cleaned_text[: self._text_limit]
                logger.info(
                    f"PDF VLM 视觉转写成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}"
                )
                return TextExtractionResult(text=cleaned_text, extraction_method="vlm", success=True)
            logger.warning(f"PDF VLM 视觉转写结果为空: {file_path}")
            return TextExtractionResult(text="", extraction_method="vlm", success=False)
        except Exception as e:
            logger.warning(f"PDF VLM 视觉转写异常，降级本地 OCR: {e}")
            return TextExtractionResult(text="", extraction_method="vlm", success=False)

    def _recognize_local(self, image_path: str) -> str:  # pragma: no cover -- 引擎阶梯路由
        """本地 OCR 阶梯：darwin 优先 macOS Vision，失败/不可用回退 RapidOCR。"""
        try:
            from apps.automation.services.ocr import MacVisionOCREngine, is_mac_vision_available

            if is_mac_vision_available():
                return MacVisionOCREngine().recognize(image_path)
        except Exception as e:
            logger.warning(f"macOS Vision OCR 失败，回退 RapidOCR: {e}")

        from apps.core.interfaces import ServiceLocator

        return ServiceLocator.get_ocr_service().recognize(image_path)

    def _extract_pdf_with_ocr(self, file_path: str, max_pages: int | None = None) -> TextExtractionResult:
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
            text = self._ocr_pdf_pages(file_path, max_pages=max_pages)

            if text and text.strip():
                # 删除所有空格
                cleaned_text = _remove_all_spaces(text)

                # 应用字数限制
                if self._text_limit and len(cleaned_text) > self._text_limit:
                    cleaned_text = cleaned_text[: self._text_limit]

                logger.info(f"PDF OCR 提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
                return TextExtractionResult(text=cleaned_text, extraction_method="ocr", success=True)

            logger.warning(f"PDF OCR 提取失败，无法识别文字: {file_path}")
            return TextExtractionResult(text="", extraction_method="ocr", success=False)
        except Exception as e:
            logger.error(f"PDF OCR 提取异常: {e}")
            return TextExtractionResult(text="", extraction_method="ocr", success=False)

    def _ocr_pdf_pages(self, file_path: str, max_pages: int | None = None) -> str:  # pragma: no cover
        """
        对 PDF 所有页面进行 OCR

        Args:
            file_path: PDF 文件路径

        Returns:
            识别的文字
        """
        import uuid

        import pymupdf as fitz
        from django.conf import settings

        all_text = []
        temp_files = []

        try:
            with fitz.open(file_path) as doc:
                for page_num in range(doc.page_count):
                    if max_pages is not None and max_pages > 0 and page_num >= max_pages:
                        break
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

                    # OCR 识别（macOS Vision → RapidOCR 阶梯）
                    page_text = self._recognize_local(temp_path.as_posix())
                    if page_text:
                        all_text.append(page_text)

                    # 检查是否达到字数限制
                    current_length = sum(len(t) for t in all_text)
                    if self._text_limit and current_length >= self._text_limit:
                        break

            return "\n".join(all_text)
        finally:
            # 清理临时文件（仅删除 MEDIA_ROOT 内的文件）
            media_root = Path(settings.MEDIA_ROOT)
            for temp_file in temp_files:
                with contextlib.suppress(Exception):
                    temp_file.relative_to(media_root)  # 边界检查：确保在 MEDIA_ROOT 内
                    temp_file.unlink(missing_ok=True)

    def _extract_from_image(self, file_path: str) -> TextExtractionResult:
        """
        从图片文件提取文本

        提取阶梯：VLM 视觉转写（vision_model 已配置时）→ 本地 OCR
        （macOS Vision → RapidOCR）。

        Args:
            file_path: 图片文件路径

        Returns:
            TextExtractionResult: 提取结果

        Requirements: 3.4, 3.5
        """
        from apps.document_recognition.services.vlm_ocr_service import VLMTranscriptionService

        # 1. VLM 视觉转写
        if VLMTranscriptionService.is_available():
            try:
                text = VLMTranscriptionService().transcribe_image(file_path)
                if text and text.strip():
                    cleaned_text = _remove_all_spaces(text)
                    if self._text_limit and len(cleaned_text) > self._text_limit:
                        cleaned_text = cleaned_text[: self._text_limit]
                    logger.info(
                        f"图片 VLM 视觉转写成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}"
                    )
                    return TextExtractionResult(text=cleaned_text, extraction_method="vlm", success=True)
                logger.warning(f"图片 VLM 视觉转写结果为空: {file_path}")
            except Exception as e:
                logger.warning(f"图片 VLM 视觉转写异常，降级本地 OCR: {e}")

        # 2. 本地 OCR（macOS Vision → RapidOCR）
        try:
            text = self._recognize_local(file_path)

            if text and text.strip():
                # 删除所有空格
                cleaned_text = _remove_all_spaces(text)

                # 应用字数限制
                if self._text_limit and len(cleaned_text) > self._text_limit:
                    cleaned_text = cleaned_text[: self._text_limit]

                logger.info(f"图片 OCR 提取成功: {file_path}, 原始字数: {len(text)}, 清理后字数: {len(cleaned_text)}")
                return TextExtractionResult(text=cleaned_text, extraction_method="ocr", success=True)

            logger.warning(f"图片 OCR 提取失败，无法识别文字: {file_path}")
            return TextExtractionResult(text="", extraction_method="ocr", success=False)
        except Exception as e:
            logger.error(f"图片 OCR 提取异常: {e}")
            return TextExtractionResult(text="", extraction_method="ocr", success=False)

    def is_supported_format(self, file_path: str) -> bool:
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

    def get_supported_extensions(self) -> tuple[str, ...]:
        """
        获取支持的文件扩展名列表

        Returns:
            支持的扩展名元组
        """
        return tuple(SUPPORTED_EXTENSIONS)


def get_supported_extensions() -> tuple[str, ...]:
    """模块级函数：获取支持的文件扩展名列表"""
    return tuple(SUPPORTED_EXTENSIONS)


def is_supported_format(file_path: str) -> bool:  # pragma: no cover
    """模块级函数：检查文件格式是否支持"""
    return TextExtractionService().is_supported_format(file_path)
