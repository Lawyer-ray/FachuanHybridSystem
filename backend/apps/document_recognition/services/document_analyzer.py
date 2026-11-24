"""法院文书单次结构化分析（分类 + 关键信息提取合一）。

旧实现为「分类、提取两次 LLM 调用」；本模块合并为一次结构化调用：
prompt 要求模型直接返回文书类型 + 案号 + 关键时间的 JSON，经
``apps.core.llm.structured_output`` 做 pydantic 严格校验，校验失败带错误
反馈自动重试。

LLM 不指定 backend/model，由统一 LLM 层按「默认后端 + AI 平台默认模型」
路由（律所 kimi 平台）。LLM 不可用或重试后仍无法解析时返回
``analysis=None`` 的结果（软失败），由 recognition_service 降级到
关键词 + 正则路径。

**职责边界（LLM 只做语义，不做日期算术）**：LLM 只负责「这份文书里明文的日期
有哪些、每个属于哪类事件、这条日期/期限的起算锚指向谁」；一切「起算日 + N 日」
的推算归确定性层（``date_candidate_service``）。两层口径必须唯一——LLM 自己按
落款日算一遍、确定性层再按送达日算一遍，同一句期限就会产出两条互相矛盾的候选。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from apps.core.llm.exceptions import LLMBackendUnavailableError, LLMNetworkError, LLMTimeoutError
from apps.core.llm.structured_output import StructuredValidationError, json_schema_instructions, retry_structured

logger = logging.getLogger("apps.document_recognition")

# 与旧实现一致：截断超长文本，避免超出模型上下文限制
MAX_ANALYSIS_CHARS = 4000

# LLM 分析整体预算（秒）：网关默认 timeout 120s，这里收紧到单任务 90s
ANALYSIS_TIMEOUT_SECONDS = 90.0

# 全后端不可用熔断（秒）：LLM_ALL_BACKENDS_UNAVAILABLE 意味着逐后端×逐 Key 已
# 轮询一整圈（律所网关挂掉时单次要烧数分钟）。熔断窗口内后续文书直接走降级
# 路径不再打 LLM，窗口过期后自动放行重试。进程内状态，各 worker 独立熔断。
LLM_BLACKOUT_SECONDS = float(os.environ.get("DOCUMENT_LLM_BLACKOUT_SECONDS", "300") or "300")
#: 熔断截止时刻（monotonic 秒）；读写均经函数内 ``global``，模块级赋值只是初始化，
#: CodeQL 误报「未使用」，不可删除。
_blackout_until = 0.0


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
    # 这条日期/期限的起算锚属于谁（LLM 只负责标注，归属判定与推算归确定性层）：
    # self=本份文书自身的日期或期限 | effective=以「判决/裁定发生法律效力」为起算
    # | future_document=锚点指向尚未产生的文书（如「裁判文书送达之日」）
    # | other_document=锚点指向另一份具名文书（如「收到《缴费通知书》之日起」） | none=无法判断
    anchor_hint: Literal["self", "effective", "future_document", "other_document", "none"] = "self"


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


def _delivery_hint(dt: datetime | None) -> str:
    """生成注入提示词的「送达日背景」一句话（纯函数，无副作用）。

    只做两件事：把送达日格式化成 YYYY-MM-DD 供模型**判断**某条相对期限是否已经
    可以确定；同时明确**禁止**模型拿它做日期运算。日期算术统一归确定性层
    （``date_candidate_service._apply_relative_deadline_rules``）——否则同一句期限
    会出现「LLM 按落款日算一条 + 确定性层按送达日算一条」两条互相矛盾的候选。

    日期取值口径与确定性层保持一致（都取 ``dt.date()``），避免提示词里的日期和
    实际推算锚点差一天。

    Args:
        dt: 文书送达/收到时间（法院短信 ``CourtSMS.received_at``）；None 表示未知。

    Returns:
        可直接拼进提示词的中文说明（含句末括号约束）。
    """
    if dt is None:
        return "（未提供送达日，禁止推算日期）"
    return f"本份文书送达日：{dt.date().isoformat()}（仅用于判断某条期限是否已可确定，禁止用它计算日期）"


ANALYSIS_PROMPT = """你是法院文书分析助手。请分析以下法院文书，一次性完成五项任务：
1. 判断文书类型：summons=传票（含开庭时间、出庭通知），execution=执行裁定书（含财产保全、查封、冻结、执行裁定），other=其他文书；
2. 提取案号：格式为（年份）法院代码+案件类型字号+序号+号，如（2024）粤0604民初41257号，必须含案件类型字号（民初/民终/刑初/执/执保等）并以"号"字结尾；无法确定填 null；
3. 提取最关键的一个时间：传票取开庭时间，执行裁定书取财产保全到期时间；格式 YYYY-MM-DD HH:MM 或 YYYY-MM-DD；无法确定填 null；
4. 提取文书中**所有**关键日期事件，每个一条填入 key_events：开庭时间、举证截止日、上诉期届满日、财产保全到期日、缴费期限、补正/材料提交期限、诉讼时效届满日等；同一文书有多个日期都要列出（如多次开庭、举证截止+开庭日期并存）；每条给出 event_type、原文片段（context，不超过 60 字）、置信度、起算锚归属（anchor_hint）；日期格式 YYYY-MM-DD HH:MM 或 YYYY-MM-DD（只有日期无时间时可省略时间）；
   4.1 **只输出原文中明文的绝对日期，且必须带年份；不做任何日期推算**：原文是「收到本通知次日起两日内交纳」「自收到本决定书之日起7日内付款」这类相对表述时，不要替律师算出具体日期，也不要拿落款日、打印日、出具日、送达日或任何其它日期去加天数、减天数、补年份——期限怎么起算、怎么推算由系统另行确定；
   4.2 **日期必须带年份**：原文只写「3月26日」「8月2日」这类无年份表述时，即使能从上下文猜出年份也**不要补年份、不要生成该条**（猜错一年会让律师跟进错期限），宁可省略；
   4.3 **不要虚构日期**：原文中找不到的日期一律不要出现；切勿把落款日期本身直接当作期限事件的日期（落款日不是「期限届满日」）；
   4.4 本文书若只是通用规则说明（须知、告知书、风险提示、举证通则等），且没有针对本案的具体日期，返回空数组 []；
   4.5 每条 key_events 必须给出 anchor_hint，标注这条日期/期限的起算锚属于谁（你只描述原文指向谁，不做归属判定、不做任何换算）：self=本份文书自身的日期或期限（开庭日、举证截止日、本份文书载明的期限等）；effective=以「判决/裁定发生法律效力」为起算（如「本判决生效之日起十日内付款」）；future_document=锚点指向尚未产生的文书（如「裁判文书送达之日」）；other_document=锚点指向另一份具名文书（如「收到《缴费通知书》之日起」）；none=无法判断；
   4.6 送达日背景：{delivery_date_hint}。它只用于判断某条期限是否已经可以确定，**禁止**拿它（或落款日、打印日）做加减来推算日期。
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
    delivery_date: datetime | None = None,
) -> DocumentAnalysisOutcome:
    """单次结构化 LLM 调用完成分类 + 提取。

    Args:
        text: 文书全文（超长自动截断）
        llm_service: 可注入的 LLM 服务（默认 ServiceLocator）
        max_attempts: 输出解析失败时带反馈重试的总次数
        model: 指定模型（None 走统一 LLM 层默认模型）
        delivery_date: 文书送达/收到时间（法院短信 ``CourtSMS.received_at``）。
            仅作为提示词背景注入（见 ``_delivery_hint``），让模型知道某些相对期限
            已经可以确定；**不**在此处做任何日期推算，也**不**用它过滤 key_events
            ——起算锚归属与届满日推算归确定性层 ``date_candidate_service``。
            默认 None，兼容既有调用方（此时提示词明确告知「未提供送达日」）。

    Returns:
        DocumentAnalysisOutcome；永不抛异常——LLM 不可用/超时/解析失败都
        折叠为 ``analysis=None``（软失败），调用方据此走降级路径。
    """
    if not text or not text.strip():
        return DocumentAnalysisOutcome(analysis=None, error="empty_text")

    global _blackout_until
    if time.monotonic() < _blackout_until:
        remaining = int(_blackout_until - time.monotonic())
        logger.info("LLM 全后端熔断窗口内，跳过 LLM 分析直接降级（剩余 %ss）", remaining)
        return DocumentAnalysisOutcome(analysis=None, error="llm_blackout")

    truncated = text[:MAX_ANALYSIS_CHARS]
    prompt = ANALYSIS_PROMPT.format(
        schema_instructions=json_schema_instructions(CourtDocumentAnalysis),
        text=truncated,
        delivery_date_hint=_delivery_hint(delivery_date),
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
    except LLMBackendUnavailableError as e:
        # 所有后端×Key 已轮询一整圈仍不可用（如律所网关整机挂掉）：进入熔断窗口，
        # 窗口内后续文书不再重复烧整轮轮询，直接降级；窗口过期自动恢复尝试
        _blackout_until = time.monotonic() + LLM_BLACKOUT_SECONDS
        logger.warning(
            "文书分析 LLM 全部后端不可用，降级为关键词+正则路径，且未来 %ss 内跳过 LLM 直连: %s",
            int(LLM_BLACKOUT_SECONDS),
            e,
        )
        return DocumentAnalysisOutcome(
            analysis=None,
            model=captured["model"],
            backend=captured["backend"],
            latency_ms=int((time.monotonic() - started) * 1000),
            error="llm_all_backends_unavailable",
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
