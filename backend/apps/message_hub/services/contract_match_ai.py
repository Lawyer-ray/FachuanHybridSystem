"""到账通知 → 在办项目：**AI 兜底**匹配。

## 为什么需要兜底

规则匹配（``contract_match_v2``）靠三个硬信号：案号、付款人命中委托人、
代付方命中委托人。真实的银行到账通知千变万化——银行改了短信模板、律师把
付款方写成了简称、一句话里塞了三家公司——任何一种都会让硬信号全部落空，
于是整笔钱只能靠「金额恰好撞上某个项目的应收余额」被列出来，在待认领页
显示成「仅金额吻合」，让人翻十几个无关项目去找真正的那一个。

规则改得再细也追不上话术的穷举。所以这里加一层**兜底**：规则没给出确定
答案时，把「邮件原文 + 候选项目清单」交给 LLM，让它读语义、给判断。

## 触发条件（严格）

**只在没有任何 ``exact`` 候选时才调用。** 规则已经给出了实名证据的确定性
答案时，不应该再花一次模型调用去"复核"——那既慢又可能把正确答案改坏。
见 ``suggest_contracts_for_transfer`` 里的调用点。

## 安全边界（不可妥协）

1. **AI 只能从给定候选里选**，不能凭空造合同 id。返回的 id 不在候选集合
   里的一律丢弃——这样即便模型幻觉出 ``999``，也不会让前端显示一个不存在的项目。
2. **AI 的输出永远只是建议**，``kind`` 恒为 ``ai_suggested``，排在所有规则
   候选之后。最终归属仍然要人在待认领页点确认。
3. **失败静默降级**：模型不可用/超时/返回非 JSON，就当地没有兜底，绝不因为
   兜底把主流程弄挂。到账认领是账务流程，不能依赖一个外部服务可用。
4. **不写任何数据**。纯只读，与规则匹配器一致。

## 为什么不复用 ``contract_match`` 的权重

那套权重是为「案号/付款人」这类**确定性**信号设计的。AI 给的是**概率性**
判断，混进同一套分数机制会让人分不清「系统确定」和「模型觉得像」。所以
AI 候选单独一种 kind、单独的分数口径。
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from apps.core.services.wiring import get_llm_service

if TYPE_CHECKING:
    from apps.message_hub.services.transfer_notice import TransferNotice

logger = logging.getLogger("apps.message_hub")

#: AI 候选的 kind。刻意与规则的三类（exact/partial/amount_only）区分开，
#: 前端据此显示不同的提示语，人工看快照时也能一眼分清来源。
KIND_AI_SUGGESTED = "ai_suggested"

#: AI 候选的展示分数。低于 amount_only 的 0.45：模型的判断再合理，
#: 也不应该盖过「金额确实等于应收余额」这条客观事实。
SCORE_AI = 0.4

#: 交给模型的候选上限。全量 100+ 个项目既超上下文也没必要——
#: 金额层已经排除掉绝大部分，这里再截一道。
MAX_PROMPT_CANDIDATES = 25

MAX_TOKENS = 500

#: 一次兜底最多接受几个 AI 结果
MAX_AI_RESULTS = 3

_SYSTEM_PROMPT = (
    "你是律所财务到账认领助手。银行到账通知里常有客户公司简称、律师个人代收、"
    "括号备注等线索。你要判断这笔钱最可能属于下面清单里的哪个项目。"
    "只输出 JSON，不要任何解释性文字。"
    '格式：{"matches": [{"contract_id": 项目编号, "confidence": 0到1的数字, "reason": "20字以内理由"}]}'
    '。若确实无法判断，输出 {"matches": []}。'
    "只能从给定清单里选 contract_id，不得编造。"
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _build_prompt(*, notice: TransferNotice, mail_text: str, candidates: list[dict[str, Any]]) -> str:
    """组装提示词：邮件原文 + 候选清单。"""
    lines = [
        "【银行到账通知原文】",
        (mail_text or "").strip()[:1500],
        "",
        "【系统已解析出的字段】",
        f"金额：{notice.amount}",
        f"付款人：{notice.payer_name or '（未识别）'}",
        f"付款方说明（括号内）：{notice.on_behalf_of or '（未识别）'}",
    ]
    if notice.payer_is_person:
        lines.append("提示：付款人是个人姓名，律所场景下常是承办律师代客户转付，不一定是委托人本人。")
    lines.extend(["", "【可选项目清单】"])
    for item in candidates:
        outstanding = item.get("outstanding_amount")
        amount_hint = f"，应收余额 {outstanding}" if outstanding else ""
        lines.append(f"- contract_id={item['contract_id']}：{item['contract_name']}{amount_hint}")
    lines.extend(
        [
            "",
            "请判断这笔到账最可能对应哪个（或哪几个）项目，按可能性从高到低输出。",
            "重点看：括号里的付款方说明、公司简称与项目名称的对应关系、金额是否吻合。",
        ]
    )
    return "\n".join(lines)


def _parse_matches(raw: str) -> list[dict[str, Any]]:
    """从模型输出里抠出 matches 数组。任何解析问题都返回空列表（静默降级）。"""
    text = (raw or "").strip()
    if not text:
        return []
    block = _JSON_BLOCK_RE.search(text)
    if block:
        text = block.group(0)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("AI 兜底返回非 JSON，已忽略: %s", (raw or "")[:200])
        return []
    matches = payload.get("matches") if isinstance(payload, dict) else None
    if not isinstance(matches, list):
        return []
    return [m for m in matches if isinstance(m, dict)]


def _coerce_confidence(value: Any) -> float:
    """置信度归一化到 [0,1]。模型偶尔给 "0.8"、85 或 "high"。"""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    if conf > 1:
        conf = conf / 100 if conf <= 100 else 1.0
    return max(0.0, min(conf, 1.0))


def _default_llm_complete(*, prompt: str, system_prompt: str) -> str:
    """默认 LLM 调用（走 Django admin 里配置的 LLMProvider，按优先级+降级链选择）。

    单独抽成模块级函数是为了让测试能 patch 它，不必真的打网络。
    """
    response = get_llm_service().complete(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.1,
        max_tokens=MAX_TOKENS,
    )
    return str(getattr(response, "content", "") or "")


def suggest_with_ai(
    *,
    notice: TransferNotice,
    mail_text: str,
    candidates: list[dict[str, Any]],
    complete_fn: Any = None,
) -> list[dict[str, Any]]:
    """让 LLM 从候选里挑出这笔到账对应的项目。

    Args:
        notice: 规则解析器的结果（金额/付款人/付款方说明）。
        mail_text: 邮件原文（含主题），交给模型读语义。
        candidates: 规则匹配器算出的候选（含 contract_id/name/outstanding）。
            只在这些里面选，模型编造的 id 会被丢掉。
        complete_fn: 可注入的补全函数（测试用）。缺省走真实 LLMProvider。

    Returns:
        至多 ``MAX_AI_RESULTS`` 个候选字典，结构同 ``Candidate.as_dict()``。
        任何失败路径都返回空列表。
    """
    if not candidates:
        return []

    allowed: dict[int, dict[str, Any]] = {}
    for item in candidates[:MAX_PROMPT_CANDIDATES]:
        try:
            allowed[int(item["contract_id"])] = item
        except (KeyError, TypeError, ValueError):
            continue
    if not allowed:
        return []

    prompt = _build_prompt(notice=notice, mail_text=mail_text, candidates=list(allowed.values()))
    complete = complete_fn or _default_llm_complete
    try:
        raw = complete(prompt=prompt, system_prompt=_SYSTEM_PROMPT)
    except Exception:
        # 兜底失败绝不向上抛：到账认领不能因为模型不可用而中断
        logger.warning("AI 兜底调用失败，按无兜底处理", exc_info=True)
        return []

    results: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in _parse_matches(raw):
        raw_id = match.get("contract_id")
        if raw_id is None:
            continue
        try:
            contract_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        # 防幻觉：只接受清单里真实存在的项目
        if contract_id not in allowed or contract_id in seen:
            continue
        confidence = _coerce_confidence(match.get("confidence"))
        if confidence <= 0:
            continue
        seen.add(contract_id)
        source = allowed[contract_id]
        reason = str(match.get("reason") or "").strip()[:60]
        results.append(
            {
                "contract_id": contract_id,
                "contract_name": source.get("contract_name", ""),
                "kind": KIND_AI_SUGGESTED,
                "score": SCORE_AI * confidence,
                "reasons": [f"AI 判断：{reason}" if reason else "AI 判断（未给出理由）"],
                "outstanding_amount": source.get("outstanding_amount"),
                "fee_mode": source.get("fee_mode", ""),
                "caveat": "AI 兜底建议，未经规则证据确认，请人工核对",
                "confidence": confidence,
            }
        )

    results.sort(key=lambda r: -float(r["confidence"]))
    if results:
        logger.info("AI 兜底给出 %d 个建议：%s", len(results), [r["contract_id"] for r in results])
    return results[:MAX_AI_RESULTS]
