"""到账匹配 v2 的纯函数测试。

锁定的核心行为（都是 v1 在真实数据上翻过的车）：

1. **已收满/已归档/案件已结案的项目不进候选** —— 需求：「project 收完款项后，
   或者结案、归档后，就不应该匹配到」。
2. **仅金额撞车的候选排在实名命中的候选之后** —— v1 把 amount_only(0.55)
   压在当事人命中(0.45)上面，导致 #547 错配到无关项目。
3. **实名命中即定案（exact）**，金额对不上不降级 —— 160 号合同应收 67044.53，
   委托人李某存入 2400 属尾款一部分，金额永远对不上但归属明确。  # privacy-allow
4. **案号信号真的生效** —— v1 读 ``case.case_number``（不存在的属性），信号恒为 0。
5. **被排除但有关联的项目写入 excluded_hints**，既执行规则又不丢线索。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from apps.contracts.services.payment.intake_eligibility import (
    EXCLUDED_ARCHIVED,
    EXCLUDED_CASE_CLOSED,
    EXCLUDED_FULLY_PAID,
    EXCLUDED_UNSIGNED,
    ineligible_reason,
)
from apps.message_hub.services.contract_match_v2 import (
    KIND_AMOUNT_ONLY,
    KIND_EXACT,
    Candidate,
    rank_candidates,
    score_contract,
)
from apps.message_hub.services.transfer_notice import TransferNotice


def _notice(amount="2400", payer="", on_behalf=""):
    return TransferNotice(
        amount=Decimal(amount) if amount is not None else None,
        payer_name=payer,
        on_behalf_of=on_behalf,
    )


def _case(*, case_numbers=(), target_amount=None, status="active"):
    return SimpleNamespace(
        case_numbers=SimpleNamespace(all=lambda: [SimpleNamespace(number=n) for n in case_numbers]),
        target_amount=Decimal(target_amount) if target_amount else None,
        status=status,
    )


def _payment(note=""):
    return SimpleNamespace(note=note)


def _contract(
    *,
    cid=1,
    name="测试合同",
    fee_mode="FIXED",
    fixed_amount=None,
    risk_rate=None,
    parties=(),
    cases=(),
    payments=(),
    status="active",
    paid_total=None,
):
    """构造够 score_contract 用的假合同（关系都预加载成列表）。"""
    return SimpleNamespace(
        id=cid,
        name=name,
        fee_mode=fee_mode,
        fixed_amount=Decimal(fixed_amount) if fixed_amount else None,
        risk_rate=Decimal(risk_rate) if risk_rate else None,
        status=status,
        paid_total=Decimal(paid_total) if paid_total is not None else None,
        contract_parties=SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    client_id=1,
                    client=SimpleNamespace(name=n),
                    role=role,
                )
                for n, role in parties
            ]
        ),
        cases=SimpleNamespace(all=lambda: list(cases)),
        payments=SimpleNamespace(all=lambda: list(payments)),
    )


class TestEligibilityExclusion:
    """资格过滤：收满 / 归档 / 未签约 / 案件结案 一律不进候选。"""

    def test_fully_paid_excluded(self):
        """需求原话：project 收完款项后就不应该再匹配到。"""
        c = _contract(fixed_amount="50000", paid_total="50000")
        assert ineligible_reason(c, paid_total=Decimal("50000")) == EXCLUDED_FULLY_PAID

    def test_over_paid_also_excluded(self):
        c = _contract(fixed_amount="50000", paid_total="60000")
        assert ineligible_reason(c, paid_total=Decimal("60000")) == EXCLUDED_FULLY_PAID

    def test_partial_paid_still_eligible(self):
        c = _contract(fixed_amount="50000", paid_total="28000")
        assert ineligible_reason(c, paid_total=Decimal("28000")) == ""

    def test_archived_excluded(self):
        assert ineligible_reason(_contract(status="archived")) == EXCLUDED_ARCHIVED

    def test_unsigned_excluded(self):
        assert ineligible_reason(_contract(status="unsigned")) == EXCLUDED_UNSIGNED

    def test_all_cases_closed_excluded(self):
        c = _contract(cases=[_case(status="closed"), _case(status="closed")])
        assert ineligible_reason(c) == EXCLUDED_CASE_CLOSED

    def test_one_active_case_keeps_eligible(self):
        c = _contract(cases=[_case(status="closed"), _case(status="active")])
        assert ineligible_reason(c) == ""

    def test_no_cases_not_excluded_by_case_rule(self):
        """没挂案件的非诉项目不该被"结案"规则误伤。"""
        assert ineligible_reason(_contract(cases=[])) == ""

    def test_full_risk_without_fixed_amount_not_treated_as_paid(self):
        """fixed_amount 为空时无法判上限，不算收满（全风险合同常见）。"""
        c = _contract(fee_mode="FULL_RISK", risk_rate="15", paid_total="5000")
        assert ineligible_reason(c, paid_total=Decimal("5000")) != EXCLUDED_FULLY_PAID


class TestScoreContractKind:
    """判定类别：实名证据定案，金额单独不够。"""

    def test_payer_hit_is_exact_even_when_amount_mismatches(self):
        """真实回归 #533：李某存入 2400，合同应收 67044.53，仍应判 exact。"""
        c = _contract(
            cid=160,
            name="李某诉某木制品公司合同纠纷一案",  # privacy-allow
            fee_mode="SEMI_RISK",
            fixed_amount="9000",
            risk_rate="15",
            parties=[("李某", "PRINCIPAL")],  # privacy-allow
            cases=[_case(target_amount="386963.50")],
        )
        cand = score_contract(
            contract=c,
            notice=_notice("2400", payer="李某"),
            mail_case_numbers=[],
            mail_text="",  # privacy-allow
        )
        assert cand is not None
        assert cand.kind == KIND_EXACT
        assert any("付款人命中委托人" in r for r in cand.reasons)

    def test_on_behalf_hit_is_exact(self):
        c = _contract(
            name="某公司与税务局税务处理案",
            fixed_amount="50000",
            parties=[("某供应链公司", "PRINCIPAL")],  # privacy-allow
        )
        cand = score_contract(
            contract=c,
            notice=_notice("10000", payer="张某", on_behalf="某供应链公司"),  # privacy-allow
            mail_case_numbers=[],
            mail_text="",
        )
        assert cand is not None
        assert cand.kind == KIND_EXACT
        assert any("代付方命中委托人" in r for r in cand.reasons)

    def test_amount_only_is_flagged(self):
        """仅金额撞车 → amount_only + caveat 提醒核对。"""
        c = _contract(cid=270, fixed_amount="10000", parties=[("无关公司", "PRINCIPAL")])
        cand = score_contract(
            contract=c, notice=_notice("10000", payer="张某"), mail_case_numbers=[], mail_text=""
        )  # privacy-allow
        assert cand is not None
        assert cand.kind == KIND_AMOUNT_ONLY
        assert "核对" in cand.caveat

    def test_opposing_party_name_does_not_count(self):
        """对方当事人的名字出现在银行备注里几乎不可能，不能当实名证据。"""
        c = _contract(fixed_amount="10000", parties=[("某对手公司", "OPPOSING")])
        cand = score_contract(contract=c, notice=_notice("100", payer="某对手公司"), mail_case_numbers=[], mail_text="")
        # 无实名证据、金额也不对 → 不产出候选
        assert cand is None

    def test_case_number_signal_actually_works(self):
        """v1 读 case.case_number（不存在）导致信号恒为 0；v2 从 case_numbers 取。"""
        c = _contract(fixed_amount="30000", cases=[_case(case_numbers=["（2026）粤0604民初1号"])])  # privacy-allow
        cand = score_contract(
            contract=c,
            notice=_notice("100"),
            mail_case_numbers=["（2026）粤0604民初1号"],  # privacy-allow
            mail_text="",
        )
        assert cand is not None
        assert cand.kind == KIND_EXACT
        assert any("案号命中" in r for r in cand.reasons)
        assert cand.score >= Decimal("0.9")

    def test_history_note_adds_hint(self):
        c = _contract(
            fixed_amount="50000",
            parties=[("某供应链公司", "PRINCIPAL")],  # privacy-allow
            payments=[_payment("付款人：张某；代某供应链公司付律师费")],  # privacy-allow
        )
        cand = score_contract(
            contract=c,
            notice=_notice("10000", payer="张某", on_behalf="某供应链公司"),  # privacy-allow
            mail_case_numbers=[],
            mail_text="",
        )
        assert cand is not None
        assert any("历史收款备注" in r for r in cand.reasons)

    def test_no_signal_yields_none(self):
        c = _contract(fixed_amount="30000")
        assert score_contract(contract=c, notice=_notice("100"), mail_case_numbers=[], mail_text="") is None

    def test_fully_paid_contract_has_zero_outstanding(self):
        """收满的合同余额为 0，金额永远对不上——所以只能靠资格层排除，
        不能指望金额信号把它排下去。这里锁住应收余额的计算口径。
        """
        from apps.message_hub.services.contract_match import compute_outstanding

        c = _contract(fixed_amount="50000", parties=[("某公司", "PRINCIPAL")])
        outstanding, _ = compute_outstanding(c, [], paid_total=Decimal("50000"))
        assert outstanding == Decimal("0")


