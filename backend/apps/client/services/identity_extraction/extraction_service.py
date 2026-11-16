"""证件信息提取服务（编排层）。

使用 RapidOCR (PP-OCRv5) 提取图片文字,然后用 LLM 结构化提取信息.

具体实现按子域拆分在本包内：
- ``ocr``：图片/PDF 的 OCR IO
- ``text_cleaning``：OCR 文本清洗与日志脱敏
- ``doc_type_detection``：证件类型自动判型
- ``rules``：身份证/营业执照/叙述式规则提取与置信度
- ``llm_extraction``：LLM 结构化提取与 JSON 解析
- ``validators``：证件号码校验位

本类只保留编排（extract/safe_extract）与 OCR 分发；其余方法为兼容既有
调用方/测试的薄委托，实现均在上述模块。
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ServiceUnavailableError, ValidationException
from apps.core.protocols import IOcrService

from . import ocr
from .data_classes import ExtractionResult, LLMExtractionError, OCRExtractionError
from .doc_type_detection import _resolve_doc_type
from .llm_extraction import _llm_extract, _parse_llm_json
from .rules import business_license as business_license_rules
from .rules import confidence as confidence_rules
from .rules import id_card as id_card_rules
from .rules import narrative as narrative_rules
from .text_cleaning import (
    _MAX_LLM_OCR_CHARS,
    _MAX_LLM_OCR_LINES,
    _is_meaningful_line,
    _looks_like_json_noise,
    _normalize_ocr_text,
    _prepare_text_for_llm,
)
from .validators import _validate_credit_code, _validate_id_number

logger = logging.getLogger(__name__)

__all__ = [
    "IdentityExtractionService",
    "_MAX_LLM_OCR_CHARS",
    "_MAX_LLM_OCR_LINES",
    "_normalize_ocr_text",
    "_parse_llm_json",
    "_validate_credit_code",
    "_validate_id_number",
]

# 「有效期限」是**起止区间**的证件类型：到期日是区间末日，正则极易错拿签发日。
# 此类证件即使规则命中关键字段，也必须同时跑 LLM 交叉校验。
_DOC_TYPES_WITH_EXPIRY_RANGE = frozenset({"id_card", "legal_rep_id_card"})


class IdentityExtractionService:
    """证件信息提取服务 - 使用 RapidOCR (PP-OCRv5) + LLM"""

    def __init__(
        self,
        recognizer: Any | None = None,
        ocr_service: IOcrService | None = None,
    ) -> None:
        self._recognizer = recognizer
        if ocr_service is None:
            from apps.core.interfaces import ServiceLocator

            ocr_service = ServiceLocator.get_ocr_service()
        self._ocr_service = ocr_service

    def extract(
        self,
        image_bytes: bytes,
        doc_type: str,
        model: str | None = None,
        source_name: str | None = None,
    ) -> ExtractionResult:
        """
        提取证件信息

        Args:
            image_bytes: 图片字节数据
            doc_type: 证件类型
            model: LLM 模型名称（None 或空字符串表示不使用 LLM）

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
            # 提前初始化：规则提取返回 None 时下面的合并分支也要用到
            needs_llm_for_expiry = resolved_doc_type in _DOC_TYPES_WITH_EXPIRY_RANGE and bool(model)
            if extracted_data is not None:
                # 判断规则提取是否命中关键字段（元字段不参与判定）
                data_fields = {k: v for k, v in extracted_data.items() if k not in ("field_confidence",)}
                key_field_hit = bool(
                    data_fields.get("id_number") or data_fields.get("credit_code") or data_fields.get("company_name")
                )
                # 身份证类的「有效期限」是起止区间，正则极易把签发日错当当到期日。
                # 即使正则可命中身份证号，也不能跳过 LLM——实跌 2026-11-06：
                # 年月日格式/OCR 断行时正则返回 2025-11-07（签发日），真值 2045-11-07，
                # 会直接造成「已过期」误报。此类证件一律同时跑 LLM 做交叉校验。
                if (key_field_hit and not needs_llm_for_expiry) or not model:
                    logger.info(
                        "证件识别使用规则提取: requested_doc_type=%s, resolved_doc_type=%s, model=%s, key_field_hit=%s",
                        doc_type,
                        resolved_doc_type,
                        model,
                        key_field_hit,
                    )
                    overall = self._overall_confidence(extracted_data)
                    return ExtractionResult(
                        doc_type=resolved_doc_type,
                        raw_text=raw_text,
                        extracted_data=extracted_data,
                        confidence=overall,
                        extraction_method="ocr_regex",
                    )

                logger.info(
                    "规则提取未命中关键字段且指定了模型，回退 LLM 提取: requested_doc_type=%s, resolved_doc_type=%s, model=%s",
                    doc_type,
                    resolved_doc_type,
                    model,
                )

            # 3. 规则无法覆盖时，仅在用户指定了模型时回退 LLM
            if not model:
                logger.info(
                    "规则提取未覆盖且未指定 LLM 模型，返回部分结果: resolved_doc_type=%s",
                    resolved_doc_type,
                )
                return ExtractionResult(
                    doc_type=resolved_doc_type,
                    raw_text=raw_text,
                    extracted_data=extracted_data or {},
                    confidence=0.3,
                    extraction_method="ocr_regex_partial",
                )

            llm_data = self._llm_extract(raw_text, resolved_doc_type, model)

            if needs_llm_for_expiry and extracted_data is not None:
                # 身份证类：以 LLM 为准，正则结果仅用于发现分歧。
                # 实跌正则会把签发日错当当到期日（2025-11-07 vs 真值 2045-11-07），
                # 故不一致时保留 LLM 值并告警，便于事后量化正则问题。
                regex_expiry = (extracted_data or {}).get("expiry_date")
                llm_expiry = llm_data.get("expiry_date")
                if regex_expiry != llm_expiry:
                    logger.warning(
                        "证件到期日正则与 LLM 不一致，以 LLM 为准: doc_type=%s, regex=%s, llm=%s",
                        resolved_doc_type,
                        regex_expiry,
                        llm_expiry,
                    )
                # 其余字段（姓名/地址等）保留正则的高置信结果，只改用 LLM 的到期日
                merged = dict(extracted_data or {})
                merged.update({k: v for k, v in llm_data.items() if v not in (None, "")})
                merged["expiry_date"] = llm_expiry
                return ExtractionResult(
                    doc_type=resolved_doc_type,
                    raw_text=raw_text,
                    extracted_data=merged,
                    confidence=0.9,
                    extraction_method="ocr_regex_llm",
                )

            return ExtractionResult(
                doc_type=resolved_doc_type,
                raw_text=raw_text,
                extracted_data=llm_data,
                confidence=0.8,
                extraction_method="ocr_llm",
            )

        except (OCRExtractionError, LLMExtractionError, ServiceUnavailableError):
            raise
        except Exception as e:
            logger.exception("证件信息提取失败: %s", e)
            raise ValidationException(
                message=_("证件信息提取失败: %(error)s") % {"error": str(e)},
                code="EXTRACTION_FAILED",
                errors={"extraction": str(e)},
            ) from e

    def safe_extract(
        self,
        image_bytes: bytes,
        doc_type: str,
        model: str | None = None,
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
            "raw_text": "",
        }
        # Service 层内部允许 try/except（规范禁止的是 API 层）
        try:
            extraction = self.extract(
                image_bytes,
                doc_type,
                model=model,
                source_name=source_name,
            )
            result["success"] = True
            result["doc_type"] = extraction.doc_type
            result["extracted_data"] = extraction.extracted_data
            result["confidence"] = extraction.confidence
            result["raw_text"] = extraction.raw_text
        except (OCRExtractionError, LLMExtractionError) as e:
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

    # ── OCR 分发（保留 self.* 调用，测试通过 patch.object 替换子步骤）──

    def _ocr_extract(self, image_bytes: bytes) -> str:
        """使用 RapidOCR (PP-OCRv5) 提取图片/PDF文字。"""
        try:
            if self._recognizer is not None and hasattr(self._recognizer, "classification"):
                try:
                    raw_text = self._recognizer.classification(image_bytes) or ""
                except Exception as e:
                    raise OCRExtractionError(_("OCR 提取失败: %(e)s") % {"e": e}) from e
                if raw_text.strip():
                    return raw_text.strip()
                raise OCRExtractionError(_("OCR 未能提取到有效文字"))

            if self._is_pdf_file(image_bytes):
                return self._extract_from_pdf(image_bytes)
            return self._extract_from_image(image_bytes)

        except OCRExtractionError:
            raise
        except Exception as e:
            logger.exception("OCR 提取失败: %s", e)
            raise OCRExtractionError(_("OCR 提取失败: %(e)s") % {"e": e}) from e

    def _is_pdf_file(self, file_bytes: bytes) -> bool:  # pragma: no cover
        return ocr._is_pdf_file(file_bytes)

    def _extract_from_image(self, image_bytes: bytes) -> str:  # pragma: no cover
        return ocr._extract_from_image(image_bytes, self._ocr_service)

    def _extract_from_pdf(self, pdf_bytes: bytes) -> str:  # pragma: no cover
        return ocr._extract_from_pdf(pdf_bytes, self._ocr_service)

    def _ocr_single_page(self, page: Any) -> str:
        return ocr._ocr_single_page(page, self._ocr_service)

    # ── 纯函数委托（实现见各子域模块，保留方法面兼容既有调用方/测试）──

    def _looks_like_json_noise(self, line: str) -> bool:
        return _looks_like_json_noise(line)

    def _is_meaningful_line(self, line: str) -> bool:
        return _is_meaningful_line(line)

    def _prepare_text_for_llm(self, raw_text: str) -> str:
        return _prepare_text_for_llm(raw_text)

    def _resolve_doc_type(self, doc_type: str, raw_text: str, source_name: str | None = None) -> str:
        return _resolve_doc_type(doc_type, raw_text, source_name=source_name)

    def _extract_by_rules(self, raw_text: str, doc_type: str) -> dict[str, Any] | None:
        # 经由 self.* 分发，保留实例级 patch 点（测试据此拦截各证件类型的提取）
        if doc_type == "business_license":
            return self._extract_business_license(raw_text)
        if doc_type not in {"id_card", "legal_rep_id_card"}:
            return None
        return id_card_rules._extract_id_card_fields(raw_text)

    def _extract_business_license(self, raw_text: str) -> dict[str, Any] | None:
        return business_license_rules._extract_business_license(raw_text)

    def _extract_id_number_candidates(self, text: str) -> list[str]:
        return id_card_rules._extract_id_number_candidates(text)

    def _select_best_id_number(self, text: str) -> tuple[str | None, bool]:
        return id_card_rules._select_best_id_number(text)

    def _extract_id_number(self, text: str) -> str | None:
        return id_card_rules._extract_id_number(text)

    def _extract_name(self, lines: list[str]) -> str | None:
        return id_card_rules._extract_name(lines)

    def _extract_gender(self, lines: list[str]) -> str | None:
        return id_card_rules._extract_gender(lines)

    def _extract_ethnicity(self, lines: list[str]) -> str | None:
        return id_card_rules._extract_ethnicity(lines)

    def _extract_birth_date(self, text: str, id_number: str | None) -> str | None:
        return id_card_rules._extract_birth_date(text, id_number)

    def _extract_expiry_date(self, lines: list[str]) -> str | None:
        return id_card_rules._extract_expiry_date(lines)

    def _extract_address(self, lines: list[str]) -> str | None:
        return id_card_rules._extract_address(lines)

    def _format_date_parts(self, year: str, month: str, day: str) -> str | None:
        return id_card_rules._format_date_parts(year, month, day)

    def _extract_narrative_address_by_boundary(self, flat: str) -> str | None:
        return narrative_rules._extract_narrative_address_by_boundary(flat)

    def _extract_narrative_fields(self, text: str) -> dict[str, Any]:
        return narrative_rules._extract_narrative_fields(text)

    def _compute_id_card_field_confidence(self, extracted: dict[str, Any], narrative_used: bool) -> dict[str, float]:
        return confidence_rules._compute_id_card_field_confidence(extracted, narrative_used)

    def _compute_business_license_field_confidence(self, extracted: dict[str, Any]) -> dict[str, float]:
        return confidence_rules._compute_business_license_field_confidence(extracted)

    def _overall_confidence(self, extracted_data: dict[str, Any]) -> float:
        return confidence_rules._overall_confidence(extracted_data)

    def _llm_extract(self, raw_text: str, doc_type: str, model: str) -> dict[str, Any]:  # pragma: no cover
        return _llm_extract(raw_text, doc_type, model)
