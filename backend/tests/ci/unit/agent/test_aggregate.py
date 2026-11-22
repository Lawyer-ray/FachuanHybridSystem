"""``services/chat/aggregate.py``：综合结论的候选装配（纯函数）。

本文件钉的是三件会让律师被误导的事：

1. **候选必须带来源头**：没有 ``【栏名 · 模型】`` 的候选无法在正文里标
   ``[来源：栏名]``，结论就退化成"不知道谁说的"（MoA 原版的坑，见模块 docstring）；
2. **空 / 失败候选不进 prompt**：空答案被编号进去，聚合者会"参考"一段沉默，
   而律师看到的结论里会多出一份根本不存在的论据；
3. **不截断、不按长度丢弃**：截了不标注，聚合者会以为自己看的是全文。

调用模型、重试与正文校验在 ``services/synthesis/agent_runner``（见其测试）。
全部离线：不联网也不建库。
"""

from __future__ import annotations

import pytest

from apps.agent.services.chat import aggregate
from apps.agent.services.chat.aggregate import (
    AGGREGATE_SYSTEM_PROMPT,
    MAX_CANDIDATES,
    Candidate,
    extract_citations,
    partition_candidates,
    render_candidate,
)

_STATUTE = "依据《民法典》第五百八十四条，损失赔偿额应当相当于因违约造成的损失。"
# 引用串形状与真实案号一致（citing 正则要能抓到），但内容是虚构的。
_CASE_QUOTE = "（2023）京0105民初1234号"  # privacy-allow 虚构案号
_CASE_NO = f"参考{_CASE_QUOTE}，法院支持了违约金调整。"


class TestRenderCandidate:
    def test_candidate_carries_index_lane_and_model_header(self) -> None:
        rendered = render_candidate(2, Candidate(lane="dsh", model="glm53", text=_CASE_NO))

        assert rendered.startswith("2. 【dsh · glm53】\n")
        assert rendered.endswith(_CASE_NO)

    def test_model_missing_never_guesses_a_model_name(self) -> None:
        rendered = render_candidate(1, Candidate(lane="pi", model="", text=_STATUTE))

        assert f"【pi · {aggregate.UNKNOWN_MODEL_LABEL}】" in rendered

    def test_long_candidate_goes_in_whole(self) -> None:
        """长候选**原样**进 prompt：截断的唯一后果是聚合者读不到后文论证。"""
        long_text = "甲" * 50_000
        rendered = render_candidate(1, Candidate(lane="pi", model="kimi-2.6", text=long_text))

        assert "甲" * 50_000 in rendered
        assert "已截断" not in rendered

    def test_system_prompt_demands_source_anchors(self) -> None:
        """来源锚点是契约 §C4 的形状（``[来源：栏名]``），不能被改成别的写法。"""
        assert "[来源：栏名]" in AGGREGATE_SYSTEM_PROMPT
        assert aggregate.ANCHOR_MARKER in AGGREGATE_SYSTEM_PROMPT


class TestPartitionCandidates:
    def test_empty_candidate_is_dropped_as_empty(self) -> None:
        used, dropped = partition_candidates(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="dsh", model="glm53", text="   \n"),
            ]
        )

        assert [candidate.lane for candidate in used] == ["pi"]
        assert [(item.lane, item.reason) for item in dropped] == [("dsh", "empty")]

    def test_failed_lane_is_dropped_as_failed(self) -> None:
        """``text=None`` = 该栏本轮没落库正文（跑了但失败），与"空回答"不是一回事。"""
        _used, dropped = partition_candidates(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="openai-agents", model="glm53", text=None),
            ]
        )

        assert [(item.lane, item.reason) for item in dropped] == [("openai-agents", "failed")]

    def test_absurdly_long_candidate_is_kept_not_dropped(self) -> None:
        """不按长度整栏丢弃：丢了会让 ``lanes_used`` 说假话。"""
        used, dropped = partition_candidates(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="dsh", model="glm53", text="乙" * 300_000),
            ]
        )

        assert [candidate.lane for candidate in used] == ["pi", "dsh"]
        assert dropped == []

    def test_order_is_request_order(self) -> None:
        used, dropped = partition_candidates(
            [
                Candidate(lane="dsh", model="glm53", text=_CASE_NO),
                Candidate(lane="pi", model="kimi-2.6", text=None),
                Candidate(lane="antigravity", model="glm53", text=_STATUTE),
            ]
        )

        assert [candidate.lane for candidate in used] == ["dsh", "antigravity"]
        assert [item.lane for item in dropped] == ["pi"]

    def test_more_candidates_than_cap_is_rejected_not_silently_dropped(self) -> None:
        candidates = [Candidate(lane=f"lane{index}", model="m", text=_STATUTE) for index in range(MAX_CANDIDATES + 1)]

        with pytest.raises(ValueError, match="一次最多综合"):
            partition_candidates(candidates)


class TestExtractCitations:
    def test_citations_are_recorded_per_lane(self) -> None:
        """引用锚点从各栏原文抽：法条按栏记、案号按栏记，不合并到"某栏"。"""
        citations = extract_citations(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="dsh", model="glm53", text=_CASE_NO),
            ]
        )

        assert [(item.lane, item.quote) for item in citations] == [
            ("pi", "《民法典》第五百八十四条"),
            ("dsh", _CASE_QUOTE),
        ]

    def test_same_quote_in_two_lanes_is_kept_twice_but_deduped_within_lane(self) -> None:
        citations = extract_citations(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE + _STATUTE),
                Candidate(lane="dsh", model="glm53", text=_STATUTE),
            ]
        )

        assert [(item.lane, item.quote) for item in citations] == [
            ("pi", "《民法典》第五百八十四条"),
            ("dsh", "《民法典》第五百八十四条"),
        ]


class TestRemovedBareLLMPath:
    """裸 LLM 综合路径（``synthesize`` / ``_llm_aggregate``）已删除：综合只走 agent 运行时。

    留着它等于留一条没人调用、却仍被测试"证明可用"的第二实现，口径迟早分叉。
    """

    @pytest.mark.parametrize(
        "name",
        [
            "synthesize",
            "_llm_aggregate",
            "call_once",
            "build_aggregate_messages",
            "validate_reply",
            "strip_code_fences",
            "SynthesisReply",
            "SYNTHESIS_MAX_TOKENS",
        ],
    )
    def test_bare_llm_symbols_are_gone(self, name: str) -> None:
        assert not hasattr(aggregate, name)
        assert name not in aggregate.__all__
