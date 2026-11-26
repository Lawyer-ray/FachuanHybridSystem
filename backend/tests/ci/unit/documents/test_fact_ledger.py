"""事实账本（fact_ledger）单测：出处核对、三档过滤、一致性核对、软失败。

覆盖：
- 出处核不到 → 丢弃 + warning（账本里不许留下材料中没有的引文）
- inference 留在账本里给律师看，但 writable_facts 不放行（推断不得直接进文书）
- 分项之和 ≠ 声称合计（超出 0.01 容差）→ conflicts；容差内不算冲突
- 同 key 多值、日期区间倒置、日比率超过 0.5% → conflicts
- 模型挂掉 / 输出不是 JSON → 空 facts + warnings，绝不抛
- limit 截断生效
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.documents.services.draft.fact_ledger import ConflictKind, FactBasis, LLMCaller, extract_ledger

#: 虚构材料：律师函（欠款）+ 合同（承包金/期限/管辖）+ 补充协议（期限延长）。
#: 所有数字都是自造值，只为把「分项 / 合计 / 期限 / 日比率」四类核对都摆在同一段原文里。
MATERIAL_TEXT = (
    "律师函：截至本函发出之日，贵方尚欠管理维护费 361,320.00 元、水费 42,901.00 元，"
    "合计 404,221.00 元。请于收到本函之日起十日内付清。\n"
    "土地分包合同书 三、承包金：首个承包年度承包金 384,277 元，于 2026 年 5 月 8 日前缴交；"
    "逾期按每日 3‰ 计收违约金。\n"
    "九、本合同期限自 2023 年 12 月 28 日起至 2026 年 5 月 7 日止。\n"
    "十、因本合同发生争议，由地块所在地人民法院管辖。\n"
    "补充协议：合同期限延长至 2026 年 12 月 31 日。"
)


def make_fact(
    key: str,
    value: str,
    source: str,
    basis: FactBasis = FactBasis.CONTRACT_CLAUSE,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {"key": key, "value": value, "source": source, "basis": str(basis), "confidence": confidence}


def fake_caller(*facts: dict[str, Any]) -> LLMCaller:
    """固定回一份合法账本 JSON 的模型调用口。"""
    payload = json.dumps({"facts": list(facts)}, ensure_ascii=False)

    def _call(messages: list[dict[str, str]]) -> str:
        return payload

    return _call


class TestSourceLocating:
    def test_source_not_in_material_is_dropped_with_warning(self) -> None:
        """D3 的原始形态：模型补的「保证金缴交」在材料里核不到出处，必须作废。"""
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact(
                    "保证金缴交",
                    "1,061,814.25 元",
                    "被告于 2026 年 5 月 8 日缴交履约保证金 1,061,814.25 元",
                    FactBasis.INFERENCE,
                )
            ),
        )
        assert ledger.facts == []
        assert any("出处" in warning for warning in ledger.warnings)

    def test_source_matching_ignores_whitespace_differences(self) -> None:
        """OCR 会在词中间塞空格：引文与原文只差空白时必须仍算核到。"""
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact("管理维护费", "361,320.00 元", "管理维护费  361,320.00  元", FactBasis.LETTER)
            ),
        )
        assert [fact.key for fact in ledger.facts] == ["管理维护费"]
        assert ledger.warnings == []

    def test_empty_material_never_calls_model(self) -> None:
        def exploding_caller(messages: list[dict[str, str]]) -> str:
            raise AssertionError("空材料不该调用模型")

        ledger = extract_ledger("   ", llm_caller=exploding_caller)
        assert ledger.facts == []
        assert ledger.warnings


class TestBasis:
    def test_inference_stays_in_ledger_but_not_writable(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact("承包金", "384,277 元", "首个承包年度承包金 384,277 元"),
                make_fact("承包金缴交日", "2026 年 5 月 8 日", "于 2026 年 5 月 8 日前缴交", FactBasis.INFERENCE),
            ),
        )
        assert len(ledger.facts) == 2
        assert [fact.key for fact in ledger.writable_facts()] == ["承包金"]

    def test_letter_and_contract_clause_are_both_writable(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact("管理维护费", "361,320.00 元", "管理维护费 361,320.00 元", FactBasis.LETTER),
                make_fact("管辖", "地块所在地人民法院", "由地块所在地人民法院管辖"),
            ),
        )
        assert {fact.basis for fact in ledger.writable_facts()} == {FactBasis.LETTER, FactBasis.CONTRACT_CLAUSE}


class TestConsistency:
    def test_amount_sum_mismatch_blocks_every_involved_key(self) -> None:
        material = "对账单：管理维护费 100.00 元、水费 200.00 元，合计 400.00 元。"
        ledger = extract_ledger(
            material,
            llm_caller=fake_caller(
                make_fact("欠款-管理维护费", "100.00 元", "管理维护费 100.00 元", FactBasis.LETTER),
                make_fact("欠款-水费", "200.00 元", "水费 200.00 元", FactBasis.LETTER),
                make_fact("欠款合计", "400.00 元", "合计 400.00 元", FactBasis.LETTER),
            ),
        )
        kinds = {conflict.kind for conflict in ledger.conflicts}
        assert ConflictKind.AMOUNT_SUM in kinds
        blocked = {key for conflict in ledger.conflicts for key in conflict.keys}
        assert blocked == {"欠款-管理维护费", "欠款-水费", "欠款合计"}
        assert ledger.writable_facts() == []

    def test_amount_sum_within_tolerance_is_clean(self) -> None:
        """容差是一分钱：300.01 vs 300.00 不算冲突（合同金额都是两位小数）。"""
        material = "对账单：管理维护费 100.00 元、水费 200.00 元，合计 300.01 元。"
        ledger = extract_ledger(
            material,
            llm_caller=fake_caller(
                make_fact("欠款-管理维护费", "100.00 元", "管理维护费 100.00 元", FactBasis.LETTER),
                make_fact("欠款-水费", "200.00 元", "水费 200.00 元", FactBasis.LETTER),
                make_fact("欠款合计", "300.01 元", "合计 300.01 元", FactBasis.LETTER),
            ),
        )
        assert ledger.conflicts == []

    def test_same_key_two_values_conflict(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact(
                    "合同期限",
                    "2023 年 12 月 28 日至 2026 年 5 月 7 日",
                    "本合同期限自 2023 年 12 月 28 日起至 2026 年 5 月 7 日止",
                ),
                make_fact(
                    "合同期限", "2023 年 12 月 28 日至 2026 年 12 月 31 日", "合同期限延长至 2026 年 12 月 31 日"
                ),
                make_fact("管辖", "地块所在地人民法院", "由地块所在地人民法院管辖"),
            ),
        )
        assert [conflict.kind for conflict in ledger.conflicts] == [ConflictKind.DUPLICATE_KEY]
        assert [fact.key for fact in ledger.writable_facts()] == ["管辖"]

    def test_reversed_date_range_conflict(self) -> None:
        material = "合同期限：自 2026 年 5 月 7 日起至 2023 年 12 月 28 日止。"
        ledger = extract_ledger(
            material,
            llm_caller=fake_caller(
                make_fact(
                    "合同期限",
                    "2026 年 5 月 7 日起至 2023 年 12 月 28 日止",
                    "自 2026 年 5 月 7 日起至 2023 年 12 月 28 日止",
                ),
            ),
        )
        assert [conflict.kind for conflict in ledger.conflicts] == [ConflictKind.DATE_RANGE]

    def test_daily_rate_above_half_percent_conflict(self) -> None:
        """D3 的第二处：OCR 把「每日 3‰」读成「每日 3%」（年化 1095%）。"""
        material = "合同 五、逾期付款按每日 3% 计收违约金。"
        ledger = extract_ledger(
            material,
            llm_caller=fake_caller(make_fact("违约金比率", "每日 3%", "按每日 3% 计收违约金")),
        )
        assert [conflict.kind for conflict in ledger.conflicts] == [ConflictKind.DAILY_RATE]

    def test_three_per_mille_is_within_limit(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(make_fact("违约金比率", "每日 3‰", "逾期按每日 3‰ 计收违约金")),
        )
        assert ledger.conflicts == []

    def test_valid_term_range_has_no_conflict(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            llm_caller=fake_caller(
                make_fact(
                    "合同期限",
                    "2023 年 12 月 28 日至 2026 年 5 月 7 日",
                    "本合同期限自 2023 年 12 月 28 日起至 2026 年 5 月 7 日止",
                ),
            ),
        )
        assert ledger.conflicts == []


class TestSoftFailure:
    def test_llm_failure_returns_empty_ledger(self) -> None:
        def exploding_caller(messages: list[dict[str, str]]) -> str:
            raise RuntimeError("模型超时")

        ledger = extract_ledger(MATERIAL_TEXT, llm_caller=exploding_caller)
        assert ledger.facts == []
        # 「调用挂了」与「输出不合 JSON」要能分开：混成一句会让律师去查错方向
        assert any("调用模型失败（RuntimeError）" in warning for warning in ledger.warnings)

    def test_invalid_json_returns_empty_ledger(self) -> None:
        ledger = extract_ledger(MATERIAL_TEXT, llm_caller=lambda messages: "我不会输出 JSON")
        assert ledger.facts == []
        assert any("无法解析" in warning for warning in ledger.warnings)

    def test_missing_facts_field_returns_empty_ledger(self) -> None:
        ledger = extract_ledger(MATERIAL_TEXT, llm_caller=lambda messages: '{"结论": "合同已成立"}')
        assert ledger.facts == []
        assert any("没有从材料里抽到任何事实" in warning for warning in ledger.warnings)


class TestLimit:
    def test_limit_truncates_and_warns(self) -> None:
        ledger = extract_ledger(
            MATERIAL_TEXT,
            limit=2,
            llm_caller=fake_caller(
                make_fact("管辖", "地块所在地人民法院", "由地块所在地人民法院管辖"),
                make_fact("承包金", "384,277 元", "首个承包年度承包金 384,277 元"),
                make_fact("违约金比率", "每日 3‰", "逾期按每日 3‰ 计收违约金"),
            ),
        )
        assert [fact.key for fact in ledger.facts] == ["管辖", "承包金"]
        assert any("上限" in warning for warning in ledger.warnings)

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            extract_ledger(MATERIAL_TEXT, llm_caller=fake_caller(), limit=0)
