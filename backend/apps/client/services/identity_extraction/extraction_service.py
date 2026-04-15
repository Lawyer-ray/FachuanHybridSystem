"""
证件信息提取服务

使用 RapidOCR (PP-OCRv5) 提取图片文字,然后用 Ollama 结构化提取信息.
"""

import json
import logging
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.client.models import ClientIdentityDoc
from apps.client.services.wiring import get_llm_service
from apps.core.exceptions import ServiceUnavailableError, ValidationException
from apps.core.llm.config import LLMConfig
from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError

from .data_classes import ExtractionResult, OCRExtractionError, OllamaExtractionError
from .prompts import PROMPT_MAPPING, get_prompt_for_doc_type

logger = logging.getLogger(__name__)

# 喂给 LLM 的 OCR 文本上限，避免噪声与超长上下文拖慢推理
_MAX_LLM_OCR_CHARS = 1800
_MAX_LLM_OCR_LINES = 80


class IdentityExtractionService:
    """证件信息提取服务 - 使用 RapidOCR (PP-OCRv5) + Ollama"""

    def __init__(
        self, recognizer: Any | None = None, ollama_model: str | None = None, ollama_base_url: str | None = None
    ) -> None:
        self._recognizer = recognizer
        self._ollama_model = ollama_model or LLMConfig.get_ollama_model()
        self._ollama_base_url = ollama_base_url or LLMConfig.get_ollama_base_url()

    def extract(
        self,
        image_bytes: bytes,
        doc_type: str,
        enable_ollama: bool = True,
        source_name: str | None = None,
    ) -> ExtractionResult:
        """
        提取证件信息

        Args:
            image_bytes: 图片字节数据
            doc_type: 证件类型
            enable_ollama: 是否允许回退 Ollama（身份证场景可关闭）

        Returns:
            ExtractionResult: 提取结果
        """
        if not image_bytes:
            raise ValidationException(
                message=_("图片数据不能为空"), code="INVALID_IMAGE_DATA", errors={"image": _("图片数据不能为空")}
            )

        if not doc_type:
            raise ValidationException(
                message=_("证件类型不能为空"), code="INVALID_DOC_TYPE", errors={"doc_type": _("证件类型不能为空")}
            )

        try:
            # 1. OCR 提取文字
            raw_text = self._ocr_extract(image_bytes)
            resolved_doc_type = self._resolve_doc_type(doc_type, raw_text, source_name=source_name)

            # 2. 优先规则提取（身份证场景稳定且低延迟）
            extracted_data = self._extract_by_rules(raw_text, resolved_doc_type)
            if extracted_data is not None:
                id_number_hit = bool(extracted_data.get("id_number"))
                if id_number_hit or not enable_ollama:
                    logger.info(
                        "证件识别使用规则提取: requested_doc_type=%s, resolved_doc_type=%s, enable_ollama=%s, id_number_hit=%s",
                        doc_type,
                        resolved_doc_type,
                        enable_ollama,
                        id_number_hit,
                    )
                    return ExtractionResult(
                        doc_type=resolved_doc_type,
                        raw_text=raw_text,
                        extracted_data=extracted_data,
                        confidence=0.95,
                        extraction_method="ocr_regex",
                    )

                logger.info(
                    "规则提取未命中身份证号且允许 Ollama，回退模型提取: requested_doc_type=%s, resolved_doc_type=%s",
                    doc_type,
                    resolved_doc_type,
                )

            # 3. 规则无法覆盖时回退 Ollama
            extracted_data = self._ollama_extract(raw_text, resolved_doc_type)

            return ExtractionResult(
                doc_type=resolved_doc_type,
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
                    raise OCRExtractionError(_("OCR 提取失败: %(e)s") % {"e": e}) from e
                if raw_text.strip():
                    return raw_text.strip()
                raise OCRExtractionError(_("OCR 未能提取到有效文字"))

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
            raise OCRExtractionError(_("OCR 提取失败: %(e)s") % {"e": e}) from e

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
        from PIL import Image

        try:
            img = Image.open(BytesIO(image_bytes))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
        except Exception as e:
            logger.exception("图片格式无效: %s", e)
            raise OCRExtractionError(_("图片格式无效,请上传 JPG 或 PNG 格式的图片")) from e

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            img.save(tmp, format="JPEG", quality=95)
            tmp_path = tmp.name

            from apps.automation.services.ocr.ocr_service import OCRService

            ocr_service = OCRService()
            raw_text = ocr_service.recognize(tmp_path)

            if raw_text and raw_text.strip():
                logger.info("OCR 提取成功,文字长度: %s", len(raw_text))
                return raw_text.strip()

            raise OCRExtractionError(_("OCR 未能提取到有效文字"))

    def _extract_from_pdf(self, pdf_bytes: bytes) -> str:
        """从 PDF 提取文字(图片型PDF)"""
        import fitz  # pymupdf
        from PIL import Image

        from apps.automation.services.ocr.ocr_service import OCRService

        # 禁用 PIL 的解压炸弹检查，避免超大 PDF 页面触发 DecompressionBombError
        Image.MAX_IMAGE_PIXELS = None

        all_texts = []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            ocr_service = OCRService()

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
                    page_text = ocr_service.recognize(tmp_path)
                    if page_text:
                        all_texts.append(page_text)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            doc.close()

            if all_texts:
                raw_text = "\n".join(all_texts)
                logger.info("PDF OCR 提取成功,文字长度: %s", len(raw_text))
                return raw_text.strip()

            raise OCRExtractionError(_("PDF OCR 未能提取到有效文字"))

        except OCRExtractionError:
            raise
        except Exception as e:
            logger.exception("PDF 处理失败: %s", e)
            raise OCRExtractionError(_("PDF 处理失败: %(e)s") % {"e": e}) from e

    def _looks_like_json_noise(self, line: str) -> bool:
        """判断是否为结构化 JSON/调试噪声行。"""
        candidate = line.strip()
        if len(candidate) < 10:
            return False

        if (candidate.startswith("{") and candidate.endswith("}")) or (
            candidate.startswith("[") and candidate.endswith("]")
        ):
            return True

        # 常见 JSON 键值模式: "key": ...
        if re.search(r'"[A-Za-z_][\w-]*"\s*:', candidate):
            return True

        json_chars = sum(1 for c in candidate if c in '{}[]":,')
        if len(candidate) >= 30 and (json_chars / len(candidate)) > 0.30:
            return True

        return False

    def _is_meaningful_line(self, line: str) -> bool:
        """判断 OCR 行是否有信息价值。"""
        if not line:
            return False

        # 仅符号/分隔线（如 ----、====、...）直接过滤
        if re.fullmatch(r"[\W_]+", line):
            return False

        # 纯重复字符噪声（如 111111、哈哈哈哈）过滤
        if len(set(line)) == 1 and len(line) >= 4:
            return False

        # 结构化 JSON 噪声过滤
        if self._looks_like_json_noise(line):
            return False

        # 过短且不含常见有效字符（数字/中文/字母）过滤
        if len(line) <= 1 and not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", line):
            return False

        return True

    def _prepare_text_for_ollama(self, raw_text: str) -> str:
        """清洗 OCR 文本后再发送给 Ollama，减少噪声与无意义上下文。"""
        # 统一换行并拆分候选行（兼容部分 OCR 用 | 作为分隔符）
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        candidates = re.split(r"\n+|\|", normalized)

        seen: set[str] = set()
        cleaned_lines: list[str] = []

        for part in candidates:
            # 合并中英文空白，减少 OCR 抖动导致的重复
            line = re.sub(r"\s+", "", part).strip()
            if not line:
                continue
            if not self._is_meaningful_line(line):
                continue
            if line in seen:
                continue

            seen.add(line)
            cleaned_lines.append(line)

        if not cleaned_lines:
            fallback = raw_text.strip()
            return fallback[:_MAX_LLM_OCR_CHARS]

        # 行数限制
        limited_lines = cleaned_lines[:_MAX_LLM_OCR_LINES]

        # 字符总量限制
        merged: list[str] = []
        current_len = 0
        for line in limited_lines:
            add_len = len(line) + (1 if merged else 0)
            if current_len + add_len > _MAX_LLM_OCR_CHARS:
                break
            merged.append(line)
            current_len += add_len

        prepared = "\n".join(merged)
        return prepared if prepared else "\n".join(limited_lines[:10])

    def _resolve_doc_type(self, doc_type: str, raw_text: str, source_name: str | None = None) -> str:
        requested = (doc_type or "").strip()
        if requested and requested != "auto" and requested in PROMPT_MAPPING:
            return requested

        if requested and requested not in {"auto", *PROMPT_MAPPING.keys()}:
            logger.warning("收到不支持的证件类型，已自动降级判型: doc_type=%s", requested)

        text = self._prepare_text_for_ollama(raw_text)
        normalized = text.lower()
        source = (source_name or "").lower()

        def has_any(tokens: tuple[str, ...]) -> bool:
            return any(token in text or token in normalized or token in source for token in tokens)

        business_tokens = (
            "营业执照",
            "统一社会信用代码",
            "企业名称",
            "法定代表人",
            "注册资本",
            "成立日期",
            "营业期限",
            "经营范围",
            "住所",
            "类型",
            "business license",
            "credit code",
        )
        id_card_tokens = ("公民身份号码", "居民身份证", "姓名", "性别", "民族", "住址", "出生")

        business_score = sum(1 for token in business_tokens if token in text or token in normalized or token in source)
        id_score = sum(1 for token in id_card_tokens if token in text)

        credit_code_match = re.search(r"(?<![0-9A-Z])([0-9A-Z]{18})(?![0-9A-Z])", text.upper())
        if credit_code_match:
            credit_code = credit_code_match.group(1)
            has_alpha = any(ch.isalpha() for ch in credit_code)
            if has_alpha or business_score >= 1:
                logger.info(
                    "证件自动判型命中统一社会信用代码特征: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
                    requested or "auto",
                    ClientIdentityDoc.BUSINESS_LICENSE,
                    business_score,
                    id_score,
                )
                return str(ClientIdentityDoc.BUSINESS_LICENSE)

        if business_score >= 2 and business_score >= id_score + 1:
            logger.info(
                "证件自动判型命中营业执照关键词: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
                requested or "auto",
                ClientIdentityDoc.BUSINESS_LICENSE,
                business_score,
                id_score,
            )
            return str(ClientIdentityDoc.BUSINESS_LICENSE)

        if has_any(("passport", "护照", "nationality", "passport no", "issuing country")):
            return str(ClientIdentityDoc.PASSPORT)

        if has_any(("港澳", "通行证", "往来港澳", "hk", "macao")):
            return str(ClientIdentityDoc.HK_MACAO_PERMIT)

        if has_any(("户口本", "常住人口登记", "户主", "与户主关系")):
            return str(ClientIdentityDoc.HOUSEHOLD_REGISTER)

        if has_any(("居住证", "residence permit")):
            return str(ClientIdentityDoc.RESIDENCE_PERMIT)

        if has_any(("法定代表人", "负责人", "法人身份证")) and re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
            return str(ClientIdentityDoc.LEGAL_REP_ID_CARD)

        logger.info(
            "证件自动判型回退身份证: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
            requested or "auto",
            ClientIdentityDoc.ID_CARD,
            business_score,
            id_score,
        )
        return str(ClientIdentityDoc.ID_CARD)

    def _extract_by_rules(self, raw_text: str, doc_type: str) -> dict[str, Any] | None:
        """规则提取：当前覆盖身份证与法代身份证。"""
        if doc_type not in {"id_card", "legal_rep_id_card"}:
            return None

        text = self._prepare_text_for_ollama(raw_text)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        merged = "\n".join(lines)

        id_number = self._extract_id_number(merged)
        name = self._extract_name(lines)
        gender = self._extract_gender(lines)
        ethnicity = self._extract_ethnicity(lines)
        address = self._extract_address(lines)
        expiry_date = self._extract_expiry_date(lines)
        birth_date = self._extract_birth_date(merged, id_number)

        extracted: dict[str, Any] = {
            "name": name,
            "id_number": id_number,
            "address": address,
            "expiry_date": expiry_date,
            "gender": gender,
            "ethnicity": ethnicity,
            "birth_date": birth_date,
        }

        return extracted

    def _extract_id_number(self, text: str) -> str | None:
        match = re.search(r"(?<!\d)(\d{17}[\dXx])(?!\d)", text)
        if not match:
            return None
        return match.group(1).upper()

    def _extract_name(self, lines: list[str]) -> str | None:
        for line in lines:
            match = re.search(r"姓名[:：]?([\u4e00-\u9fa5·]{2,20})", line)
            if match:
                return match.group(1)
        return None

    def _extract_gender(self, lines: list[str]) -> str | None:
        for line in lines:
            match = re.search(r"性别[:：]?([男女])", line)
            if match:
                return match.group(1)
        return None

    def _extract_ethnicity(self, lines: list[str]) -> str | None:
        for line in lines:
            match = re.search(r"民族[:：]?([\u4e00-\u9fa5]{1,8})", line)
            if match:
                return match.group(1)
        return None

    def _extract_birth_date(self, text: str, id_number: str | None) -> str | None:
        # 优先取“出生”行
        match = re.search(r"出生[:：]?\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", text)
        if match:
            return self._format_date_parts(match.group(1), match.group(2), match.group(3))

        # 兜底：身份证号中解析出生日期（第7-14位）
        if id_number and len(id_number) >= 14 and id_number[:17].isdigit():
            year, month, day = id_number[6:10], id_number[10:12], id_number[12:14]
            return self._format_date_parts(year, month, day)

        return None

    def _extract_expiry_date(self, lines: list[str]) -> str | None:
        for line in lines:
            if "长期" in line and ("有效" in line or "期限" in line):
                return "2099-12-31"

            range_match = re.search(
                r"(?:有效期限?|有效期)?[:：]?\s*(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})\s*(?:[-~至到])\s*(长期|\d{4}[.\-/年]\d{1,2}[.\-/月]\d{1,2})",
                line,
            )
            if range_match:
                end_part = range_match.group(4)
                if end_part == "长期":
                    return "2099-12-31"

                end_date_match = re.search(r"(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})", end_part)
                if end_date_match:
                    return self._format_date_parts(
                        end_date_match.group(1),
                        end_date_match.group(2),
                        end_date_match.group(3),
                    )

            until_match = re.search(r"(?:有效期限?|有效期至)[:：]?\s*(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})", line)
            if until_match:
                return self._format_date_parts(until_match.group(1), until_match.group(2), until_match.group(3))

        return None

    def _extract_address(self, lines: list[str]) -> str | None:
        address_parts: list[str] = []
        collecting = False
        stop_keywords = ("公民身份号码", "有效期限", "签发机关", "机关")

        for line in lines:
            if any(keyword in line for keyword in stop_keywords):
                break

            if line.startswith("住址"):
                collecting = True
                tail = line.replace("住址", "", 1).strip(" :：")
                if tail:
                    address_parts.append(tail)
                continue

            if collecting:
                if re.fullmatch(r"\d{17}[\dXx]", line):
                    break
                address_parts.append(line)

        if not address_parts:
            return None

        return "".join(address_parts)

    def _format_date_parts(self, year: str, month: str, day: str) -> str | None:
        try:
            y = int(year)
            m = int(month)
            d = int(day)
        except ValueError:
            return None
        if y <= 1900 or m <= 0 or d <= 0 or m > 12 or d > 31:
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"

    def _ollama_extract(self, raw_text: str, doc_type: str) -> dict[str, Any]:
        """
        使用 Ollama 从文字中提取结构化信息
        """
        try:
            llm_text = self._prepare_text_for_ollama(raw_text)
            logger.info("发送 Ollama 前 OCR 文本清洗完成: 原始长度=%d, 清洗后长度=%d", len(raw_text), len(llm_text))
            logger.info("发送 Ollama 前 OCR 清洗后文本内容:\n%s", llm_text)

            prompt = get_prompt_for_doc_type(doc_type, llm_text)
            logger.info("证件识别将调用 Ollama: model=%s, timeout=%ss, max_tokens=%s, think=%s", self._ollama_model, max(180, int(LLMConfig.get_ollama_timeout())), 256, False)

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"请从以下文字中提取信息:\n{llm_text}"},
            ]

            ollama_timeout = max(180, int(LLMConfig.get_ollama_timeout()))
            llm_service = get_llm_service()
            llm_resp = llm_service.chat(
                messages=messages,
                backend="ollama",
                model=self._ollama_model,
                max_tokens=256,
                timeout=ollama_timeout,
                think=False,
                fallback=False,
            )
            content = llm_resp.content or ""
            if not content:
                raise OllamaExtractionError(_("Ollama 返回内容为空"))

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
                return dict(extracted_data)

            except json.JSONDecodeError as e:
                logger.exception("Ollama 返回的 JSON 格式错误: %s", e)
                raise OllamaExtractionError(_("智能识别结果解析失败，请稍后重试")) from e

        except ConnectionError as e:
            logger.exception("Ollama 服务连接失败: %s", e)
            raise ServiceUnavailableError(
                message=_("Ollama 服务连接失败: %(e)s") % {"e": e}, service_name="Ollama"
            ) from e
        except LLMTimeoutError as e:
            logger.warning("Ollama 请求超时: %s", e)
            raise OllamaExtractionError(_("智能识别超时，请稍后重试。若多次失败，请检查 Ollama 服务状态后重试")) from e
        except LLMNetworkError as e:
            logger.warning("Ollama 网络异常: %s", e)
            raise OllamaExtractionError(_("无法连接智能识别服务，请检查 Ollama 服务或网络后重试")) from e
        except OllamaExtractionError:
            raise
        except Exception as e:
            logger.exception("Ollama 提取失败: %s", e)
            raise OllamaExtractionError(_("智能识别暂时不可用，请稍后重试")) from e

    def safe_extract(
        self,
        image_bytes: bytes,
        doc_type: str,
        enable_ollama: bool = True,
        source_name: str | None = None,
    ) -> dict[str, Any]:
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
            extraction = self.extract(
                image_bytes,
                doc_type,
                enable_ollama=enable_ollama,
                source_name=source_name,
            )
            result["success"] = True
            result["doc_type"] = extraction.doc_type
            result["extracted_data"] = extraction.extracted_data
            result["confidence"] = extraction.confidence
        except (OCRExtractionError, OllamaExtractionError) as e:
            result["error"] = str(e)
        except ServiceUnavailableError as e:
            logger.warning("证件识别服务不可用: %s", e)
            result["error"] = str(_("智能识别服务暂时不可用，请稍后重试"))
        except ValidationException as e:
            result["error"] = str(e)
        except Exception as e:
            logger.exception("证件识别未知错误: %s", e)
            result["error"] = str(_("识别过程中发生未知错误，请稍后重试"))
        return result
