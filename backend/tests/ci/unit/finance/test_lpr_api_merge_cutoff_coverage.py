"""补充覆盖测试: finance/api/lpr_api.py 的 _merge_interest_cutoff

endpoint 函数体均带 pragma: no cover，可测逻辑集中在止算日合并口径：
- 本金/违约金/费用取整段（full），未付利息取止算段（cut）
- 罚息/复利按 cont_penalty / cont_compound 开关取整段或止算段
- cumulative 与 per-item 两种舍入模式
- warnings 文案生成
"""

from __future__ import annotations

from decimal import Decimal

from apps.finance.api.lpr_api import _merge_interest_cutoff


def _full_claim() -> dict:
    return {
        "claim": {
            "claim_date": "2026-06-30",
            "outstanding_principal": "100000.00",
            "unpaid_interest": "5000.555",
            "penalty_interest": "3000.555",
            "compound_interest": "1000.555",
            "lump_penalty": "200.444",
            "other_fees": "50.333",
            "total_claim": "99999.99",
        },
        "schedule_rows": [],
    }


def _cut_claim() -> dict:
    return {
        "claim": {
            "claim_date": "2026-03-31",
            "outstanding_principal": "100000.00",
            "unpaid_interest": "2000.111",
            "penalty_interest": "800.222",
            "compound_interest": "300.333",
            "lump_penalty": "0",
            "other_fees": "0",
            "total_claim": "0",
        }
    }


class TestMergeInterestCutoffDefaults:
    def test_unpaid_interest_takes_cut_value(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        assert result["claim"]["unpaid_interest"] == "2000.11"

    def test_penalty_and_compound_take_cut_when_switches_off(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        assert result["claim"]["penalty_interest"] == "800.22"
        assert result["claim"]["compound_interest"] == "300.33"

    def test_penalty_and_compound_take_full_when_switches_on(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=True, cont_compound=True
        )
        assert result["claim"]["penalty_interest"] == "3000.56"  # 3000.555 → HALF_UP
        assert result["claim"]["compound_interest"] == "1000.56"

    def test_principal_lump_fees_always_full(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        # 本金/违约金/费用不因止算收缩
        assert result["claim"]["outstanding_principal"] == "100000.00"


class TestMergeInterestCutoffRounding:
    def test_cumulative_rounds_total_once(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        principal = Decimal("100000.00")
        interest = Decimal("2000.111")
        penalty = Decimal("800.222")
        compound = Decimal("300.333")
        lump = Decimal("200.444")
        fees = Decimal("50.333")
        expected = (principal + interest + penalty + compound + lump + fees).quantize(Decimal("0.01"))
        assert Decimal(result["claim"]["total_claim"]) == expected

    def test_per_item_rounds_each_component(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="per_item", cont_penalty=False, cont_compound=False
        )
        q = Decimal("0.01")
        expected = (
            Decimal("100000.00").quantize(q)
            + Decimal("2000.111").quantize(q)
            + Decimal("800.222").quantize(q)
            + Decimal("300.333").quantize(q)
            + Decimal("200.444").quantize(q)
            + Decimal("50.333").quantize(q)
        )
        assert Decimal(result["claim"]["total_claim"]) == expected

    def test_cumulative_and_per_item_differ_on_half_cases(self):
        """构造 .005 边界：cumulative 一次舍入 vs per_item 逐项舍入结果不同。

        _merge 会原地改写 full 的嵌套 claim，两次调用必须各用全新字典。
        """

        def _half_full() -> dict:
            return {
                "claim": {
                    "claim_date": "2026-06-30",
                    "outstanding_principal": "0.005",
                    "unpaid_interest": "0",
                    "penalty_interest": "0",
                    "compound_interest": "0",
                    "lump_penalty": "0",
                    "other_fees": "0",
                    "total_claim": "0",
                }
            }

        def _half_cut() -> dict:
            return {
                "claim": {
                    "claim_date": "2026-03-31",
                    "outstanding_principal": "0",
                    "unpaid_interest": "0.005",
                    "penalty_interest": "0",
                    "compound_interest": "0.005",
                    "lump_penalty": "0",
                    "other_fees": "0",
                    "total_claim": "0",
                }
            }

        cumulative = _merge_interest_cutoff(
            full=_half_full(), cut=_half_cut(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        per_item = _merge_interest_cutoff(
            full=_half_full(), cut=_half_cut(), rounding_mode="per_item", cont_penalty=False, cont_compound=False
        )
        # 0.005×3（本金 + 止算利息 + 止算复利）:
        # cumulative 先求和 0.015 → 0.02; per_item 逐项 HALF_UP 0.01×3 = 0.03
        assert Decimal(cumulative["claim"]["total_claim"]) == Decimal("0.02")
        assert Decimal(per_item["claim"]["total_claim"]) == Decimal("0.03")


class TestMergeInterestCutoffWarnings:
    def test_both_switches_off_all_stop_wording(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        warnings = result["warnings"]
        assert len(warnings) == 1
        assert "2026-03-31" in warnings[0]
        assert "均止算" in warnings[0]

    def test_penalty_continues_wording(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=True, cont_compound=False
        )
        warning = result["warnings"][0]
        assert "罚息继续计算至计算截止日" in warning
        assert "复利" not in warning.split("；")[-1]

    def test_penalty_and_compound_continue_wording(self):
        result = _merge_interest_cutoff(
            full=_full_claim(), cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=True, cont_compound=True
        )
        warning = result["warnings"][0]
        assert "罚息、复利继续计算至计算截止日" in warning

    def test_warning_appended_not_replacing_existing(self):
        full = _full_claim()
        full["warnings"] = ["既有警告"]
        result = _merge_interest_cutoff(
            full=full, cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        assert result["warnings"][0] == "既有警告"
        assert len(result["warnings"]) == 2


class TestMergeInterestCutoffReturnsSameDict:
    def test_mutates_and_returns_full_dict(self):
        full = _full_claim()
        result = _merge_interest_cutoff(
            full=full, cut=_cut_claim(), rounding_mode="cumulative", cont_penalty=False, cont_compound=False
        )
        assert result is full
        # 其它键保持
        assert result["schedule_rows"] == []