class TestRankCandidates:
    """排序：实名命中必须压在"仅金额撞车"之上（v1 的核心 bug）。"""

    def _c(self, cid, kind, score):
        return Candidate(contract_id=cid, contract_name=f"合同{cid}", kind=kind, score=Decimal(str(score)))

    def test_amount_only_loses_to_exact_despite_higher_score(self):
        """真实回归 #547：amount_only 0.55 不能压过 exact 0.45。"""
        ranked = rank_candidates(
            [
                self._c(270, KIND_AMOUNT_ONLY, "0.55"),
                self._c(446, KIND_EXACT, "0.45"),
            ]
        )
        assert [c.contract_id for c in ranked] == [446, 270]

    def test_same_kind_sorted_by_score(self):
        ranked = rank_candidates(
            [
                self._c(1, KIND_EXACT, "0.3"),
                self._c(2, KIND_EXACT, "0.9"),
            ]
        )
        assert [c.contract_id for c in ranked] == [2, 1]

    def test_drops_below_threshold(self):
        ranked = rank_candidates([self._c(1, KIND_EXACT, "0.01")])
        assert ranked == []

    def test_limit(self):
        ranked = rank_candidates([self._c(i, KIND_EXACT, "0.5") for i in range(10)], limit=3)
        assert len(ranked) == 3

    def test_empty(self):
        assert rank_candidates([]) == []

    def test_multiple_amount_only_all_after_exact(self):
        ranked = rank_candidates(
            [
                self._c(1, KIND_AMOUNT_ONLY, "0.9"),
                self._c(2, KIND_EXACT, "0.2"),
            ]
        )
        assert ranked[0].contract_id == 2
