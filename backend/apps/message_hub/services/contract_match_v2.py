"""到账通知 → 在办项目 的候选匹配（v2）。

## v1 的四个致命缺陷（真实数据实测，见设计文档 §2）

1. **案号信号恒为 0**：v1 读 ``case.case_number``，但工单模型没有这个属性
   （案号实际在 ``case.case_numbers[].number``）。于是唯一能判"确定匹配"的
   信号一条都没生效。
2. **已收满的项目仍进候选**：v1 只按 ``status=ACTIVE`` 过滤。实测 446 号
   （某税务案）已收清 50000 且全额开票，客户又打来 10000，v1 仍把它列进
   候选，且因余额为 0 而金额永远不匹配，只挂着一个弱信号。
3. **仅金额撞车能压过实名证据**：v1 里 ``amount_only``（0.55）把
   ``当事人命中``（0.45）压在下面——#547 就是这样把无关的 270 号合同排到第一。
4. **「代 XXX 付」被当普通子串**：既不区分"代付方 ≠ 付款人"，也不区分当事人身份。

## v2 的分层

第一层 **资格过滤**（``intake_eligibility.eligible_contract_qs``）：已归档/未签约/
已收满/案件全结案的项目直接不进候选，但记入 ``excluded_hints`` 保留线索。

第二层 **候选判定**（本模块）：给每个合格项目打 ``kind`` + ``score`` + ``reasons``。

    exact       案号命中，或 付款人/代付方 命中委托人 + 金额 = 应收余额   ← 最可信
    partial     付款人/代付方命中委托人，金额对不上
    amount_only 仅金额撞上应收余额，无任何实名证据

排序：``exact > partial > amount_only``，同类内按分数降序。

## 本模块不做的事

**不写任何财务数据。** 输出只是"建议 + 依据"，最终归属由人在首页确认
（需求原话：每一笔记账都应该人工确认）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.contracts.services.payment.intake_eligibility import (
    eligible_contract_qs,
    excluded_note,
    ineligible_reason,
    with_paid_total,
)
from apps.message_hub.services.contract_match import (
    AMOUNT_NEAR_RATIO,
    W_CASE_NUMBER,
    W_CONTRACT_NAME,
    W_PARTY_NAME,
    compute_outstanding,
    extract_case_numbers,
)
from apps.message_hub.services.transfer_notice import TransferNotice, parse_transfer_notice

logger = logging.getLogger("apps.message_hub")

# 判定类别
KIND_EXACT = "exact"
KIND_PARTIAL = "partial"
KIND_AMOUNT_ONLY = "amount_only"

# 类别排序权重（只用于排序，不参与展示分数）
_KIND_ORDER = {KIND_EXACT: 0, KIND_PARTIAL: 1, KIND_AMOUNT_ONLY: 2}

# 权重
W_ON_BEHALF_EXACT = 0.9  # 代付方命中委托人全称：银行备注明确指向该委托人
W_HISTORY_HINT = 0.15  # 历史收款备注含同一付款人/代付方
W_AMOUNT_EXACT = 0.45
W_AMOUNT_NEAR = 0.2

# 「弱候选」下限：低于它的不进快照，避免噪声
WEAK_CANDIDATE_THRESHOLD = Decimal("0.15")

# 候选上限（首页窄栏 + 详情页都够用）
MAX_CANDIDATES = 5


@dataclass
class Candidate:
    contract_id: int
    contract_name: str
    kind: str
    score: Decimal
    reasons: list[str] = field(default_factory=list)
    outstanding_amount: Decimal | None = None
    fee_mode: str = ""
    caveat: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_name": self.contract_name,
            "kind": self.kind,
            "score": float(self.score),
            "reasons": self.reasons,
            "outstanding_amount": str(self.outstanding_amount) if self.outstanding_amount is not None else None,
            "fee_mode": self.fee_mode,
            "caveat": self.caveat,
        }


def _party_names(contract: Any) -> list[tuple[str, str]]:
    """合同的 (当事人姓名, 身份) 列表。身份用于区分委托人与对方当事人。

    只把 **PRINCIPAL（委托人）** 当作强证据：对方当事人的名字出现在银行付款
    备注里几乎不可能，若也计入会造成误判。
    """
    names: list[tuple[str, str]] = []
    for cp in contract.contract_parties.all():
        if not cp.client_id:
            continue
        name = str(getattr(cp.client, "name", "") or "").strip()
        if name:
            names.append((name, str(getattr(cp, "role", "") or "")))
    return names


def _case_numbers_of(contract: Any) -> list[str]:
    """取合同关联案件的案号。

    v1 在这里读 ``case.case_number``（不存在）导致信号恒为 0。
    案号真实位置：``case.case_numbers`` 反向关系上的 ``number`` 字段。
    """
    numbers: list[str] = []
    for case in contract.cases.all():
        manager = getattr(case, "case_numbers", None)
        if manager is None:
            continue
        for cn in manager.all():
            value = str(getattr(cn, "number", "") or "").strip()
            if value:
                numbers.append(value)
    return numbers


def _history_mentions(contract: Any, probes: list[str]) -> list[str]:
    """历史收款备注里提到这些名字的证据。

    真实数据里付款人/代付方会在人工登记收款时写进 note
    （如「付款人：张某；代某供应链公司付律师费」），
    这是比金额可靠得多的"同一委托关系"线索。
    """
    hits: list[str] = []
    candidates = [p for p in probes if p and len(p) >= 2]
    if not candidates:
        return hits
    for payment in contract.payments.all():
        note = str(getattr(payment, "note", "") or "")
        if not note:
            continue
        for probe in candidates:
            if probe in note and probe not in hits:
                hits.append(probe)
    return hits


def score_contract(
    *,
    contract: Any,
    notice: TransferNotice,
    mail_case_numbers: list[str],
    mail_text: str,
) -> Candidate | None:
    """给单个**合格**合同打分。纯函数（除合同已预加载的关系），不写库。"""
    contract_name = str(getattr(contract, "name", "") or "")
    fee_mode = str(getattr(contract, "fee_mode", "") or "")

    paid_total = getattr(contract, "paid_total", None)
    cases = list(contract.cases.all())
    case_target_amounts = [getattr(c, "target_amount", None) for c in cases]
    outstanding, explain = compute_outstanding(contract, case_target_amounts, paid_total=paid_total)

    score = Decimal("0")
    reasons: list[str] = []
    # 实名证据分项标记（判定 kind 用，不能用单一 strong 布尔——
    # 否则无法区分「案号命中」与「仅名字相近」的可信度差异）
    on_behalf_hit = False
    payer_hit = False
    name_hit = False

    # 1) 案号命中
    contract_numbers = _case_numbers_of(contract)
    hit_numbers = [n for n in mail_case_numbers if n in contract_numbers]
    if hit_numbers:
        score += Decimal(str(W_CASE_NUMBER))
        reasons.append(f"案号命中 {hit_numbers[0]}")

    # 2) 代付方 / 付款人 命中委托人（只认 PRINCIPAL）
    parties = _party_names(contract)
    principals = [n for n, role in parties if role == "PRINCIPAL"]
    payer = (notice.payer_name or "").strip()
    on_behalf = (notice.on_behalf_of or "").strip()

    if on_behalf:
        hit = [p for p in principals if p and (p in on_behalf or on_behalf in p)]
        if hit:
            score += Decimal(str(W_ON_BEHALF_EXACT))
            reasons.append(f"代付方命中委托人「{hit[0]}」")
            on_behalf_hit = True
    if payer:
        hit = [p for p in principals if p and (p == payer or p in payer or payer in p)]
        if hit:
            payer_hit = True
            if on_behalf_hit:
                # 代付方已命中时，付款人再命中只作补充说明，不重复加分
                reasons.append(f"付款人 {payer}（代付）")
            else:
                score += Decimal(str(W_PARTY_NAME))
                reasons.append(f"付款人命中委托人「{hit[0]}」")

    # 3) 合同全名出现在正文里（名称太短容易误伤，要求 ≥6 字）
    if len(contract_name) >= 6 and contract_name in mail_text:
        score += Decimal(str(W_CONTRACT_NAME))
        reasons.append(f"合同名称命中「{contract_name[:16]}」")
        name_hit = True

    # 4) 历史收款备注线索
    history_hits = _history_mentions(contract, [payer, on_behalf])
    if history_hits:
        score += Decimal(str(W_HISTORY_HINT))
        reasons.append(f"历史收款备注含「{history_hits[0]}」")

    # 5) 金额 vs 应收余额
    amount = notice.amount
    amount_exact = False
    if outstanding is not None and amount is not None and outstanding > 0:
        if amount == outstanding:
            score += Decimal(str(W_AMOUNT_EXACT))
            reasons.append(f"金额 {amount} = 应收余额（{explain}）")
            amount_exact = True
        elif abs(amount - outstanding) <= outstanding * AMOUNT_NEAR_RATIO:
            score += Decimal(str(W_AMOUNT_NEAR))
            reasons.append(f"金额 {amount} ≈ 应收余额 {outstanding}")

    if not reasons:
        return None

    # 判定类别。
    #
    # 关键口径：**实名证据（案号 / 代付方 / 付款人命中委托人）本身就足以定案**，
    # 金额对不上不应把它降级。真实场景：160 号合同应收余额 67044.53，李某存入
    # 2400（尾款的一部分），金额永远对不上，但委托人本人存入的钱显然是这个项目
    # 的——降为 partial 会让人误以为要核对金额，反而多一层无用判断。
    # 金额只在**没有实名证据**时才是唯一的判据（amount_only），此时必须提醒风险。
    if hit_numbers or on_behalf_hit or payer_hit or name_hit:
        kind = KIND_EXACT
    elif amount_exact:
        kind = KIND_AMOUNT_ONLY
    else:
        # 既无实名证据、金额也只是近似 —— 不值得展示
        return None

    caveat = "" if outstanding is not None else explain
    if kind == KIND_AMOUNT_ONLY:
        caveat = "仅有金额吻合，缺少付款人/案号证据，请核对"

    return Candidate(
        contract_id=int(getattr(contract, "id", 0) or 0),
        contract_name=contract_name,
        kind=kind,
        score=min(score, Decimal("1")),
        reasons=reasons,
        outstanding_amount=outstanding,
        fee_mode=fee_mode,
        caveat=caveat,
    )


def rank_candidates(candidates: list[Candidate], *, limit: int = MAX_CANDIDATES) -> list[Candidate]:
    """按类别排序，同类内分数降序。

    v1 只按分数排序，导致「仅金额撞车」压过「实名命中」。类别优先是 v2 的核心修正。
    """
    ranked = [c for c in candidates if c.score >= WEAK_CANDIDATE_THRESHOLD]
    ranked.sort(key=lambda c: (_KIND_ORDER.get(c.kind, 9), -c.score, c.contract_id))
    return ranked[:limit]


def _collect_excluded_hints(
    *, notice: TransferNotice, mail_case_numbers: list[str], mail_text: str, eligible_ids: set[int]
) -> list[dict[str, Any]]:
    """收集被资格规则排除、但**有实名线索**的项目。

    设计文档 §3.5：既执行「收满/结案不匹配」，又不丢线索。只收有实名证据的
    （否则会把几十个无关的已归档项目全列出来）。
    """
    from apps.contracts.models import Contract

    payer = (notice.payer_name or "").strip()
    on_behalf = (notice.on_behalf_of or "").strip()
    if not payer and not mail_case_numbers and not on_behalf:
        return []

    hints: list[dict[str, Any]] = []
    # 必须走 with_paid_total 注解：excluded_note 要显示「已收 X / 应收 Y」，
    # 没有注解得再打一轮 N+1 聚合。
    qs = (
        with_paid_total(Contract.objects.exclude(id__in=eligible_ids))
        .prefetch_related("cases__case_numbers", "contract_parties__client", "payments")
        .only("id", "name", "status", "fixed_amount", "risk_rate", "fee_mode")
    )
    for contract in qs:
        reason = ineligible_reason(contract)
        if not reason:
            continue

        principals = [n for n, role in _party_names(contract) if role == "PRINCIPAL"]
        matched: list[str] = []
        if on_behalf:
            matched += [p for p in principals if p and (p in on_behalf or on_behalf in p)]
        if payer:
            matched += [p for p in principals if p and (p == payer or p in payer or payer in p)]
        hit_numbers = [n for n in mail_case_numbers if n in _case_numbers_of(contract)]
        if not matched and not hit_numbers:
            continue

        hints.append(
            {
                "contract_id": int(contract.id),
                "contract_name": str(contract.name or ""),
                "excluded_by": reason,
                "note": excluded_note(reason, contract, paid_total=getattr(contract, "paid_total", None)),
            }
        )
    # 有委托人对上的排前面
    hints.sort(key=lambda h: (h["excluded_by"] != "fully_paid", h["contract_id"]))
    return hints[:5]


def suggest_contracts_for_transfer(*, subject: str = "", body_text: str = "", body_html: str = "") -> dict[str, Any]:
    """给一封到账通知算出候选项目。

    返回结构对应 ``PaymentIntake.match_snapshot``（设计文档 §3.5）。
    **不写任何数据**，纯只读。
    """
    notice = parse_transfer_notice(subject=subject, body_text=body_text, body_html=body_html)
    mail_text = "\n".join(p for p in (subject or "", body_text or "") if p).strip()
    if not mail_text and body_html:
        from apps.message_hub.services.transfer_notice import html_to_text

        mail_text = html_to_text(body_html)
    mail_case_numbers = extract_case_numbers(mail_text)

    eligible = list(
        eligible_contract_qs().prefetch_related("cases__case_numbers", "contract_parties__client", "payments")
    )
    eligible_ids = {int(c.id) for c in eligible}

    candidates: list[Candidate] = []
    for contract in eligible:
        candidate = score_contract(
            contract=contract, notice=notice, mail_case_numbers=mail_case_numbers, mail_text=mail_text
        )
        if candidate is not None:
            candidates.append(candidate)

    ranked = rank_candidates(candidates)
    excluded_hints = _collect_excluded_hints(
        notice=notice, mail_case_numbers=mail_case_numbers, mail_text=mail_text, eligible_ids=eligible_ids
    )

    return {
        "matcher_version": "v2",
        "parsed": {
            "amount": str(notice.amount) if notice.amount is not None else None,
            "payer_name": notice.payer_name,
            "on_behalf_of": notice.on_behalf_of,
            "received_at": notice.received_at.isoformat() if notice.received_at else None,
            "evidence": notice.evidence,
        },
        "candidates": [c.as_dict() for c in ranked],
        "excluded_hints": excluded_hints,
        "mail_case_numbers": mail_case_numbers,
    }
