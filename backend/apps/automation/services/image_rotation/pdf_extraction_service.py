"""Business logic services."""

from __future__ import annotations

"""
PDF 页面提取服务

负责从 PDF 文件中提取页面为图片,并检测每页的方向.
使用 PyMuPDF (fitz) 进行 PDF 处理.

Requirements: 1.2, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3
"""


import base64
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .orientation.service import OrientationDetectionService

logger = logging.getLogger("apps.automation.pdf_extraction")


class PDFExtractionService:
    """
    PDF 页面提取服务

    从 PDF 文件中提取每一页为 PNG 图片,并使用 OrientationDetectionService
    检测每页的方向.

    Requirements: 1.2, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3
    """

    MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_PAGES = 100
    DPI = 150  # 提取图片的 DPI

    def __init__(self, orientation_service: OrientationDetectionService | None = None) -> None:
        """
        初始化 PDF 提取服务

        Args:
            orientation_service: 方向检测服务(可选,支持依赖注入)
        """
        self._orientation_service = orientation_service

    @property
    def orientation_service(self) -> OrientationDetectionService:
        """懒加载方向检测服务"""
        if self._orientation_service is None:
            from .orientation.service import OrientationDetectionService

            self._orientation_service = OrientationDetectionService()
        return self._orientation_service

    def extract_pages(self, pdf_data: str, filename: str) -> dict[str, Any]:
        """提取 PDF 页面为图片(包含方向检测,兼容旧接口)"""
        pdf_document = self._open_pdf_document(pdf_data, filename)
        if isinstance(pdf_document, dict):
            return pdf_document

        try:
            page_count = len(pdf_document)
            error = self._validate_page_count(page_count, filename)
            if error:
                return error

            pages = self._extract_all_pages_with_detection(pdf_document, filename, page_count)

            if not pages:
                return {"success": False, "filename": filename, "message": "所有页面提取失败", "pages": []}

            logger.info(f"PDF 页面提取完成: {filename}", extra={})
            return {"success": True, "filename": filename, "pages": pages}
        finally:
            pdf_document.close()

    def _extract_all_pages_with_detection(
        self, pdf_document: Any, filename: str, page_count: int
    ) -> list[dict[str, Any]]:
        """提取所有页面(包含方向检测)"""
        pages: list[Any] = []
        for page_num in range(page_count):
            try:
                page = pdf_document[page_num]
                page_result = self._extract_single_page(page, page_num + 1, filename)
                pages.append(page_result)
            except Exception as e:
                logger.warning(f"页面提取失败: 第 {page_num + 1} 页", extra={"pdf_filename": filename, "error": str(e)})
        return pages

    def _open_pdf_document(self, pdf_data: str, filename: str) -> Any:
        """解码并打开 PDF 文档,失败返回错误 dict"""
        try:
            import fitz
        except ImportError:
            return {"success": False, "filename": filename, "message": "PDF 处理库未安装", "pages": []}

        try:
            if "," in pdf_data:
                pdf_data = pdf_data.split(",", 1)[1]
            pdf_bytes = base64.b64decode(pdf_data)
        except Exception as e:
            logger.warning(f"PDF Base64 解码失败: {e}", extra={"pdf_filename": filename})
            return {"success": False, "filename": filename, "message": "PDF 数据解码失败", "pages": []}

        if len(pdf_bytes) > self.MAX_PDF_SIZE:
            size_mb = len(pdf_bytes) / (1024 * 1024)
            return {
                "success": False,
                "filename": filename,
                "message": f"PDF 文件大小 ({size_mb:.1f}MB) 超过 50MB 限制",
                "pages": [],
            }

        try:
            return fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            logger.exception("PDF 文件解析失败", extra={"pdf_filename": filename})
            return {"success": False, "filename": filename, "message": "PDF 文件解析失败", "pages": []}

    def _validate_page_count(self, page_count: int, filename: str) -> dict[str, Any] | None | None:
        """验证页数,返回错误 dict 或 None"""
        if page_count > self.MAX_PAGES:
            return {
                "success": False,
                "filename": filename,
                "message": f"PDF 页数 ({page_count}) 超过 100 页限制",
                "pages": [],
            }
        if page_count == 0:
            return {"success": False, "filename": filename, "message": "PDF 文件没有页面", "pages": []}
        return None

    def _extract_all_pages_without_detection(
        self, pdf_document: Any, filename: str, page_count: int
    ) -> list[dict[str, Any]]:
        """提取所有页面(不检测方向)"""
        pages: list[Any] = []
        for page_num in range(page_count):
            try:
                page = pdf_document[page_num]
                page_result = self._extract_page_without_detection(page, page_num + 1)
                pages.append(page_result)
            except Exception as e:
                logger.warning(f"页面提取失败: 第 {page_num + 1} 页", extra={"pdf_filename": filename, "error": str(e)})
        return pages

    def _extract_page_without_detection(self, page: Any, page_number: int) -> dict[str, Any]:
        """
        提取单个 PDF 页面为图片,不检测方向

        Args:
            page: PyMuPDF 页面对象
            page_number: 页码(从 1 开始)

        Returns:
            页面数据字典
        """
        image_bytes = self._extract_page_image(page, self.DPI)

        rect = page.rect
        width = int(rect.width * self.DPI / 72)
        height = int(rect.height * self.DPI / 72)

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        return {
            "page_number": page_number,
            "data": f"data:image/png;base64,{image_base64}",
            "rotation": 0,
            "width": width,
            "height": height,
        }

    def detect_single_page_orientation(self, image_data: str) -> dict[str, Any]:
        """
        检测单个页面的方向(供前端异步调用)

        Args:
            image_data: Base64 编码的图片数据(可带 data URL 前缀)

        Returns:
            {
                "rotation": 0/90/180/270,
                "confidence": float,
                "method": str
            }
        """
        try:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            image_bytes = base64.b64decode(image_data)
            return self._detect_page_orientation(image_bytes)
        except Exception as e:
            logger.warning(f"页面方向检测失败: {e}")
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "error",
                "error": str(e),
            }

    def _extract_single_page(self, page: Any, page_number: int, filename: str) -> dict[str, Any]:
        """
        提取单个 PDF 页面为图片并检测方向

        Args:
            page: PyMuPDF 页面对象
            page_number: 页码(从 1 开始)
            filename: 原始 PDF 文件名

        Returns:
            页面数据字典
        """
        # 提取页面为 PNG 图片
        image_bytes = self._extract_page_image(page, self.DPI)

        # 获取页面尺寸
        rect = page.rect
        width = int(rect.width * self.DPI / 72)  # 转换为像素
        height = int(rect.height * self.DPI / 72)

        # 检测页面方向 (Requirements 2.1, 2.2, 2.3)
        # 得分阈值判断已在 OrientationDetectionService 中处理
        orientation_result = self._detect_page_orientation(image_bytes)

        # 直接使用检测结果(得分过低时 OrientationDetectionService 已返回 rotation=0)
        rotation = orientation_result.get("rotation", 0)
        confidence = orientation_result.get("confidence", 0)

        # 编码为 Base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        return {
            "page_number": page_number,
            "data": f"data:image/png;base64,{image_base64}",
            "rotation": rotation,
            "confidence": confidence,
            "width": width,
            "height": height,
        }

    def _extract_page_image(self, page: Any, dpi: int = 150) -> Any:
        """
        将单个 PDF 页面转换为 PNG 图片

        Args:
            page: PyMuPDF 页面对象
            dpi: 输出图片的 DPI

        Returns:
            PNG 图片的字节数据
        """
        # 计算缩放比例(PDF 默认 72 DPI)
        zoom = dpi / 72

        # 使用 fitz.Matrix 进行缩放
        import fitz

        mat = fitz.Matrix(zoom, zoom)

        # 渲染页面为 pixmap
        pixmap = page.get_pixmap(matrix=mat, alpha=False)

        # 转换为 PNG 字节
        return pixmap.tobytes("png")

    def _detect_page_orientation(self, image_data: bytes) -> dict[str, Any]:
        """
        检测页面方向

        使用 OrientationDetectionService 的四方向 OCR 投票法检测图片方向.

        Args:
            image_data: PNG 图片字节数据

        Returns:
            {
                "rotation": 0/90/180/270,
                "confidence": float,
                "method": str
            }

        Requirements: 2.1, 2.2, 2.3
        """
        try:
            result = self.orientation_service.detect_orientation(image_data)
            return result
        except Exception as e:
            # 检测失败时假设页面方向正确 (Requirement 2.3)
            logger.warning(f"页面方向检测失败,使用默认方向: {e}", extra={})
            return {
                "rotation": 0,
                "confidence": 0,
                "method": "default",
                "error": str(e),
            }
