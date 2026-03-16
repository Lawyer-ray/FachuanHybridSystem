"""
关键信息提取器

调用 Ollama 大模型从法院文书中提取关键信息（案号、开庭时间等）。
支持正则表达式提取和 Ollama 交叉校验机制。

Requirements: 4.3, 4.4, 4.7
"""

import logging
from datetime import datetime
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.automation.services.ai import get_ollama_base_url, get_ollama_model
from apps.automation.services.ai.ollama_client import chat
from apps.core.exceptions import RecognitionTimeoutError, ServiceUnavailableError

from ._case_number_mixin import CaseNumberMixin
from ._datetime_extraction_mixin import DatetimeExtractionMixin
from ._response_parser_mixin import ResponseParserMixin

logger = logging.getLogger("apps.document_recognition")


class InfoExtractor(CaseNumberMixin, DatetimeExtractionMixin, ResponseParserMixin):
    """
    关键信息提取器

    使用 Ollama 大模型从法院文书中提取关键信息：
    - 传票：案号、开庭时间
    - 执行裁定书：案号、财产保全到期时间（预留扩展）

    Requirements: 4.3, 4.4
    """

    SUMMONS_PROMPT = """请从以下传票内容中提取案号和开庭时间。

传票内容：
{text}

提取要求：
1. 案号格式：（年份）法院代码+案件类型字号+序号+号
   - 年份：4位数字，如2024、2025
   - 法院代码：省份简称+区县代码，如"粤0604"、"京0105"、"沪0115"
   - 案件类型字号（必须包含）：民初、民终、刑初、刑终、执、执保、执异、执恢、破、行初、行终等
   - 序号：数字
   - 必须以"号"字结尾
   - 示例：（2024）粤0604民初41257号、（2025）京0105刑初12345号

2. 重要：案号中必须包含案件类型字号（如民初、民终、刑初等），不能省略！
   - 错误示例：（2025）粤060441257（缺少案件类型）
   - 正确示例：（2025）粤0604民初41257号

3. 开庭时间需要包含完整的日期和时间，格式为：YYYY-MM-DD HH:MM

4. 如果无法确定某个字段，请返回 null

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"case_number": "案号或null", "court_time": "YYYY-MM-DD HH:MM或null"}}
"""

    EXECUTION_PROMPT = """请从以下执行裁定书中提取案号和财产保全到期时间。

裁定书内容：
{text}

提取要求：
1. 案号格式：（年份）法院代码+案件类型字号+序号+号
   - 年份：4位数字，如2024、2025
   - 法院代码：省份简称+区县代码，如"粤0604"、"京0105"
   - 案件类型字号（必须包含）：执、执保、执异、执恢、民初、民终等
   - 序号：数字
   - 必须以"号"字结尾
   - 示例：（2024）粤0604执保12345号、（2025）京0105执12345号

2. 重要：案号中必须包含案件类型字号，不能省略！

3. 财产保全到期时间格式为：YYYY-MM-DD

4. 如果无法确定某个字段，请返回 null

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"case_number": "案号或null", "preservation_deadline": "YYYY-MM-DD或null"}}
"""

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
    ):
        self.ollama_model = ollama_model or get_ollama_model()
        self.ollama_base_url = ollama_base_url or get_ollama_base_url()

    def extract_summons_info(self, text: str) -> dict[str, Any]:
        """
        提取传票信息

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

        ollama_result: dict[str, Any] = {"case_number": None, "court_time": None}
        ollama_datetime: datetime | None = None

        try:
            prompt = self.SUMMONS_PROMPT.format(text=truncated_text)
            response = chat(
                model=self.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                base_url=self.ollama_base_url,
            )
            ollama_result = self._parse_summons_response(response)
            ollama_datetime = ollama_result.get("court_time")
            if ollama_datetime:
                logger.info(f"Ollama 提取到时间: {ollama_datetime}")
            if regex_case_number is None and ollama_result.get("case_number"):
                logger.info(f"Ollama 提取到案号: {ollama_result.get('case_number')}")
        except ConnectionError as e:
            logger.warning(f"Ollama 服务不可用，将仅使用正则结果: {e}")
        except TimeoutError as e:
            logger.warning(f"Ollama 提取超时，将仅使用正则结果: {e}")
        except Exception as e:
            logger.warning(f"Ollama 提取失败，将仅使用正则结果: {e}")

        best_datetime, extraction_method = self._select_best_datetime(regex_datetimes, ollama_datetime)
        logger.info(f"最终选择时间: {best_datetime}, 方法: {extraction_method}")

        final_case_number = regex_case_number if regex_case_number else ollama_result.get("case_number")
        case_number_source = "regex" if regex_case_number else ("ollama" if ollama_result.get("case_number") else None)

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
        提取执行裁定书信息（预留扩展）

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

        try:
            prompt = self.EXECUTION_PROMPT.format(text=truncated_text)
            response = chat(
                model=self.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                base_url=self.ollama_base_url,
            )
            result = self._parse_execution_response(response)
            logger.info(
                "执行裁定书信息提取完成",
                extra={
                    "action": "extract_execution_info",
                    "case_number": result.get("case_number"),
                    "preservation_deadline": (
                        str(result.get("preservation_deadline")) if result.get("preservation_deadline") else None
                    ),
                },
            )
            return result
        except ConnectionError as e:
            logger.error(
                f"Ollama 服务不可用: {e}",
                extra={"action": "extract_execution_info", "error_type": "connection_error", "error": str(e)},
            )
            raise ServiceUnavailableError(
                message=_("AI 服务暂时不可用，请稍后重试"),
                code="OLLAMA_SERVICE_UNAVAILABLE",
                errors={"service": "Ollama 服务连接失败"},
                service_name="Ollama",
            ) from e
        except TimeoutError as e:
            logger.error(
                f"执行裁定书信息提取超时: {e}",
                extra={"action": "extract_execution_info", "error_type": "timeout_error", "error": str(e)},
            )
            raise RecognitionTimeoutError(
                message=_("信息提取超时，请重试"),
                code="EXTRACTION_TIMEOUT",
                errors={"timeout": "AI 提取超时"},
            ) from e
        except Exception as e:
            logger.error(
                f"执行裁定书信息提取失败: {e!s}",
                extra={"action": "extract_execution_info", "error_type": type(e).__name__, "error": str(e)},
                exc_info=True,
            )
            raise RuntimeError(f"执行裁定书信息提取失败: {e!s}") from e
