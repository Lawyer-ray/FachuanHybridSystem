"""调用 LLM 从合同正文抽取结构化字段。

职责边界：**只负责「文档文本 → ContractExtraction」**，不做表单回填、
不碰数据库写入。后期的归一化在 :mod:`normalize`，权限与文件落盘在 Admin 视图。

失败策略（对齐本仓库 ``ai_classify_service`` 等既有 LLM 辅助链路）：
任何异常都抛 :class:`ContractExtractionError`，由调用方转成页面上可读的
提示——**绝不静默返回空草稿**，否则用户会以为「AI 说这份合同没有信息」。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.contracts.services.contract.intake.document_snapshot import DocumentSnapshot
from apps.contracts.services.contract.intake.extract_schema import ContractExtraction, trim_quotes
from apps.core.llm.structured_output import StructuredValidationError, json_schema_instructions, retry_structured

logger = logging.getLogger(__name__)

#: 抽取任务的 temperature：接近 0，保证同一份合同多次分析结果稳定
_TEMPERATURE = 0.0
#: 输出上限：字段不多但含多个当事人/律师，4000 足够且不易被截断
_MAX_TOKENS = 4000
#: 结构化重试次数（首次 + 2 次纠错重试）
_MAX_ATTEMPTS = 3


class ContractExtractionError(Exception):
    """LLM 抽取失败（无可用模型 / 超时 / 输出非法）。"""


_SYSTEM_PROMPT = """\
你是律所合同录入助手。用户会给你一份中文法律服务合同（律师事务所与委托方签订）的全文文本，\
你需要从中读取信息，供系统自动填充合同登记表单。

铁律（违反会导致系统录入错误数据）：
1. **只抄录文档中真实存在的信息**。找不到就留空（空字符串 / 空数组 / false），
   绝对不要用常识、行业惯例或当前日期去推测补全。
2. 当事人名称、证照号、姓名必须**逐字抄录**，不要简写、不要补全全称、不要改错别字。
3. 落款处若是空白的「年　月　日」，`sign_date_text` 必须留空，不要填任何日期。
4. 律师事务所（乙方）**不是合同当事人**：请照实在 `parties` 里列出并标 `is_law_firm=true`，\
   系统会自动剔除。不要漏掉律所，也不要把它写成甲方。
5. 金额请把**原文表述**整段抄进 `amount_text`（如「壹万元整（10000.00）」）。\
   若合同分多个律所分别收费，抄录合计总额并令 `amount_is_total=true`；\
   若是按比例计费（如「回款额的 20%」），照抄比例原文并把 `fee_mode` 设为对应风险模式。
