"""邮件 → 在办合同 自动关联匹配的纯函数测试。

锁定的核心行为：
1. 金额/案号提取的口径（全角括号、千分位、多种金额写法）；
2. 应收余额的计算口径（**比余额不比合同总额**）—— 这是本模块最关键的设计，
   风险收费三种模式必须各自算对；
3. 打分与阈值：只有案号级信号够得上「确定匹配」，其余要人工；
4. 真实回归：付款人姓名能在金额完全对不上时仍把正确合同顶出来。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.message_hub.services.contract_match import (
    CONFIDENT_THRESHOLD,
    build_mail_text,
    compute_outstanding,
    extract_amounts,
    extract_case_numbers,
    rank_candidates,
    score_contract,
)


def _contract(**kwargs):
    """构造一个够 compute_outstanding / score_contract 用的假合同。"""
    base = {
        "id": 1,
        "name": "测试合同",
        "fee_mode": "FIXED",
        "fixed_amount": None,
        "risk_rate": None,
        "paid_total": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestExtractCaseNumbers:
    def test_full_width_parentheses(self):
        assert extract_case_numbers("请查收（2026）粤0604民初29662号文书") == ["（2026）粤0604民初29662号"]  # privacy-allow

    def test_half_width_parentheses(self):
        assert extract_case_numbers("(2023)粤0606执保34791号") == ["（2023）粤0606执保34791号"]  # privacy-allow

    def test_multiple_and_dedup(self):
        text = "（2026）粤0604民初1号 和 (2026)粤0604民初2号，再次提到（2026）粤0604民初1号"  # privacy-allow
        assert extract_case_numbers(text) == ["（2026）粤0604民初1号", "（2026）粤0604民初2号"]  # privacy-allow

    def test_no_match(self):
        assert extract_case_numbers("这封邮件没有案号") == []
        assert extract_case_numbers("") == []


class TestExtractAmounts:
    def test_renminbi_with_hao(self):
        assert extract_amounts("存入人民币 2400 元") == [Decimal("2400")]

    def test_thousands_separator(self):
        assert extract_amounts("人民币 12,345.67 元") == [Decimal("12345.67")]

    def test_yen_symbol(self):
        assert extract_amounts("付款 ¥3000.00") == [Decimal("3000.00")]

    def test_sorted_desc_and_dedup(self):
        assert extract_amounts("人民币 100 元，另有 ¥999 元，再提 100 元") == [Decimal("999"), Decimal("100")]

    def test_no_amount(self):
        assert extract_amounts("没有任何金额的邮件") == []


class TestComputeOutstanding:
    """应收余额口径 —— 比余额不比合同总额。"""

    def test_fixed_minus_paid(self):
        contract = _contract(fee_mode="FIXED", fixed_amount=Decimal("30000"), paid_total=Decimal("28000"))
        outstanding, _ = compute_outstanding(contract, [])
        assert outstanding == Decimal("2000")

    def test_fixed_no_payment_yet(self):
        contract = _contract(fee_mode="FIXED", fixed_amount=Decimal("8000"), paid_total=None)
        outstanding, _ = compute_outstanding(contract, [])
        assert outstanding == Decimal("8000")

    def test_fixed_without_amount_is_none(self):
        contract = _contract(fee_mode="FIXED", fixed_amount=None)
        outstanding, reason = compute_outstanding(contract, [])
        assert outstanding is None
        assert "未填固定律师费" in reason

    def test_full_risk_uses_target_amount(self):
        contract = _contract(fee_mode="FULL_RISK", fixed_amount=None, risk_rate=Decimal("8"), paid_total=None)
        # 标的额 1,121,783.76 × 8% = 89,742.7008
        outstanding, _ = compute_outstanding(contract, [Decimal("1121783.76")])
        assert outstanding == Decimal("1121783.76") * Decimal("8") / Decimal("100")

    def test_full_risk_without_target_amount_needs_manual(self):
        """全风险合同缺标的额时无法推算，必须落人工而不是瞎猜。"""
        contract = _contract(fee_mode="FULL_RISK", risk_rate=Decimal("15"), paid_total=None)
        outstanding, reason = compute_outstanding(contract, [None])
        assert outstanding is None
        assert "标的额未填" in reason

    def test_semi_risk_fixed_plus_risk_part(self):
        contract = _contract(
            fee_mode="SEMI_RISK", fixed_amount=Decimal("9000"), risk_rate=Decimal("15"), paid_total=None
        )
        # 前期 9000 + 386,963.50 × 15% = 9000 + 58,044.525
        outstanding, _ = compute_outstanding(contract, [Decimal("386963.50")])
        assert outstanding == Decimal("9000") + Decimal("386963.50") * Decimal("15") / Decimal("100")

    def test_semi_risk_targets_take_max_across_cases(self):
        """一个合同挂多个案件时，标的额取最大（风险费按大标的算）。"""
        contract = _contract(fee_mode="SEMI_RISK", fixed_amount=Decimal("0"), risk_rate=Decimal("10"), paid_total=None)
        outstanding, _ = compute_outstanding(contract, [Decimal("100"), Decimal("500")])
        assert outstanding == Decimal("50")

    def test_custom_needs_manual(self):
        contract = _contract(fee_mode="CUSTOM", paid_total=None)
        outstanding, reason = compute_outstanding(contract, [])
        assert outstanding is None
        assert "自定义" in reason

    def test_legacy_risk_mode_treated_as_risk(self):
        """脏数据 'risk'（不在枚举里）按风险类处理，并给出明确说明而不是崩。"""
        contract = _contract(fee_mode="risk", fixed_amount=Decimal("5000"), risk_rate=Decimal("12"), paid_total=None)
        outstanding, _ = compute_outstanding(contract, [Decimal("1000")])
        assert outstanding is not None


class TestScoreContract:
    def _score(self, *, mail_text, amounts=(), mail_numbers=(), contract_numbers=(), targets=(), parties=(), **ck):
        return score_contract(
            contract=_contract(**ck),
            mail_text=mail_text,
            mail_amounts=list(amounts),
            mail_case_numbers=list(mail_numbers),
            contract_case_numbers=list(contract_numbers),
            case_target_amounts=list(targets),
            party_names=list(parties),
        )

    def test_case_number_hit_reaches_confident(self):
        cand = self._score(
            mail_text="请查收（2026）粤0604民初1号",  # privacy-allow
            mail_numbers=["（2026）粤0604民初1号"],  # privacy-allow
            contract_numbers=["（2026）粤0604民初1号"],  # privacy-allow
            fee_mode="FIXED",
            fixed_amount=Decimal("30000"),
        )
        assert cand.score >= CONFIDENT_THRESHOLD
        assert any("案号命中" in r for r in cand.reasons)

    def test_amount_alone_never_reaches_confident(self):
        """关键约束：只靠金额永远不够确定匹配（同名同额合同太多）。"""
        cand = self._score(
            mail_text="收到 30000 元",
            amounts=[Decimal("30000")],
            fee_mode="FIXED",
            fixed_amount=Decimal("30000"),
        )
        assert cand.score < CONFIDENT_THRESHOLD

    def test_outstanding_beats_contract_total(self):
        """已收 28000 的 30000 合同，来 2000 才对得上；来 30000 反而不对。"""
        cand = self._score(
            mail_text="收到 2000 元",
            amounts=[Decimal("2000")],
            fee_mode="FIXED",
            fixed_amount=Decimal("30000"),
            paid_total=Decimal("28000"),
        )
        assert any("应收余额" in r for r in cand.reasons)

    def test_no_signal_scores_zero(self):
        cand = self._score(mail_text="一封无关的邮件", fee_mode="FIXED", fixed_amount=Decimal("30000"))
        assert cand.score == 0

    def test_caveat_reported_when_outstanding_unknown(self):
        cand = self._score(
            mail_text="收到 100 元", amounts=[Decimal("100")], fee_mode="FULL_RISK", risk_rate=Decimal("10")
        )
        assert cand.caveat
        assert "标的额未填" in cand.caveat

    def test_real_regression_payer_name_rescues_when_amount_mismatches(self):
        """真实回归（银行到账通知形态）：
        金额 2400 与合同应收余额 67044.53 对不上，但付款人「张某」命中当事人，
        仍应把该合同作为候选顶出来 —— 金额不可靠时靠当事人兜住。
        """
        cand = self._score(
            mail_text="【某银行】张某于 1 月 1 日向贵公司 0000 账户汇入人民币 2400 元",
            amounts=[Decimal("2400")],
            parties=["张某"],
            fee_mode="SEMI_RISK",
            fixed_amount=Decimal("9000"),
            risk_rate=Decimal("15"),
            paid_total=Decimal("0"),
            targets=[Decimal("386963.50")],
        )
        assert cand.score > 0
        assert any("当事人命中" in r for r in cand.reasons)


class TestRankCandidates:
    def _c(self, cid, score):
        from apps.message_hub.services.contract_match import MatchCandidate

        return MatchCandidate(contract_id=cid, contract_name=f"合同{cid}", score=Decimal(str(score)))

    def test_drops_below_threshold(self):
        ranked = rank_candidates([self._c(1, "0.05"), self._c(2, "0.5")])
        assert [c.contract_id for c in ranked] == [2]

    def test_sorted_by_score_desc(self):
        ranked = rank_candidates([self._c(1, "0.3"), self._c(2, "0.9"), self._c(3, "0.5")])
        assert [c.contract_id for c in ranked] == [2, 3, 1]

    def test_limit(self):
        ranked = rank_candidates([self._c(i, "0.5") for i in range(1, 11)], limit=3)
        assert len(ranked) == 3

    def test_empty(self):
        assert rank_candidates([]) == []


class TestBuildMailText:
    def test_strips_html_tags(self):
        text = build_mail_text(
            subject="【到账通知】",
            body_text="",
            body_html="<html><body><p>人民币 <b>2400</b> 元</p></body></html>",
        )
        assert "到账通知" in text
        assert "2400" in text
        assert "<p>" not in text

    def test_handles_entities(self):
        text = build_mail_text(subject="", body_text="", body_html="A&nbsp;B")
        assert "A B" in text
