"""
文书类型分类器

主路径：消费 document_analyzer 的单次结构化分析结果（与关键信息提取共享
同一次 LLM 调用）；降级路径：关键词规则分类（LLM 不可用或未注入分析时）。

Requirements: 4.1, 4.2, 4.7
"""

import json
import logging
from typing import Any, Callable, cast

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.core.llm.structured_output import json_schema_instructions

from .data_classes import DocumentType
from .document_analyzer import CourtDocumentAnalysis, DocumentAnalysisOutcome

logger = logging.getLogger("apps.document_recognition")


def get_ollama_model() -> str:  # pragma: no cover
    """兼容旧测试与调用方：保留模块级配置读取入口。"""
    return LLMConfig.get_ollama_model()


def get_ollama_base_url() -> str:  # pragma: no cover
    """兼容旧测试与调用方：保留模块级配置读取入口。"""
    return LLMConfig.get_ollama_base_url()


def chat(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    llm_service: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:  # pragma: no cover
    """
    兼容旧测试与调用方：保留模块级 chat 入口，内部转发到统一 LLM 服务。
    """
    service = llm_service or ServiceLocator.get_llm_service()
    llm_response = service.chat(messages=messages, model=model, **kwargs)
    return {"message": {"content": llm_response.content}}


class DocumentClassifier:
    """
    文书类型分类器

    - 注入 ``analysis_lookup``（recognition_service 的 per-run 共享分析）时，
      优先消费其结构化结果——与关键信息提取共用同一次 LLM 调用；
    - 未注入或分析失败时，退到关键词规则分类（确定性、零外部依赖）。

    Requirements: 4.1, 4.2
    """

    # 分类提示词模板（历史遗留：旧双调用架构使用，保留给兼容测试；
    # 生产路径的提示词在 document_analyzer.ANALYSIS_PROMPT）
    CLASSIFICATION_PROMPT = """请分析以下法院文书内容，判断文书类型。

文书内容：
{text}

请判断这是以下哪种类型的文书：
1. summons - 传票（包含开庭时间、出庭通知等）
2. execution - 执行裁定书（包含财产保全、执行裁定等）
3. other - 其他类型文书

判断依据：
- 传票通常包含：开庭时间、出庭地点、案号、当事人信息
- 执行裁定书通常包含：财产保全、查封、冻结、执行裁定等关键词
- 如果无法确定或不属于以上两种，请返回 other

请严格按照以下 JSON 格式返回结果，不要包含其他内容：
{{"type": "summons|execution|other", "confidence": 0.0-1.0, "reason": "判断理由"}}
"""

    # 关键词分类规则（降级路径）：顺序即优先级，更具体的靠前
    KEYWORD_TYPE_RULES: list[tuple[str, DocumentType]] = [
        ("执行裁定书", DocumentType.EXECUTION_RULING),
        ("执行裁定", DocumentType.EXECUTION_RULING),
        ("财产保全", DocumentType.EXECUTION_RULING),
        ("查封", DocumentType.EXECUTION_RULING),
        ("冻结", DocumentType.EXECUTION_RULING),
        ("开庭传票", DocumentType.SUMMONS),
        ("传票", DocumentType.SUMMONS),
        ("出庭通知", DocumentType.SUMMONS),
        ("开庭", DocumentType.SUMMONS),
        ("到庭", DocumentType.SUMMONS),
    ]

    KEYWORD_CONFIDENCE = 0.6

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
        llm_service: Any | None = None,
        analysis_lookup: Callable[[str], DocumentAnalysisOutcome] | None = None,
    ):
        """
        Args:
            ollama_model: 兼容保留参数（旧双调用架构使用；不读系统配置，
                避免构造期触发 DB 访问）
            ollama_base_url: 兼容保留参数
            llm_service: 兼容保留参数
            analysis_lookup: per-run 共享结构化分析（recognition_service 注入）
        """
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self._llm_service = llm_service
        self._analysis_lookup = analysis_lookup

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = ServiceLocator.get_llm_service()
        return self._llm_service

    @staticmethod
    def schema_instructions() -> str:
        """结构化输出说明（供旧提示词消费方参考）。"""
        return json_schema_instructions(CourtDocumentAnalysis)

    def classify(self, text: str) -> tuple[DocumentType, float]:
        """
        分类文书类型

        Args:
            text: 文书文本内容

        Returns:
            Tuple[DocumentType, float]: (文书类型, 置信度)

        Requirements: 7.2, 7.3
        """
        if not text or not text.strip():
            logger.warning("文书内容为空，返回 OTHER 类型", extra={"action": "classify", "result": "empty_text"})
            return DocumentType.OTHER, 0.0

        analysis = self._shared_analysis(text)
        if analysis is not None:
            doc_type = self._map_type_string(analysis.document_type)
            confidence = max(0.0, min(1.0, float(analysis.confidence)))
            logger.info(
                "文书分类完成（结构化分析）",
                extra={"action": "classify", "document_type": doc_type.value, "confidence": confidence},
            )
            return doc_type, confidence

        doc_type, confidence = self._classify_by_keywords(text)
        logger.info(
            "文书分类完成（关键词降级）",
            extra={"action": "classify", "document_type": doc_type.value, "confidence": confidence},
        )
        return doc_type, confidence

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

    def _classify_by_keywords(self, text: str) -> tuple[DocumentType, float]:
        """关键词规则分类（确定性降级路径）。"""
        for keyword, doc_type in self.KEYWORD_TYPE_RULES:
            if keyword in text:
                return doc_type, self.KEYWORD_CONFIDENCE
        return DocumentType.OTHER, 0.5

    def _parse_classification_response(self, response: dict[str, Any]) -> tuple[DocumentType, float]:
        """
        解析 LLM 分类响应（历史遗留：旧双调用架构使用，兼容测试保留）

        Args:
            response: LLM API 响应

        Returns:
            Tuple[DocumentType, float]: (文书类型, 置信度)
        """
        try:
            # 提取响应内容
            if "message" not in response or "content" not in response["message"]:
                logger.warning("LLM 响应格式异常，返回 OTHER 类型")
                return DocumentType.OTHER, 0.0

            content = response["message"]["content"]

            # 尝试解析 JSON
            result = self._extract_json_from_response(content)

            if result is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return DocumentType.OTHER, 0.0

            # 提取类型
            type_str = result.get("type", "other").lower()
            doc_type = self._map_type_string(type_str)

            # 提取置信度
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # 限制在 0-1 范围

            # 记录判断理由
            reason = result.get("reason", "")
            if reason:
                logger.debug(f"分类理由: {reason}")

            return doc_type, confidence

        except (TypeError, ValueError) as e:
            logger.warning(f"解析分类响应失败: {e!s}")
            return DocumentType.OTHER, 0.0

    def _extract_json_from_response(self, content: str) -> dict[str, Any] | None:
        """
        从响应内容中提取 JSON

        支持处理包含额外文本的响应。

        Args:
            content: 响应内容

        Returns:
            Optional[dict]: 解析出的 JSON 对象，失败返回 None
        """
        content = content.strip()

        # 直接尝试解析
        try:
            return cast(dict[str, Any] | None, json.loads(content))
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        # 查找 { 和 } 的位置
        start_idx = content.find("{")
        end_idx = content.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx : end_idx + 1]
            try:
                return cast(dict[str, Any] | None, json.loads(json_str))
            except json.JSONDecodeError:
                pass

        # 尝试处理 markdown 代码块
        if "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return cast(dict[str, Any] | None, json.loads(json_str))
            except (ValueError, json.JSONDecodeError):
                pass

        if "```" in content:
            try:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return cast(dict[str, Any] | None, json.loads(json_str))
            except (ValueError, json.JSONDecodeError):
                pass

        return None

    def _map_type_string(self, type_str: str) -> DocumentType:
        """
        将类型字符串映射为 DocumentType 枚举

        Args:
            type_str: 类型字符串

        Returns:
            DocumentType: 文书类型枚举
        """
        type_mapping = {
            "summons": DocumentType.SUMMONS,
            "传票": DocumentType.SUMMONS,
            "execution": DocumentType.EXECUTION_RULING,
            "执行裁定书": DocumentType.EXECUTION_RULING,
            "execution_ruling": DocumentType.EXECUTION_RULING,
            "other": DocumentType.OTHER,
            "其他": DocumentType.OTHER,
        }

        return type_mapping.get(type_str.lower(), DocumentType.OTHER)