6. `case_type` 只能从上文给定的枚举英文值里选一个，不要自己发明。
7. `confidence` 请如实给出把握度：没把握给低分，比填一个猜测值有用得多。"""


def build_user_prompt(snapshot: DocumentSnapshot, *, our_law_firm: str = "") -> str:
    """拼装用户消息：我方律所身份 + 文件名 + 正文 + 输出格式约束。

    **我方律所是决定金额归属的关键上下文**：多律所共同承办的合同常写
    「甲乙双方各付壹万、共贰万」，而我方合同金额只是自己那一份。不给这个
    身份，模型只能取合计（实测就把 1 万报成了 2 万）。
    """
    firm_line = (
        f"我方（录入人所属）律所：{our_law_firm}\n"
        "当合同由多家律所共同承办、费用分别约定时，请把**我方那一份**填进 `amount_text`，"
        "并把 `amount_is_total` 设为 false；只有合同总价确实就是全案总额时才设 true。\n\n"
        if our_law_firm
        else ""
    )
    return (
        f"文件名：{snapshot.filename}\n"
        f"（文档共 {snapshot.paragraph_count} 段、{snapshot.table_count} 个表格）\n\n"
        f"{firm_line}"
        "===== 合同正文开始 =====\n"
        f"{snapshot.text}\n"
        "===== 合同正文结束 =====\n\n"
        "请按要求抽取字段。\n"
        f"{json_schema_instructions(ContractExtraction)}"
    )


def _call_llm(*, prompt: str, model_id: str) -> str:
    """单次 LLM 调用，返回原始文本内容。"""
    from apps.core.services.wiring import get_llm_service

    try:
        response = get_llm_service().complete(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            # 只传 model：LLMClient 会按模型名自动路由到对应平台，
            # 前端因此只需让用户选模型，无需再选平台
            model=model_id or None,
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
            caller="contracts.intake.extract",
        )
    except Exception as exc:
        # 底层异常可能带 HTTP 请求体、模型响应、鉴权头等敏感内容，
        # 只进服务端日志（logger.exception），用户文案给固定提示。
        # 若把 {exc} 拼进文案，它会沿 ContractIntakeError → admin JsonResponse
        # 一路透传到前端（CodeQL py/stack-trace-exposure）。
        logger.exception("合同抽取 LLM 调用失败")
        raise ContractExtractionError("调用大模型失败，请稍后重试或换一个模型") from exc

    content = str(getattr(response, "content", "") or "").strip()
    if not content:
        raise ContractExtractionError("大模型返回了空内容，请稍后重试或换一个模型")
    return content


def extract_contract(
    *,
    snapshot: DocumentSnapshot,
    model_id: str = "",
    our_law_firm: str = "",
    budget_seconds: float | None = None,
) -> ContractExtraction:
    """从文档快照抽取合同字段。

    Args:
        snapshot: 已提取文本的文档快照。
        model_id: 用户选择的模型名；空字符串表示用平台默认模型。
        our_law_firm: 当前登录律师所属律所名。多律所分收的合同里，
            它直接决定「我方金额」取哪一个，必须传给模型。
        budget_seconds: 墙钟预算。超时抛 :class:`ContractExtractionError`。
            LLM 后端自身的重试链可能远超单次超时，这里再兜一层总时限，
            避免把 admin 请求拖到浏览器超时。

    Returns:
        通过 Pydantic 校验的抽取结果。

    Raises:
        ContractExtractionError: 调用失败、超时或输出无法解析成合法结构。
    """
    prompt = build_user_prompt(snapshot, our_law_firm=our_law_firm)
    logger.info(
        "开始合同抽取: file=%s model=%s chars=%d truncated=%s",
        snapshot.filename,
        model_id or "(默认)",
        snapshot.char_count,
        snapshot.truncated,
    )

    def responder(last_error: StructuredValidationError | None) -> str:
        if last_error is None:
            return _call_llm(prompt=prompt, model_id=model_id)
        # 把校验错误回喂，要求模型只修正格式
        feedback = f"{prompt}\n\n上一次输出不符合要求：{last_error.feedback_message}\n请只输出修正后的 JSON，不要解释。"
        return _call_llm(prompt=feedback, model_id=model_id)

    try:
        extraction = retry_structured(
            model_cls=ContractExtraction,
            responder=responder,
            max_attempts=_MAX_ATTEMPTS,
        )
    except StructuredValidationError as exc:
        logger.warning("合同抽取输出无法解析: %s", exc)
        raise ContractExtractionError(
            "大模型输出无法解析为结构化数据（已自动重试 3 次）。建议换一个能力更强的模型重试"
        ) from exc

    extraction = trim_quotes(extraction)
    logger.info(
        "合同抽取完成: parties=%d lawyers=%d case_type=%s",
        len(extraction.parties),
        len(extraction.lawyers),
        extraction.case_type or "(未判定)",
    )
    return extraction


def available_models() -> list[dict[str, Any]]:
    """列出可供用户选择的模型（供前端下拉框）。

    直接复用 ``LLMProviderService`` 的平台配置缓存，因此新建合同页与
    ``/admin/core/llmprovider/`` 看到的是同一份数据。
    """
    from apps.core.services.llm_provider_service import LLMProviderService

    options: list[dict[str, Any]] = []
    default_model = ""
    try:
        providers = LLMProviderService.get_providers()
    except Exception:
        logger.warning("读取 LLM 平台配置失败，模型下拉框将为空", exc_info=True)
        return options

    for provider in providers:
        if not provider.enabled:
            continue
        models = provider.all_models
        if not models:
            continue
        if not default_model and provider.default_model:
            default_model = provider.default_model
        for model in models:
            options.append(
                {
                    "value": model,
                    "label": f"{provider.name} · {model}",
                    "provider": provider.name,
                    "is_default": model == provider.default_model,
                }
            )

    # 同一模型可能被多个平台提供：按 value 去重，保留优先级更高的平台（providers 已排序）
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for option in options:
        if option["value"] in seen:
            continue
        seen.add(option["value"])
        unique.append(option)

    return unique


def default_model_of() -> str:
    """默认模型名（用于前端预选）。找不到返回空串，后端会回落到平台默认。"""
    from apps.core.services.llm_provider_service import LLMProviderService

    try:
        for provider in LLMProviderService.get_providers():
            if provider.enabled and provider.default_model:
                return provider.default_model
    except Exception:
        logger.warning("读取默认模型失败", exc_info=True)
    return ""
