"""邮件 → 在办合同 的自动关联匹配（一期：只出候选，不写库）。

## 为什么是打分而不是「匹配/不匹配」

真实数据里只靠金额必然错：108 个在办合同有相当一部分 ``fixed_amount`` 为空
或重复（30000 出现多次）。只靠金额匹配等于随机关联，写进财务数据比不写更糟。
所以这里做成**多信号加权打分 + 阈值**，只有 100% 命中的强信号才判为
「确定匹配」，其余一律交给人工。

## 匹配信号分层

强信号（能独立定位，命中即满分）：
- 案号：邮件正文/主题里出现 ``（20XX）粤0604民初123号`` 与案件案号完全一致  # privacy-allow 格式示意
- 合同全名：邮件正文包含合同名称全文

中信号（需组合才有意义）：
- 付款人 / 当事人姓名
- 金额（比的是**应收余额**，不是合同总额）

弱信号（仅加分，不足以单独成立）：
- 款项性质关键词（到账 / 尾款 / 律师费 / 开票）

## 金额口径：比应收余额而不是合同总额

这是本模块最关键的设计。合同总额 30000 已经收了两笔共 28000，这时来一笔
2000 才是对的；只比「合同总额 30000」会把所有 30000 的合同都命中。

- ``FIXED``：应收余额 = ``fixed_amount`` - 已收合计
- ``SEMI_RISK``：应收余额 = ``fixed_amount`` + 标的额×``risk_rate``% - 已收合计
  （前期固定部分与风险尾款**分段**都比一次，任一段对上即算命中）
- ``FULL_RISK``：应收余额 = 标的额×``risk_rate``% - 已收合计
  （无 ``fixed_amount``，且标的额常为空 → 多半只能落人工，这是如实反映）
- ``CUSTOM``：不自动判，标记为需人工
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("apps.message_hub")

# ── 权重与阈值 ────────────────────────────────────────────
# 权重反映信号可靠性。满分 1.0 = 强信号直接命中。
W_CASE_NUMBER = 1.0  # 案号精确命中：唯一可信的「确定匹配」
W_CONTRACT_NAME = 0.85  # 合同全名命中
W_PARTY_NAME = 0.45  # 当事人姓名
W_AMOUNT_EXACT = 0.45  # 金额精确命中应收余额
W_AMOUNT_NEAR = 0.2  # 金额接近（±1%，容忍手续费/multiple payments）
W_KEYWORD = 0.1  # 款项性质关键词

# 判定为「确定匹配」的阈值。只有案号级信号才够得着，其余都要人工确认。
CONFIDENT_THRESHOLD = Decimal("0.99")

# 「弱候选」下限：分数高于它才值得给人看，低于它连提示都不给（避免噪声）。
# 0.15 意味着至少有一条中/弱信号命中（比如金额接近、或当事人命中）。
WEAK_CANDIDATE_THRESHOLD = Decimal("0.15")

# 金额接近的相对容差（如 2400 vs 2400.00 视为相同；2397 也接受）
AMOUNT_NEAR_RATIO = Decimal("0.01")

# 案号：全角/半角括号、「号」字可有可无
CASE_NUMBER_RE = re.compile(
    r"[（(]\s*(\d{4})\s*[）)]\s*([\u4e00-\u9fa5]{1,4}\d{0,6})\s*([\u4e00-\u9fa5]{1,8})\s*(\d{1,8})\s*号?"
)

# 金额：人民币 1,234.56 元 / ￥1234 / 1234.56 元
AMOUNT_RES = (
    re.compile(r"(?:人民币|¥|￥)\s*([\d,]+(?:\.\d{1,2})?)\s*元?"),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*元"),
)

# 款项性质关键词 → 命中的邮件更可能是收款类
KEYWORDS = ("到账", "汇入", "存入", "转入", "收款", "尾款", "律师费", "开票", "付款", "服务费")


@dataclass
class MatchCandidate:
    """一个候选合同 + 它是怎么被选出来的"""

    contract_id: int
    contract_name: str
    score: Decimal
    reasons: list[str] = field(default_factory=list)
    # 该合同算出来的应收余额（用于前端展示「为什么是它」）
    outstanding_amount: Decimal | None = None
    fee_mode: str = ""
    # 明确不可自动匹配时的说明（全风险缺标的额 / 自定义条款）
    caveat: str = ""


def extract_case_numbers(text: str) -> list[str]:
    """从文本里抽取案号，返回标准化后的字符串列表（去重保序）。"""
    seen: list[str] = []
    for m in CASE_NUMBER_RE.finditer(text or ""):
        normalized = f"（{m.group(1)}）{m.group(2)}{m.group(3)}{m.group(4)}号"
        if normalized not in seen:
            seen.append(normalized)
    return seen


def extract_amounts(text: str) -> list[Decimal]:
    """从文本里抽取金额，返回 Decimal 列表（去重、降序）。

    银行通知常见「人民币 2,400 元」「¥2400.00」两种写法；带千分位的要先去掉逗号。
    """
    found: list[Decimal] = []
    for pattern in AMOUNT_RES:
        for m in pattern.finditer(text or ""):
            raw = m.group(1).replace(",", "")
            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError):
                continue
            if value > 0 and value not in found:
                found.append(value)
    return sorted(found, reverse=True)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def compute_outstanding(contract: Any, case_target_amounts: list[Decimal | None]) -> tuple[Decimal | None, str]:
    """算出合同的应收余额，返回 (余额, 说明)。

    说明用于前端/日志解释「这个数是怎么来的」，也是匹配失败时给人工看的依据。
    """
    paid = _to_decimal(getattr(contract, "paid_total", None)) or Decimal("0")
    fee_mode = str(getattr(contract, "fee_mode", "") or "")
    fixed = _to_decimal(getattr(contract, "fixed_amount", None))
    rate = _to_decimal(getattr(contract, "risk_rate", None))

    if fee_mode == "CUSTOM":
        return None, "自定义收费条款，需人工核对"

    if fee_mode == "FIXED":
        if fixed is None:
            return None, "合同未填固定律师费"
        return fixed - paid, f"固定收费 {fixed} - 已收 {paid}"

    # 风险类：标的额取该合同关联案件的最大值（同一合同可能挂多个案件）
    targets = [t for t in case_target_amounts if t is not None]
    target = max(targets) if targets else None

    if fee_mode in ("SEMI_RISK", "FULL_RISK", "risk"):
        if rate is None:
            return None, "风险比例未填，需人工核对"
        if target is None:
            return None, "案件标的额未填，无法推算风险收费"
        risk_part = target * rate / Decimal("100")
        if fee_mode == "FULL_RISK":
            return risk_part - paid, f"标的额 {target} × {rate}% = {risk_part} - 已收 {paid}"
        # 半风险：前期固定 + 风险尾款
        if fixed is None:
            return None, "半风险合同未填前期律师费，需人工核对"
        return fixed + risk_part - paid, f"前期 {fixed} + 标的额 {target} × {rate}% = {risk_part} - 已收 {paid}"

    return None, f"未知收费模式 {fee_mode!r}，需人工核对"


def score_contract(
    *,
    contract: Any,
    mail_text: str,
    mail_amounts: list[Decimal],
    mail_case_numbers: list[str],
    contract_case_numbers: list[str],
    case_target_amounts: list[Decimal | None],
    party_names: list[str],
) -> MatchCandidate:
    """给单个合同打分。纯函数，不碰数据库。"""
    score = Decimal("0")
    reasons: list[str] = []

    contract_name = str(getattr(contract, "name", "") or "")
    fee_mode = str(getattr(contract, "fee_mode", "") or "")

    # 1) 案号命中：最高优先级，命中即可定案
    hit_numbers = [n for n in mail_case_numbers if n in contract_case_numbers]
    if hit_numbers:
        score += Decimal(str(W_CASE_NUMBER))
        reasons.append(f"案号命中 {hit_numbers[0]}")

    # 2) 合同全名命中（名称太短时容易误伤，要求至少 6 字）
    if len(contract_name) >= 6 and contract_name in mail_text:
        score += Decimal(str(W_CONTRACT_NAME))
        reasons.append(f"合同名称命中「{contract_name[:16]}」")

    # 3) 当事人姓名命中
    hit_parties = [p for p in party_names if p and p in mail_text]
    if hit_parties:
        score += Decimal(str(W_PARTY_NAME))
        reasons.append(f"当事人命中 {hit_parties[0]}")

    # 4) 金额 vs 应收余额
    outstanding, explain = compute_outstanding(contract, case_target_amounts)
    if outstanding is not None and mail_amounts:
        for amt in mail_amounts:
            if amt == outstanding:
                score += Decimal(str(W_AMOUNT_EXACT))
                reasons.append(f"金额 {amt} = 应收余额（{explain}）")
                break
            if outstanding > 0 and abs(amt - outstanding) <= outstanding * AMOUNT_NEAR_RATIO:
                score += Decimal(str(W_AMOUNT_NEAR))
                reasons.append(f"金额 {amt} ≈ 应收余额 {outstanding}")
                break

    # 5) 款项性质关键词（邮件层面命中，对每个候选都加分，不区分度，但能整体抬高可信度）
    if any(k in mail_text for k in KEYWORDS) and "金额" in "".join(reasons):
        score += Decimal(str(W_KEYWORD))
        reasons.append("含款项性质关键词")

    return MatchCandidate(
        contract_id=int(getattr(contract, "id", 0) or 0),
        contract_name=contract_name,
        score=min(score, Decimal("1")),
        reasons=reasons,
        outstanding_amount=outstanding,
        fee_mode=fee_mode,
        caveat="" if outstanding is not None else explain,
    )


def rank_candidates(candidates: list[MatchCandidate], *, limit: int = 5) -> list[MatchCandidate]:
    """排序并截断候选列表。

    排序规则：分数降序；同分时**应收余额与邮件金额更接近的排前面**——两个合同
    同分时，「差 3 块」的那个比「差 3 万」的那个更值得人先看。
    """
    ranked = [c for c in candidates if c.score >= WEAK_CANDIDATE_THRESHOLD]
    ranked.sort(key=lambda c: (-c.score, c.contract_id))
    return ranked[:limit]


def build_mail_text(*, subject: str, body_text: str, body_html: str) -> str:
    """把邮件的主题 + 纯文本 + HTML（剥标签）拼成一段可匹配的文本。"""
    html_text = re.sub(r"<[^>]+>", " ", body_html or "")
    html_text = re.sub(r"&nbsp;?", " ", html_text)
    return "\n".join(part for part in (subject or "", body_text or "", html_text) if part).strip()


def suggest_contracts_for_message(*, subject: str, body_text: str, body_html: str) -> dict[str, Any]:
    """给一条邮件算出候选合同列表。

    只读，不写任何财务数据（一期约定：自动写入留到二期）。
    返回结构直接对应 ``ContractMatchOut``。
    """
    from django.db.models import Sum

    from apps.contracts.models import Contract
    from apps.contracts.models.contract import ContractStatus

    mail_text = build_mail_text(subject=subject, body_text=body_text, body_html=body_html)
    mail_amounts = extract_amounts(mail_text)
    mail_case_numbers = extract_case_numbers(mail_text)

    candidates: list[MatchCandidate] = []
    contracts = (
        Contract.objects.filter(status=ContractStatus.ACTIVE)
        .prefetch_related("cases", "contract_parties__client", "payments")
        .only("id", "name", "fee_mode", "fixed_amount", "risk_rate")
    )
    for contract in contracts:
        # 已收合计：应收余额的减项，必须算进来，否则尾款会被判成「对不上」
        paid = contract.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        contract.paid_total = paid  # 供 compute_outstanding 读取

        cases = list(contract.cases.all())
        contract_case_numbers = [str(getattr(c, "case_number", "") or "") for c in cases]
        case_target_amounts = [_to_decimal(getattr(c, "target_amount", None)) for c in cases]
        party_names = [
            str(getattr(cp.client, "name", "") or "") for cp in contract.contract_parties.all() if cp.client_id
        ]

        candidate = score_contract(
            contract=contract,
            mail_text=mail_text,
            mail_amounts=mail_amounts,
            mail_case_numbers=mail_case_numbers,
            contract_case_numbers=[n for n in contract_case_numbers if n],
            case_target_amounts=case_target_amounts,
            party_names=[n for n in party_names if n],
        )
        if candidate.score > 0:
            candidates.append(candidate)

    ranked = rank_candidates(candidates)
    confident = any(c.score >= CONFIDENT_THRESHOLD for c in ranked)
    if confident:
        status = "confident"
    elif ranked:
        status = "suggested"
    else:
        status = "none"

    return {
        "status": status,
        "candidates": [
            {
                "contract_id": c.contract_id,
                "contract_name": c.contract_name,
                "score": float(c.score),
                "reasons": c.reasons,
                "outstanding_amount": str(c.outstanding_amount) if c.outstanding_amount is not None else None,
                "fee_mode": c.fee_mode,
                "caveat": c.caveat,
            }
            for c in ranked
        ],
        "extracted_amounts": [str(a) for a in mail_amounts],
        "extracted_case_numbers": mail_case_numbers,
    }
