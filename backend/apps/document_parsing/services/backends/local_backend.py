"""本地文档解析后端（PyMuPDF + RapidOCR）"""

import logging
from pathlib import Path
from typing import Any, List, Optional

from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult

logger = logging.getLogger(__name__)


class LocalBackend:
    """本地文档解析后端

    使用 PyMuPDF (fitz) 提取文本，必要时使用 OCR。
    作为 MinerU 的 fallback 选项。
    """

    def __init__(self, **kwargs: Any) -> None:
        """初始化本地后端"""
        self._ocr_service: Any = None

    def _get_ocr_service(self) -> Any:
        """获取 OCR 服务（延迟加载）"""
        if self._ocr_service is None:
            try:
                from apps.core.interfaces import ServiceLocator

                self._ocr_service = ServiceLocator.get_ocr_service()
            except Exception as e:
                logger.warning("无法获取 OCR 服务: %s", e)
                self._ocr_service = None
        return self._ocr_service

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """通过本地工具解析文档

        Args:
            file_path: 文件路径
            file_type: 文件类型
            extract_tables: 是否提取表格（本地后端不支持）
            extract_images: 是否提取图片
            return_markdown: 是否返回 Markdown（本地后端不支持）

        Returns:
            ParsedDocument 解析结果
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info("开始本地解析: %s", file_path)

        try:
            if file_type.lower() == "pdf":
                return self._parse_pdf(
                    file_path,
                    extract_images=extract_images,
                )
            elif file_type.lower() in ("jpg", "jpeg", "png", "bmp", "tiff"):
                return self._parse_image(file_path)
            else:
                raise ValueError(f"本地后端不支持的文件类型: {file_type}")

        except Exception as e:
            logger.error("本地解析失败: %s - %s", file_path, str(e))
            raise

    def extract_text(
        self,
        file_path: str,
        max_length: int | None = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """提取文档纯文本

        Args:
            file_path: 文件路径
            max_length: 最大文本长度

        Returns:
            TextExtractionResult 提取结果
        """
        try:
            parsed = self.parse_document(
                file_path=file_path,
                extract_tables=False,
                extract_images=False,
                return_markdown=False,
                **kwargs,
            )

            text = parsed.text
            if max_length and len(text) > max_length:
                text = text[:max_length]

            return TextExtractionResult(
                text=text,
                success=True,
                method="pymupdf",
                metadata=parsed.metadata,
            )

        except Exception as e:
            logger.error("本地文本提取失败: %s - %s", file_path, str(e))
            return TextExtractionResult(
                text="",
                success=False,
                method="pymupdf",
                metadata={"error": str(e)},
            )

    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式"""
        return ["pdf", "jpg", "jpeg", "png", "bmp", "tiff"]

    def _parse_pdf(
        self,
        file_path: str,
        extract_images: bool = False,
    ) -> ParsedDocument:
        """解析 PDF 文件

        Args:
            file_path: PDF 文件路径
            extract_images: 是否提取图片

        Returns:
            ParsedDocument 解析结果
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            texts = []
            images = []

            for page_num in range(len(doc)):
                page = doc[page_num]

                # 提取文本
                text = page.get_text()
                if text.strip():
                    texts.append(text)

                # 提取图片（可选）
                if extract_images:
                    image_list = page.get_images()
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        try:
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]

                            # 保存图片到临时文件
                            import tempfile

                            with tempfile.NamedTemporaryFile(suffix=f".{image_ext}", delete=False) as tmp:
                                tmp.write(image_bytes)
                                images.append(tmp.name)
                        except Exception as e:
                            logger.warning(
                                "提取图片失败 (page=%d, img=%d): %s",
                                page_num,
                                img_index,
                                e,
                            )

            page_count = len(doc)
            doc.close()

            # 合并文本
            full_text = "\n".join(texts)

            return ParsedDocument(
                text=full_text,
                images=images if images else None,
                metadata={"page_count": page_count},
                parse_method="pymupdf",
            )

        except ImportError:
            raise RuntimeError("未安装 PyMuPDF (fitz)。请运行: pip install PyMuPDF")

    def _parse_image(self, file_path: str) -> ParsedDocument:
        """解析图片文件（OCR）

        Args:
            file_path: 图片文件路径

        Returns:
            ParsedDocument 解析结果
        """
        ocr_service = self._get_ocr_service()
        if ocr_service is None:
            raise RuntimeError("OCR 服务不可用")

        try:
            # 使用 RapidOCR 提取文本
            result = ocr_service.recognize(file_path)

            text = result.strip() if result else ""

            return ParsedDocument(
                text=text,
                metadata={"file_type": "image"},
                parse_method="rapidocr",
            )

        except Exception as e:
            logger.error("图片 OCR 失败: %s - %s", file_path, str(e))
            raise
