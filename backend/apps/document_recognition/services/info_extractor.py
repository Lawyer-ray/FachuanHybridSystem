"""
关键信息提取器

从法院文书中提取关键信息（案号、开庭时间等）。
正则先行（确定性、带上下文打分），LLM 结果来自 document_analyzer 的
单次结构化分析（经 recognition_service 注入共享，不单独发调用），
两者交叉校验择优。

Requirements: 4.3, 4.4, 4.7
"""

import logging
from datetime import datetime
from typing import Any, Callable

from apps.core.llm.config import LLMConfig

from ._case_number_mixin import CaseNumberMixin
from ._datetime_extraction_mixin import DatetimeExtractionMixin
from ._response_parser_mixin import ResponseParserMixin
from .document_analyzer import CourtDocumentAnalysis, DocumentAnalysisOutcome

logger = logging.getLogger("apps.document_recognition")


def get_ollama_model() -> str:  # pragma: no cover
    """兼容旧测试与调用方：保留模块级配置读取入口。"""
    return LLMConfig.get_ollama_model()


def get_ollama_base_url() -> str:  # pragma: no cover
    """兼容旧测试与调用方：保留模块级配置读取入口。"""
    return LLMConfig.get_ollama_base_url()


class InfoExtractor(CaseNumberMixin, DatetimeExtractionMixin, ResponseParserMixin):
    """
    关键信息提取器

    提取策略（正则 + LLM 交叉校验）：
    - 案号：正则命中直接采用（格式严格、可靠）；正则未命中时回退 LLM 结果；
      两者冲突时以正则为准并记日志。
    - 开庭时间：正则候选（带上下文打分）与 LLM 结果经 ``_select_best_datetime``
      择优；``extraction_method`` 记录最终来源。
    - 未注入 ``analysis_lookup`` 时仅用正则（单测与降级路径）。

    Requirements: 4.3, 4.4
    """

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
        llm_service: Any | None = None,
        analysis_lookup: Callable[[str], DocumentAnalysisOutcome] | None = None,
    ):
        # ollama_model/ollama_base_url/llm_service 为兼容保留参数（旧双调用架构）；
        # 不读系统配置，避免构造期触发 DB 访问（无 django_db 标记的单测会被阻断）
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self._llm_service = llm_service
        self._analysis_lookup = analysis_lookup

    def _shared_analysis(self, text: str) -> CourtDocumentAnalysis | None:
        """取 per-run 共享分析结果；未注入或分析失败返回 None。"""
        if self._analysis_lookup is None:
            return None
        try:
            outcome = self._analysis_lookup(text)
        except Exception as e:  # pragma: no cover - lookup 内部已折叠异常
            logger.warning("共享文书分析调用异常: %s", e)
            return None
        return outcome.analysis if outcome is not None else None

    def extract_summons_info(self, text: str) -> dict[str, Any]:
        """
        提取传票信息（案号 + 开庭时间，正则与 LLM 交叉校验）

        Requirements: 4.3
        """
        if not text or not text.strip():
            logger.warning(
                "传票内容为空，无法提取信息",
                extra={"action": "extract_summons_info", "result": "empty_text"},
            )
            return {"case_number": None, "court_time": None, "extraction_method": None}

        truncated_text = text[:4000] if len(text) > 4000 else text
        logger.info(
            "开始提取传票信息",
            extra={"action": "extract_summons_info", "text_length": len(text), "truncated_length": len(truncated_text)},
        )

        regex_case_number = self._extract_case_number_by_regex(truncated_text)
        if regex_case_number:
            logger.info(f"正则成功提取案号: {regex_case_number}")

        regex_datetimes = self._extract_datetime_by_regex(truncated_text)
        logger.info(f"正则提取到 {len(regex_datetimes)} 个时间候选")
        for dt, matched_text, score in regex_datetimes:
            logger.info(f"  - {dt} (原文: {matched_text}, 得分: {score})")

        llm_case_number: str | None = None
        llm_datetime: datetime | None = None

        analysis = self._shared_analysis(truncated_text)
        if analysis is not None:
            raw_case_number = (analysis.case_number or "").strip()
            if raw_case_number and raw_case_number.lower() != "null":
                llm_case_number = self._normalize_case_number(raw_case_number)
                if not regex_case_number:
                    logger.info(f"LLM 提取到案号: {llm_case_number}")
                elif llm_case_number != regex_case_number:
                    logger.warning(f"案号交叉校验不一致，以正则为准: 正则={regex_case_number}, LLM={llm_case_number}")
            llm_datetime = self._parse_datetime(analysis.court_time or "") if analysis.court_time else None
            if llm_datetime:
                logger.info(f"LLM 提取到时间: {llm_datetime}")

        best_datetime, extraction_method = self._select_best_datetime(regex_datetimes, llm_datetime)
        logger.info(f"最终选择时间: {best_datetime}, 方法: {extraction_method}")

        final_case_number = regex_case_number if regex_case_number else llm_case_number
        case_number_source = "regex" if regex_case_number else ("llm" if llm_case_number else None)

        result = {
            "case_number": final_case_number,
            "court_time": best_datetime,
            "extraction_method": extraction_method,
        }
        logger.info(
            "传票信息提取完成",
            extra={
                "action": "extract_summons_info",
                "case_number": result.get("case_number"),
                "case_number_source": case_number_source,
                "court_time": str(result.get("court_time")) if result.get("court_time") else None,
                "extraction_method": extraction_method,
            },
        )
        return result

    def extract_execution_info(self, text: str) -> dict[str, Any]:
        """
        提取执行裁定书信息（案号 + 财产保全到期时间）

        Requirements: 4.4
        """
        if not text or not text.strip():
            logger.warning(
                "执行裁定书内容为空，无法提取信息",
                extra={"action": "extract_execution_info", "result": "empty_text"},
            )
            return {"case_number": None, "preservation_deadline": None}

        truncated_text = text[:4000] if len(text) > 4000 else text
        logger.info(
            "开始提取执行裁定书信息",
            extra={
                "action": "extract_execution_info",
                "text_length": len(text),
                "truncated_length": len(truncated_text),
            },
        )

        regex_case_number = self._extract_case_number_by_regex(truncated_text)
        if regex_case_number:
            logger.info(f"正则成功提取案号: {regex_case_number}")

        final_case_number = regex_case_number
        preservation_deadline: datetime | None = None

        analysis = self._shared_analysis(truncated_text)
        if analysis is not None:
            if not final_case_number:
                raw_case_number = (analysis.case_number or "").strip()
                if raw_case_number and raw_case_number.lower() != "null":
                    final_case_number = self._normalize_case_number(raw_case_number)
                    logger.info(f"LLM 提取到案号: {final_case_number}")
            if analysis.court_time:
                preservation_deadline = self._parse_date(analysis.court_time)
                if preservation_deadline:
                    logger.info(f"LLM 提取到保全到期时间: {preservation_deadline}")

        logger.info(
            "执行裁定书信息提取完成",
            extra={
                "action": "extract_execution_info",
                "case_number": final_case_number,
                "preservation_deadline": (str(preservation_deadline) if preservation_deadline else None),
            },
        )
        return {
            "case_number": final_case_number,
            "preservation_deadline": preservation_deadline,
        }
