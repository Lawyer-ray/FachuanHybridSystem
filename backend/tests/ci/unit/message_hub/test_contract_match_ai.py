"""AI 兜底匹配（``contract_match_ai``）的纯函数测试。

锁定的核心行为——都是「兜底不能弄坏主流程」的边界：

1. **防幻觉**：模型返回的 contract_id 不在候选清单里就丢弃，
   哪怕它看起来很合理。否则前端会显示一个不存在的项目。
2. **失败静默降级**：模型抛错/超时/返回非 JSON → 空列表，不向上抛。
   到账认领是账务流程，不能依赖外部服务可用。
3. **只在规则无确定答案时触发**：有 exact 候选时不调模型
   （见 ``contract_match_v2.suggest_contracts_for_transfer`` 的 ``ai_fallback_used``）。
4. AI 候选恒排在规则候选之后，且 kind 独立为 ``ai_suggested``。
"""

from __future__ import annotations

from decimal import Decimal

from apps.message_hub.services.contract_match_ai import (
    KIND_AI_SUGGESTED,
    SCORE_AI,
    _coerce_confidence,
    _parse_matches,
    suggest_with_ai,
)
from apps.message_hub.services.transfer_notice import TransferNotice

_POOL = [
    {"contract_id": 372, "contract_name": "甲方公司劳动合同纠纷", "outstanding_amount": "9000.00", "fee_mode": "FIXED"},
    {"contract_id": 260, "contract_name": "乙方照明确认劳动关系", "outstanding_amount": "9000.00", "fee_mode": "FIXED"},
]


def _notice(amount="9000", payer="某律师", on_behalf="甲方公司"):
    n = TransferNotice(
        amount=Decimal(amount) if amount else None,
        payer_name=payer,
        on_behalf_of=on_behalf,
    )
    return n


def _stub(response: str):
    def _fn(*, prompt: str, system_prompt: str) -> str:
        return response

    return _fn


class TestParseMatches:
    def test_plain_json(self):
        assert len(_parse_matches('{"matches": [{"contract_id": 1}]}')) == 1

    def test_json_wrapped_in_prose(self):
        """模型常把 JSON 包在解释文字里，要能抠出来。"""
        raw = '好的，判断如下：\n{"matches": [{"contract_id": 372, "confidence": 0.9}]}\n以上。'
        matches = _parse_matches(raw)
        assert matches and matches[0]["contract_id"] == 372

    def test_invalid_json_returns_empty(self):
        assert _parse_matches("我觉得应该是 372 号项目") == []

    def test_empty(self):
        assert _parse_matches("") == []

    def test_missing_matches_key(self):
        assert _parse_matches('{"foo": 1}') == []


class TestCoerceConfidence:
    def test_percent_becomes_fraction(self):
        assert _coerce_confidence(85) == 0.85

    def test_string_number(self):
        assert _coerce_confidence("0.8") == 0.8

    def test_clamped(self):
        assert _coerce_confidence(5) == 0.05
        assert _coerce_confidence("high") == 0.0


class TestSuggestWithAi:
    def test_normal_suggestion(self):
        results = suggest_with_ai(
            notice=_notice(),
            mail_text="（甲方公司支付律师费）",
            candidates=_POOL,
            complete_fn=_stub('{"matches": [{"contract_id": 372, "confidence": 0.9, "reason": "括号写明甲方"}]}'),
        )
        assert len(results) == 1
        assert results[0]["contract_id"] == 372
        assert results[0]["kind"] == KIND_AI_SUGGESTED
        assert results[0]["score"] == SCORE_AI * 0.9
        assert "甲方" in results[0]["reasons"][0]

    def test_hallucinated_id_is_dropped(self):
        """核心安全边界：模型编造的合同号不能流到前端。"""
        results = suggest_with_ai(
            notice=_notice(),
            mail_text="x",
            candidates=_POOL,
            complete_fn=_stub('{"matches": [{"contract_id": 999, "confidence": 0.99}]}'),
        )
        assert results == []

    def test_mixed_real_and_fake_keeps_only_real(self):
        results = suggest_with_ai(
            notice=_notice(),
            mail_text="x",
            candidates=_POOL,
            complete_fn=_stub(
                '{"matches": [{"contract_id": 999, "confidence": 0.9}, {"contract_id": 260, "confidence": 0.5}]}'
            ),
        )
        assert [r["contract_id"] for r in results] == [260]

    def test_llm_exception_degrades_silently(self):
        """模型炸了不能把到账认领流程带崩。"""

        def _boom(*, prompt: str, system_prompt: str) -> str:
            raise RuntimeError("provider down")

        assert suggest_with_ai(notice=_notice(), mail_text="x", candidates=_POOL, complete_fn=_boom) == []

    def test_no_candidates_skips_llm(self):
        called = []

        def _fn(*, prompt: str, system_prompt: str) -> str:
            called.append(1)
            return '{"matches": []}'

        assert suggest_with_ai(notice=_notice(), mail_text="x", candidates=[], complete_fn=_fn) == []
        assert called == [], "无候选时不该调用模型"

    def test_empty_matches(self):
        assert (
            suggest_with_ai(notice=_notice(), mail_text="x", candidates=_POOL, complete_fn=_stub('{"matches": []}'))
            == []
        )

    def test_results_sorted_by_confidence(self):
        results = suggest_with_ai(
            notice=_notice(),
            mail_text="x",
            candidates=_POOL,
            complete_fn=_stub(
                '{"matches": [{"contract_id": 260, "confidence": 0.3}, {"contract_id": 372, "confidence": 0.9}]}'
            ),
        )
        assert [r["contract_id"] for r in results] == [372, 260]

    def test_caveat_marks_it_as_ai_judgement(self):
        results = suggest_with_ai(
            notice=_notice(),
            mail_text="x",
            candidates=_POOL,
            complete_fn=_stub('{"matches": [{"contract_id": 372, "confidence": 0.8}]}'),
        )
        assert "AI" in results[0]["caveat"]
