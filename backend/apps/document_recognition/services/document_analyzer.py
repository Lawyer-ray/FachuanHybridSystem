"""法院文书单次结构化分析（分类 + 关键信息提取合一）。

旧实现为「分类、提取两次 LLM 调用」；本模块合并为一次结构化调用：
prompt 要求模型直接返回文书类型 + 案号 + 关键时间的 JSON，经
``apps.core.llm.structured_output`` 做 pydantic 严格校验，校验失败带错误
反馈自动重试。

LLM 不指定 backend/model，由统一 LLM 层按「默认后端 + AI 平台默认模型」
路由（律所 kimi 平台）。LLM 不可用或重试后仍无法解析时返回
``analysis=None`` 的结果（软失败），由 recognition_service 降级到
关键词 + 正则路径。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError
from apps.core.llm.structured_output import StructuredValidationError, json_schema_instructions, retry_structured

logger = logging.getLogger("apps.document_recognition")

# 与旧实现一致：截断超长文本，避免超出模型上下文限制
MAX_ANALYSIS_CHARS = 4000

# LLM 分析整体预算（秒）：网关默认 timeout 120s，这里收紧到单任务 90s
ANALYSIS_TIMEOUT_SECONDS = 90.0


class ExtractedDateEvent(BaseModel):
    """文书中的一个关键日期事件。"""

    # YYYY-MM-DD HH:MM 或 YYYY-MM-DD
    datetime: str
    event_type: Literal[
        "hearing",
        "asset_preservation_expires",
        "evidence_deadline",
        "appeal_deadline",
        "payment_deadline",
        "submission_deadline",
        "statute_limitations",
        "other",
    ] = "other"
    # 原文片段（截断到 80 字内），供律师人工核对
    context: str = Field(default="", max_length=80)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class CourtDocumentAnalysis(BaseModel):
    """单次结构化分析结果。"""

    document_type: Literal["summons", "execution", "other"] = "other"
    # 案号格式如（2024）粤0604民初41257号；无法确定时为 null
    case_number: str | None = None
    # 开庭时间（传票）或财产保全到期时间（执行裁定书）；YYYY-MM-DD HH:MM 或 YYYY-MM-DD
    court_time: str | None = None
    # 文书中所有关键日期事件（开庭、举证截止、上诉届满、保全到期等），多个日期都要列出
    key_events: list[ExtractedDateEvent] = Field(default_factory=list)
    # 当事人名称（原告/被告/申请人/被申请人），供案件绑定推荐评分使用
    party_names: list[str] = Field(default_factory=list)
    # 法院名称，如"佛山市顺德区人民法院"
    court_name: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""


@dataclass
class DocumentAnalysisOutcome:
    """一次分析调用的完整结果（含可观测性信息）。

    ``analysis`` 为 None 表示 LLM 不可用或输出始终无法解析——调用方据此降级。
    """

    analysis: CourtDocumentAnalysis | None
    model: str | None = None
    backend: str | None = None
    latency_ms: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.analysis is not None


ANALYSIS_PROMPT = """你是法院文书分析助手。请分析以下法院文书，一次性完成五项任务：
1. 判断文书类型：summons=传票（含开庭时间、出庭通知），execution=执行裁定书（含财产保全、查封、冻结、执行裁定），other=其他文书；
2. 提取案号：格式为（年份）法院代码+案件类型字号+序号+号，如（2024）粤0604民初41257号，必须含案件类型字号（民初/民终/刑初/执/执保等）并以"号"字结尾；无法确定填 null；
3. 提取最关键的一个时间：传票取开庭时间，执行裁定书取财产保全到期时间；格式 YYYY-MM-DD HH:MM 或 YYYY-MM-DD；无法确定填 null；
4. 提取文书中**所有**关键日期事件，每个一条填入 key_events：开庭时间、举证截止日、上诉期届满日、财产保全到期日、缴费期限、补正/材料提交期限、诉讼时效届满日等；同一文书有多个日期都要列出（如多次开庭、举证截止+开庭日期并存）；每条给出 event_type、原文片段（context，不超过 60 字）、置信度；日期格式 YYYY-MM-DD HH:MM 或 YYYY-MM-DD（只有日期无时间时可省略时间）；期限为相对表述时（如「收到本通知次日起两日内交纳」「自收到本决定书之日起7日内付款」），以文书落款/打印/出具日期为锚点推算届满日期——起算当日不计入、自次日起算（如落款 2025-11-11、「次日起两日内」→ 2025-11-13，「（之）日起七日内」→ 落款+7天），切勿把落款日期本身直接当作期限事件日期；找不到锚点日期时省略该条，不要虚构日期；没有关键日期返回空数组；
5. 提取当事人名称（原告/被告/申请人/被申请人，去掉"原告""被告"等前缀只留名称）与法院名称；没有则 party_names 为空数组、court_name 为 null。

