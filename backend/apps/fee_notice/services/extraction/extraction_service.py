"""Business logic services."""

from __future__ import annotations

"\n交费通知书识别主服务\n\n协调整个识别流程:文本提取、通知书检测、费用金额提取.\n"
"支持多文件批量处理、单PDF多份通知书识别.\n\nRequirements: 2.1, 4.1-4.4, 6.1-6.3, 7.1-7.6\n"
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..detection.detector import FeeNoticeDetector
from ..detection.extractor import FeeAmountExtractor
from ..types import FeeNoticeExtractionResult, FeeNoticeInfo

if TYPE_CHECKING:
    from apps.document_recognition.services.text_extraction_service import TextExtractionService
logger = logging.getLogger("apps.fee_notice")


class FeeNoticeExtractionService:
    """
    交费通知书识别服务

    协调整个识别流程,支持:
    - 多文件批量处理
    - 单PDF多份通知书识别
    - 详细调试信息输出
    """

    SUPPORTED_EXTENSIONS: ClassVar = {".pdf"}

    def __init__(
        self,
        text_service: TextExtractionService | None = None,
        detector: FeeNoticeDetector | None = None,
        extractor: FeeAmountExtractor | None = None,
    ) -> None:
        """
        初始化服务

        Args:
            text_service: 文本提取服务(可选,用于依赖注入)
            detector: 交费通知书检测器(可选)
            extractor: 费用金额提取器(可选)
        """
        self._text_service = text_service
        self._detector = detector
        self._extractor = extractor

    @property
    def text_service(self) -> TextExtractionService:
        """延迟加载文本提取服务"""
        if self._text_service is None:
            from apps.document_recognition.services.text_extraction_service import TextExtractionService

            self._text_service = TextExtractionService()
        return self._text_service

    @property
    def detector(self) -> FeeNoticeDetector:
        """延迟加载检测器"""
        if self._detector is None:
            self._detector = FeeNoticeDetector()
        return self._detector

    @property
    def extractor(self) -> FeeAmountExtractor:
        """延迟加载提取器"""
        if self._extractor is None:
            self._extractor = FeeAmountExtractor()
        return self._extractor

    def extract_from_files(self, file_paths: list[str], debug: bool = False) -> FeeNoticeExtractionResult:
        """
        从多个文件中提取交费通知书信息

        遍历所有上传的PDF文件,识别并提取交费通知书中的费用金额.
        支持多个PDF中包含多份交费通知书的情况.

        Args:
            file_paths: PDF文件路径列表
            debug: 是否输出调试信息

        Returns:
            FeeNoticeExtractionResult: 提取结果

        Requirements: 2.1, 4.1, 6.1
        """
        notices: list[FeeNoticeInfo] = []
        errors: list[dict[str, Any]] = []
        debug_logs: list[str] = []
        total_pages = 0
        if debug:
            debug_logs.append(f"开始处理 {len(file_paths)} 个文件")
            logger.info("开始批量提取交费通知书", extra={})
        for file_path in file_paths:
            try:
                if not self._is_supported_format(file_path):
                    error_msg = f"不支持的文件格式: {file_path}"
                    errors.append({"file": file_path, "error": error_msg, "code": "UNSUPPORTED_FORMAT"})
                    if debug:
                        debug_logs.append(error_msg)
                    continue
                if not Path(file_path).exists():
                    error_msg = f"文件不存在: {file_path}"
                    errors.append({"file": file_path, "error": error_msg, "code": "FILE_NOT_FOUND"})
                    if debug:
                        debug_logs.append(error_msg)
                    continue
                file_notices = self.extract_from_single_file(file_path, debug=debug)
                notices.extend(file_notices)
                page_count = self._get_pdf_page_count(file_path)
                total_pages += page_count
                if debug:
                    debug_logs.append(
                        f"文件 {Path(file_path).name}: 共 {page_count} 页,识别到 {len(file_notices)} 份通知书"
                    )
            except Exception as e:
                error_msg = f"处理文件失败: {file_path}, 错误: {e!s}"
                errors.append({"file": file_path, "error": str(e), "code": "PDF_READ_ERROR"})
                if debug:
                    debug_logs.append(error_msg)
                logger.warning("处理文件失败", extra={})
        result = FeeNoticeExtractionResult(
            notices=notices,
            total_files=len(file_paths),
            total_pages=total_pages,
            errors=errors,
            debug_logs=debug_logs if debug else [],
        )
        logger.info(
            "批量提取完成",
            extra={
                "total_files": len(file_paths),
                "total_pages": total_pages,
                "notices_found": len(notices),
                "errors_count": len(errors),
            },
        )
        return result

    def extract_from_single_file(self, file_path: str, debug: bool = False) -> list[FeeNoticeInfo]:
        """
        从单个文件中提取交费通知书信息

        检查PDF的每一页,识别交费通知书并提取费用金额.
        支持单个PDF中包含多份交费通知书的情况.

        Args:
            file_path: PDF文件路径
            debug: 是否输出调试信息

        Returns:
            List[FeeNoticeInfo]: 该文件中所有交费通知书的信息

        Requirements: 2.3, 2.4, 4.2, 4.3, 4.4, 6.2, 6.3, 7.1-7.6
        """
        notices: list[FeeNoticeInfo] = []
        file_name = Path(file_path).name
        if debug:
            logger.info("开始处理单个文件", extra={})
        pages_text = self._extract_pages_text(file_path, debug=debug)
        if not pages_text:
            logger.warning("无法提取文本", extra={})
            return notices
        for page_num, (text, extraction_method) in pages_text.items():
            detection = self.detector.detect(text, page_num)
            if debug:
                logger.info(
                    "页面检测结果",
                    extra={
                        "file": file_name,
                        "page": page_num,
                        "is_fee_notice": detection.is_fee_notice,
                        "confidence": detection.confidence,
                        "matched_keywords": detection.matched_keywords,
                    },
                )
            if not detection.is_fee_notice:
                continue
            amounts = self.extractor.extract(text, debug=debug)
            if amounts.table_format == "unknown":
                if debug:
                    logger.warning(
                        "金额提取失败,保留原始文本",
                        extra={"file": file_name, "page": page_num, "raw_text_preview": text[:200] if text else ""},
                    )
                if "raw_text" not in amounts.debug_info:
                    amounts.debug_info["raw_text"] = text
            notice = FeeNoticeInfo(
                file_name=file_name,
                file_path=file_path,
                page_num=page_num,
                detection=detection,
                amounts=amounts,
                extraction_method=extraction_method,
            )
            notices.append(notice)
            if debug:
                logger.info(
                    "识别到交费通知书",
                    extra={
                        "file": file_name,
                        "page": page_num,
                        "acceptance_fee": str(amounts.acceptance_fee) if amounts.acceptance_fee else None,
                        "preservation_fee": str(amounts.preservation_fee) if amounts.preservation_fee else None,
                        "table_format": amounts.table_format,
                    },
                )
        return notices

    def _extract_pages_text(self, file_path: str, debug: bool = False) -> dict[int, tuple[str, str]]:
        """
        提取PDF每页的文本内容

        先尝试直接提取PDF文本,如果失败则降级到OCR.

        Args:
            file_path: PDF文件路径
            debug: 是否输出调试信息

        Returns:
            Dict[int, Tuple[str, str]]: {页码: (文本内容, 提取方式)}
            页码从1开始

        Requirements: 7.1
        """
        import fitz

        pages_text: dict[int, tuple[str, str]] = {}
        try:
            with fitz.open(file_path) as doc:
                for page_idx in range(doc.page_count):
                    page_num = page_idx + 1
                    page = doc.load_page(page_idx)
                    text = page.get_text()
                    extraction_method = "pdf_direct"
                    if not text or not text.strip():
                        text = self._ocr_page(page, file_path, page_idx)
                        extraction_method = "ocr"
                    if text and text.strip():
                        pages_text[page_num] = (text, extraction_method)
                        if debug:
                            logger.info(
                                "页面文本提取完成",
                                extra={
                                    "file": Path(file_path).name,
                                    "page": page_num,
                                    "method": extraction_method,
                                    "text_length": len(text),
                                },
                            )
                    elif debug:
                        logger.warning("页面文本提取失败", extra={"file": Path(file_path).name, "page": page_num})
        except Exception:
            logger.error("PDF文件读取失败", extra={})
            raise
        return pages_text

    def _ocr_page(self, page: Any, file_path: str, page_idx: int) -> str:
        """
        对单个PDF页面进行OCR识别

        Args:
            page: fitz.Page 对象
            file_path: PDF文件路径(用于日志)
            page_idx: 页面索引(从0开始)

        Returns:
            识别的文本内容
        """
        import uuid

        from apps.core.config import get_config

        try:
            from apps.automation.services.document.document_processing import extract_text_from_image_with_rapidocr

            pix = page.get_pixmap()
            media_root = get_config("django.media_root", None)
            if not media_root:
                raise RuntimeError("django.media_root 未配置")
            root = Path(str(media_root)).resolve()
            temp_dir = root / "automation" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_name = f"fee_notice_ocr_{uuid.uuid4().hex}_page{page_idx}.png"
            temp_path = temp_dir / temp_name
            pix.save(str(temp_path))
            try:
                text = extract_text_from_image_with_rapidocr(str(temp_path))
                return text or ""
            finally:
                try:
                    abs_path = temp_path.resolve()
                    abs_path.relative_to(root)
                    abs_path.unlink(missing_ok=True)
                except Exception:
                    logger.exception("操作失败")
                    pass
        except Exception as e:
            logger.warning("OCR识别失败", extra={"file": file_path, "page": page_idx + 1, "error": str(e)})
            return ""

    def _is_supported_format(self, file_path: str) -> bool:
        """
        检查文件格式是否支持

        Args:
            file_path: 文件路径

        Returns:
            是否支持该格式
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def _get_pdf_page_count(self, file_path: str) -> Any:
        """
        获取PDF文件的页数

        Args:
            file_path: PDF文件路径

        Returns:
            页数
        """
        import fitz

        try:
            with fitz.open(file_path) as doc:
                return doc.page_count
        except Exception:
            logger.exception("操作失败")

    def save_uploaded_files(
        self, files: Any, temp_dir_name: str = "fee_notice", batch_id: str = ""
    ) -> tuple[list[Path], list[dict[str, str]]]:
        """保存上传文件到临时目录.

        Args:
            files: 上传文件列表
            temp_dir_name: 临时目录名称
            batch_id: 批次 ID

        Returns:
            (saved_files, errors) 元组
        """
        import uuid

        from django.conf import settings

        from apps.core.filesystem import FolderPathValidator

        temp_dir = Path(str(settings.MEDIA_ROOT)) / "automation" / "temp" / temp_dir_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        if not batch_id:
            batch_id = uuid.uuid4().hex[:8]
        saved_files: list[Path] = []
        file_errors: list[dict[str, str]] = []
        for uploaded_file in files:
            if not uploaded_file.name.lower().endswith(".pdf"):
                file_errors.append(
                    {
                        "file": uploaded_file.name,
                        "error": "不支持的文件格式,仅支持 PDF 文件",
                        "code": "UNSUPPORTED_FORMAT",
                    }
                )
                continue
            validator = FolderPathValidator()
            try:
                original_name: str = validator.sanitize_file_name(uploaded_file.name)
            except Exception:
                logger.exception("文件名不合法")
                file_errors.append(
                    {"file": str(uploaded_file.name or ""), "error": "文件名不合法", "code": "INVALID_FILE_NAME"}
                )
                continue
            safe_name = f"{batch_id}_{uuid.uuid4().hex[:8]}_{original_name}"
            temp_path = temp_dir / safe_name
            validator.ensure_within_base(temp_dir, temp_path)  # type: ignore
            try:
                with open(str(temp_path), "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)
                saved_files.append(temp_path)
            except Exception as e:
                logger.warning("保存上传文件失败", extra={"file": uploaded_file.name, "error": str(e)})
                file_errors.append(
                    {"file": uploaded_file.name, "error": f"保存文件失败: {e!s}", "code": "FILE_SAVE_ERROR"}
                )
        return (saved_files, file_errors)

    def cleanup_temp_files(self, saved_files: list[Path]) -> None:
        """清理临时文件.

        Args:
            saved_files: 要清理的文件路径列表
        """
        for temp_path in saved_files:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                logger.warning("清理临时文件失败", extra={"file_path": str(temp_path)})
