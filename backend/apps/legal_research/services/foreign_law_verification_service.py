"""域外法核验留痕的写入服务。

## 为什么写入必须 fail-open

留痕是**旁路**：核验结论本身已经算完并要返回给律师，写台账失败不能让律师拿不到
结论（那等于为了记账把业务干掉）。所以本模块 `record_verification` 内部吞异常、
记 `logger.exception`，返回 `None`。

这与 `services/task/event_service.py` 对任务事件的处理是同一条口径。

## 为什么不存条文全文

只存 `section_text_sha256` + 长度。要复现时用条号回该平台取——存全文会让这张表  # privacy-allow 公开学术平台，非客户机构
变成境外法典的内容库（体积与合规都没必要）。

## 为什么 `judge_config` 存的是原始 env 字符串

「为什么这次没判 / 为什么弃权」只能靠开关状态解释。把 env **原样**记下来，而不是在
这里重新解析一遍：重新解析会与插件的默认值/解析规则漂移，届时记录的解释力反而更差。
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from apps.legal_research.models import ForeignLawVerification

logger = logging.getLogger(__name__)

#: 与判定相关的开关，原样记录（不在这里解析默认值，避免与插件漂移）。
_JUDGE_ENV_KEYS = (
    "FACHUAN_BARLC_JURY",
    "FACHUAN_BARLC_JURY_SIZE",
    "FACHUAN_BARLC_JURY_MODELS",
    "FACHUAN_BARLC_JURY_TIMEOUT",
    "FACHUAN_BARLC_JURY_DEADLINE",
)

#: 落库的列表/字典字段上限（防止一次异常响应把表撑大）。
_MAX_LIST_ITEMS = 20


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _trim_list(value: Any) -> list[Any]:
    """截断列表到 `_MAX_LIST_ITEMS`（留痕要复现判据，不需要无限长）。"""
    if not isinstance(value, list):
        return []
    return value[:_MAX_LIST_ITEMS]


def record_verification(
    *,
    lawyer_id: int | None,
    payload: dict[str, Any],
    result: dict[str, Any],
    total_ms: int = 0,
) -> ForeignLawVerification | None:
    """把一次核验写成一行台账；任何异常都吞掉并记日志。

    Args:
        lawyer_id: 核验人（HTTP 入口能拿到；MCP 直连路径拿不到，传 None）。
        payload: 请求入参（`law_name` / `section_number` / `claim` / `country_code` / ...）。
        result: 工具返回的完整字典（含 verdict / elements / votes / version_warnings）。
        total_ms: 本次耗时（毫秒）。

    Returns:
        写入的行；失败时返回 `None`（不影响调用方返回结论）。
    """
    try:
        section_text = str(result.get("section_text") or "")
        row = ForeignLawVerification(
            created_by_id=lawyer_id,
            law_name=str(payload.get("law_name") or "")[:255],
            section_number=str(payload.get("section_number") or "")[:32],
            claim=str(payload.get("claim") or ""),
            country_code=str(payload.get("country_code") or "")[:32],
            as_of_date=str(payload.get("as_of_date") or "")[:10],
            ok=bool(result.get("ok")),
            # `ok=False` 时 reason 是失败码（credential_missing / verify_failed / ...），
            # 而 verdict 无意义——两者必须分开，否则「没配账号」会被算成「不存在该引用」。
            failure_code="" if result.get("ok") else str(result.get("reason") or "")[:32],
            verdict=str(result.get("verdict") or "")[:16] if result.get("ok") else "",
            law_title=str(result.get("law_title") or "")[:512],
            matched_by=str(result.get("matched_by") or "")[:16],
            reason=str(result.get("reason") or ""),
            adjudicated=bool(result.get("adjudicated")),
            unconfirmed=bool(result.get("unconfirmed")),
            needs_human=bool(result.get("needs_human")),
            review_reasons=_trim_list(result.get("review_reasons")),
            agreement=result.get("agreement"),
            elements=_trim_list(result.get("elements")),
            votes=_trim_list(result.get("votes")),
            cached=bool(result.get("cached")),
            jury_tokens=int(result.get("jury_tokens") or 0),
            judge_config={key: os.environ.get(key, "") for key in _JUDGE_ENV_KEYS},
            source_url=str(result.get("source_url") or "")[:512],
            effective_date=str(result.get("effective_date") or "")[:32],
            revise_date=str(result.get("revise_date") or "")[:32],
            version_warnings=_trim_list(result.get("version_warnings")),
            section_text_sha256=_sha256(section_text) if section_text else "",
            section_text_length=len(section_text),
            total_ms=max(0, int(total_ms)),
            contract_id=payload.get("contract_id"),
            citation_anchor=str(payload.get("citation_anchor") or "")[:128],
        )
        row.save()
        return row
    except Exception:  # 留痕是旁路：写失败不能让律师拿不到结论
        logger.exception(
            "域外法核验留痕写入失败（不影响核验结果）law=%s section=%s",
            payload.get("law_name"),
            payload.get("section_number"),
        )
        return None


__all__ = ["record_verification"]
