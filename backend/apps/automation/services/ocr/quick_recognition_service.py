from __future__ import annotations

import logging
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _

from .invoice_parser import InvoiceParser, ParsedInvoice
from .ocr_service import OCRService
from .pdf_text_extractor import PDFTextExtractor
from .recognition_result import RecognitionResult

logger = logging.getLogger(__name__)


class QuickRecognitionService:
    """快速识别服务：不创建任务，直接返回识别结果
    
    用于在不创建 InvoiceRecognitionTask 的情况下快速识别发票文件。
    复用现有的 OCR 和解析逻辑，但不保存到数据库。
    
    Attributes:
        ALLOWED_EXTENSIONS: 支持的文件扩展名集合
        MAX_FILE_SIZE: 最大文件大小（字节）
    """

    ALLOWED_EXTENSIONS: set[str] = {".pdf", ".jpg", ".jpeg", ".png"}
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB

    def __init__(
        self,
        ocr_service: OCRService,
        pdf_extractor: PDFTextExtractor,
        parser: InvoiceParser,
    ) -> None:
        """初始化快速识别服务
        
        Args:
            ocr_service: OCR 服务实例
            pdf_extractor: PDF 文本提取器实例
            parser: 发票解析器实例
        """
        self._ocr = ocr_service
        self._pdf_extractor = pdf_extractor
        self._parser = parser

    def recognize_files(
        self, files: list[UploadedFile]
    ) -> list[RecognitionResult]:
        """批量识别文件，返回结构化结果
        
        Args:
            files: 上传的文件列表
            
        Returns:
            识别结果列表，每个文件对应一个 RecognitionResult
        """
        results: list[RecognitionResult] = []
        
        for file in files:
            result = self._process_single_file(file)
            results.append(result)
            
        logger.info("快速识别完成: 总文件数=%d", len(files))
        return results

    def _validate_file(self, file: UploadedFile) -> None:
        """验证文件格式和大小
        
        Args:
            file: 上传的文件
            
        Raises:
            ValidationError: 文件格式不支持或大小超限
        """
        name: str = file.name or ""
        ext = Path(name).suffix.lower()
        
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                _("不支持的文件格式：%(ext)s，仅允许 PDF、JPG、JPEG、PNG。")
                % {"ext": ext}
            )
        
        size: int = file.size or 0
        if size > self.MAX_FILE_SIZE:
            raise ValidationError(
                _("文件大小超过限制（最大 20 MB），当前文件大小：%(size).1f MB。")
                % {"size": size / 1024 / 1024}
            )

    def _process_single_file(
        self, file: UploadedFile
    ) -> RecognitionResult:
        """处理单个文件
        
        Args:
            file: 上传的文件
            
        Returns:
            识别结果
        """
        filename: str = file.name or "unknown"
        
        try:
            # 1. 验证文件
            self._validate_file(file)
            
            # 2. 提取文本
            ext = Path(filename).suffix.lower()
            if ext == ".pdf":
                raw_text = self._process_pdf(file)
            else:
                raw_text = self._process_image(file)
            
            # 3. 解析结构化字段
            parsed: ParsedInvoice = self._parser.parse(raw_text)
            
            logger.info("文件识别成功: %s", filename)
            return RecognitionResult(
                filename=filename,
                success=True,
                data=parsed,
            )
            
        except ValidationError as exc:
            logger.error("文件验证失败: %s, 文件: %s", exc.message, filename)
            return RecognitionResult(
                filename=filename,
                success=False,
                error=str(exc.message),
            )
            
        except Exception as exc:
            logger.error(
                "文件识别失败: %s, 文件: %s",
                exc,
                filename,
                exc_info=True,
            )
            return RecognitionResult(
                filename=filename,
                success=False,
                error=_("识别失败，请重试"),
            )

    def _process_pdf(self, file: UploadedFile) -> str:
        """PDF 处理：文本提取优先，OCR 兜底
        
        Args:
            file: PDF 文件
            
        Returns:
            提取的文本内容
        """
        # 将上传文件保存到临时位置
        import tempfile
        
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as tmp_file:
            for chunk in file.chunks():
                tmp_file.write(chunk)
            tmp_path = Path(tmp_file.name)
        
        try:
            # 尝试文本提取
            text = self._pdf_extractor.extract(tmp_path)
            if text is not None:
                return text
            
            # 文本不足，转图片走 OCR
            image_paths = self._pdf_extractor.pdf_to_images(tmp_path)
            parts: list[str] = []
            for img_path in image_paths:
                parts.append(self._ocr.recognize(str(img_path)))
            return "\n".join(parts)
            
        finally:
            # 清理临时文件
            tmp_path.unlink(missing_ok=True)

    def _process_image(self, file: UploadedFile) -> str:
        """图片处理：直接调用 OCRService
        
        Args:
            file: 图片文件
            
        Returns:
            识别的文本内容
        """
        # 将上传文件保存到临时位置
        import tempfile
        
        ext = Path(file.name or "").suffix.lower()
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False
        ) as tmp_file:
            for chunk in file.chunks():
                tmp_file.write(chunk)
            tmp_path = Path(tmp_file.name)
        
        try:
            return self._ocr.recognize(str(tmp_path))
        finally:
            # 清理临时文件
            tmp_path.unlink(missing_ok=True)