{schema_instructions}

文书内容：
{text}
"""


def analyze_document(
    text: str,
    *,
    llm_service: Any | None = None,
    max_attempts: int = 2,
    model: str | None = None,
) -> DocumentAnalysisOutcome:
    """单次结构化 LLM 调用完成分类 + 提取。

    Args:
        text: 文书全文（超长自动截断）
        llm_service: 可注入的 LLM 服务（默认 ServiceLocator）
        max_attempts: 输出解析失败时带反馈重试的总次数
        model: 指定模型（None 走统一 LLM 层默认模型）

    Returns:
        DocumentAnalysisOutcome；永不抛异常——LLM 不可用/超时/解析失败都
        折叠为 ``analysis=None``（软失败），调用方据此走降级路径。
    """
    if not text or not text.strip():
        return DocumentAnalysisOutcome(analysis=None, error="empty_text")

    truncated = text[:MAX_ANALYSIS_CHARS]
    prompt = ANALYSIS_PROMPT.format(
        schema_instructions=json_schema_instructions(CourtDocumentAnalysis),
        text=truncated,
    )

    if llm_service is None:
        from apps.core.interfaces import ServiceLocator

        llm_service = ServiceLocator.get_llm_service()

    started = time.monotonic()
    captured: dict[str, str | None] = {"model": None, "backend": None}

    def _respond(feedback: StructuredValidationError | None) -> str:
        content = prompt
        if feedback is not None:
            content = f"{prompt}\n\n{feedback.feedback_message}"
        response = llm_service.chat(
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
            model=model,
            caller="document_recognition.analyze_document",
        )
        captured["model"] = getattr(response, "model", None)
        captured["backend"] = getattr(response, "backend", None)
        return str(response.content or "")

    try:
        analysis = retry_structured(
            model_cls=CourtDocumentAnalysis,
            responder=_respond,
            max_attempts=max_attempts,
        )
    except (LLMNetworkError, LLMTimeoutError, ConnectionError) as e:
        logger.warning("文书分析 LLM 不可用，将降级为关键词+正则路径: %s", e)
        return DocumentAnalysisOutcome(
            analysis=None,
            model=captured["model"],
            backend=captured["backend"],
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"llm_unavailable: {type(e).__name__}",
        )
    except StructuredValidationError as e:
        logger.warning("文书分析输出重试后仍无法解析，将降级为关键词+正则路径: %s", e)
        return DocumentAnalysisOutcome(
            analysis=None,
            model=captured["model"],
            backend=captured["backend"],
            latency_ms=int((time.monotonic() - started) * 1000),
            error="unparseable_output",
        )
    except Exception as e:
        logger.warning("文书分析失败，将降级为关键词+正则路径: %s", e)
        return DocumentAnalysisOutcome(
            analysis=None,
            model=captured["model"],
            backend=captured["backend"],
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"unexpected: {type(e).__name__}",
        )

    logger.info(
        "文书结构化分析完成",
        extra={
            "action": "analyze_document",
            "document_type": analysis.document_type,
            "case_number": analysis.case_number,
            "court_time": analysis.court_time,
            "confidence": analysis.confidence,
            "model": captured["model"],
            "latency_ms": int((time.monotonic() - started) * 1000),
        },
    )
    return DocumentAnalysisOutcome(
        analysis=analysis,
        model=captured["model"],
        backend=captured["backend"],
        latency_ms=int((time.monotonic() - started) * 1000),
    )
