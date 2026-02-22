"""
证件信息提取服务

使用 RapidOCR (PP-OCRv5) 提取图片文字,然后用 Ollama 结构化提取信息.
"""

from django.utils.translation import gettext_lazy as _
import json
import logging
import tempfile
from typing import Any

from apps.client.dependencies import get_ocr_engine
from apps.client.services.wiring import get_llm_service
from apps.core.exceptions import ServiceUnavailableError, ValidationException
from apps.core.llm.config import LLMConfig
from pathlib import Path

from .data_classes import ExtractionResult, OCRExtractionError, OllamaExtractionError

logger = logging.getLogger(__name__)


class IdentityExtractionService:
    """证件信息提取服务 - 使用 RapidOCR (PP-OCRv5) + Ollama"""

    def __init__(
        self, recognizer: Any | None = None, ollama_model: str | None = None, ollama_base_url: str | None = None
    ) -> None:
        self._recognizer = recognizer
        self._ollama_model = ollama_model or LLMConfig.get_ollama_model()
        self._ollama_base_url = ollama_base_url or LLMConfig.get_ollama_base_url()

    def extract(self, image_bytes: bytes, doc_type: str) -> ExtractionResult:
        """
        提取证件信息

        Args:
            image_bytes: 图片字节数据
            doc_type: 证件类型

        Returns:
            ExtractionResult: 提取结果
        """
        if not image_bytes:
            raise ValidationException(
                message=_("图片数据不能为空"), code="INVALID_IMAGE_DATA", errors={"image": str(_("图片数据不能为空"))}
            )

        if not doc_type:
            raise ValidationException(
                message=_("证件类型不能为空"), code="INVALID_DOC_TYPE", errors={"doc_type": str(_("证件类型不能为空"))}
            )

        try:
            # 1. OCR 提取文字
            raw_text = self._ocr_extract(image_bytes)

            # 2. Ollama 结构化提取
            extracted_data = self._ollama_extract(raw_text, doc_type)

            return ExtractionResult(
                doc_type=doc_type,
                raw_text=raw_text,
                extracted_data=extracted_data,
                confidence=0.8,
                extraction_method="ocr_ollama",
            )

        except (OCRExtractionError, OllamaExtractionError, ServiceUnavailableError):
            raise
        except Exception as e:
            logger.exception("证件信息提取失败: %s", e)
            raise ValidationException(
                message=_("证件信息提取失败: %(error)s") % {"error": str(e)},
                code="EXTRACTION_FAILED",
                errors={"extraction": str(e)},
            ) from e

    def _ocr_extract(self, image_bytes: bytes) -> str:
        """
        使用 RapidOCR (PP-OCRv5) 提取图片/PDF文字

        Args:
            image_bytes: 图片或PDF字节数据

        Returns:
            str: 提取的文字
        """
        try:
            if self._recognizer is not None and hasattr(self._recognizer, "classification"):
                try:
                    raw_text = self._recognizer.classification(image_bytes) or ""
                except Exception as e:
                    raise OCRExtractionError(f"OCR 提取失败: {e!s}") from e
                if raw_text.strip():
                    return raw_text.strip()
                raise OCRExtractionError("OCR 未能提取到有效文字")

            # 检测是否为 PDF(更健壮的检测方式)
            is_pdf = self._is_pdf_file(image_bytes)

            if is_pdf:
                # PDF 处理:用 pymupdf 转为图片
                return self._extract_from_pdf(image_bytes)
            else:
                # 图片处理
                return self._extract_from_image(image_bytes)

        except OCRExtractionError:
            raise
        except Exception as e:
            logger.exception("OCR 提取失败: %s", e)
            raise OCRExtractionError(f"OCR 提取失败: {e!s}") from e

    def _is_pdf_file(self, file_bytes: bytes) -> bool:
        """
        检测文件是否为 PDF

        Args:
            file_bytes: 文件字节数据

        Returns:
            bool: 是否为 PDF 文件
        """
        if not file_bytes or len(file_bytes) < 8:
            return False

        # 方法1: 检查 PDF 魔数(%PDF-)
        # PDF 文件通常以 %PDF- 开头,但可能有 BOM 或空白字符
        header = file_bytes[:1024]  # 检查前 1KB
        if b"%PDF-" in header:
            return True

        # 方法2: 尝试用 fitz 打开
        try:
            import fitz

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(doc)
            doc.close()
            return page_count > 0
        except Exception:
            return False

    def _extract_from_image(self, image_bytes: bytes) -> str:
        """从图片提取文字"""
        from io import BytesIO

        from PIL import Image

        try:
            img = Image.open(BytesIO(image_bytes))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")  # type: ignore[assignment]
        except Exception as e:
            logger.exception("图片格式无效: %s", e)
            raise OCRExtractionError("图片格式无效,请上传 JPG 或 PNG 格式的图片") from e

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp, format="JPEG", quality=95)
            tmp_path = tmp.name

        try:
            ocr = get_ocr_engine()
            result = ocr(tmp_path)

            # 新版 RapidOCR 返回 RapidOCROutput 对象
            if result and result.txts:
                raw_text = "\n".join(result.txts)

                if raw_text.strip():
                    logger.info("RapidOCR (PP-OCRv5) 提取成功,文字长度: %s", len(raw_text))
                    return raw_text.strip()

            raise OCRExtractionError("OCR 未能提取到有效文字")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _extract_from_pdf(self, pdf_bytes: bytes) -> str:
        """从 PDF 提取文字(图片型PDF)"""
        import fitz  # pymupdf

        all_texts = []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            ocr = get_ocr_engine()

            # 只处理前几页(证件通常只有1-2页)
            max_pages = min(len(doc), 3)

            for page_num in range(max_pages):
                page = doc[page_num]

                # 渲染为图片(300 DPI)
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)

                # 保存临时文件
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    pix.save(tmp.name)
                    tmp_path = tmp.name

                try:
                    # 新版 RapidOCR 返回 RapidOCROutput 对象
                    result = ocr(tmp_path)
                    if result and result.txts:
                        all_texts.extend(result.txts)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            doc.close()

            if all_texts:
                raw_text = "\n".join(all_texts)
                logger.info("PDF OCR (PP-OCRv5) 提取成功,文字长度: %s", len(raw_text))
                return raw_text.strip()

            raise OCRExtractionError("PDF OCR 未能提取到有效文字")

        except OCRExtractionError:
            raise
        except Exception as e:
            logger.exception("PDF 处理失败: %s", e)
            raise OCRExtractionError(f"PDF 处理失败: {e!s}") from e

    def _ollama_extract(self, raw_text: str, doc_type: str) -> dict[str, Any]:
        """
        使用 Ollama 从文字中提取结构化信息
        """
        try:
            from .prompts import get_prompt_for_doc_type

            prompt = get_prompt_for_doc_type(doc_type, raw_text)

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"请从以下文字中提取信息:\n{raw_text}"},
            ]

            llm_service = get_llm_service()
            llm_resp = llm_service.chat(messages=messages, backend="ollama", model=self._ollama_model, fallback=False)
            content = llm_resp.content or ""
            if not content:
                raise OllamaExtractionError("Ollama 返回内容为空")

            # 解析 JSON
            try:
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        content = content[json_start:json_end].strip()

                extracted_data = json.loads(content)
                logger.info("Ollama 提取成功,字段数量: %s", len(extracted_data))
                logger.info("Ollama 提取内容: %s", json.dumps(extracted_data, ensure_ascii=False, indent=2))
                return dict(extracted_data)

            except json.JSONDecodeError as e:
                logger.exception("Ollama 返回的 JSON 格式错误: %s", e)
                raise OllamaExtractionError(f"Ollama 返回的 JSON 格式错误: {e!s}") from e

        except ConnectionError as e:
            logger.exception("Ollama 服务连接失败: %s", e)
            raise ServiceUnavailableError(message=f"Ollama 服务连接失败: {e!s}", service_name="Ollama") from e
        except OllamaExtractionError:
            raise
        except Exception as e:
            logger.exception("Ollama 提取失败: %s", e)
            raise OllamaExtractionError(f"Ollama 提取失败: {e!s}") from e

    def safe_extract(self, image_bytes: bytes, doc_type: str) -> dict[str, Any]:
        """
        提取证件信息，捕获所有异常，返回含 success 字段的 dict。
        供 API 层直接调用，无需 try/except。
        """
        result: dict[str, Any] = {
            "success": False,
            "doc_type": doc_type,
            "extracted_data": {},
            "confidence": 0.0,
            "error": None,
        }
        # Service 层内部允许 try/except（规范禁止的是 API 层）
        try:
            extraction = self.extract(image_bytes, doc_type)
            result["success"] = True
            result["doc_type"] = extraction.doc_type
            result["extracted_data"] = extraction.extracted_data
            result["confidence"] = extraction.confidence
        except (OCRExtractionError, OllamaExtractionError) as e:
            result["error"] = f"识别失败: {e}"
        except ServiceUnavailableError as e:
            result["error"] = f"服务不可用: {e}"
        except ValidationException as e:
            result["error"] = str(e)
        except Exception as e:
            logger.exception("证件识别未知错误: %s", e)
            result["error"] = f"未知错误: {e}"
        return result
