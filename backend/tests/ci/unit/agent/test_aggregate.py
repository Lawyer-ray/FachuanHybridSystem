"""``services/chat/aggregate.py``：综合结论的 prompt 装配与一次可注入的调用。

本文件钉的是四件会让律师被误导的事：

1. **候选必须带来源头**：没有 ``【栏名 · 模型】`` 的候选无法在正文里标
   ``[来源：栏名]``，结论就退化成"不知道谁说的"（MoA 原版的坑，见模块 docstring）；
2. **空 / 失败候选不进 prompt**：空答案被编号进去，聚合者会"参考"一段沉默，
   而律师看到的结论里会多出一份根本不存在的论据；
3. **超长必须截断 + 明说截断**（超过硬上限则整栏丢弃报 ``too_long``）：截了不标注，
   聚合者会以为自己看的是全文；
4. **调用失败最多两次、第二次换温度**：无限重试会把"模型抽风"变成账单失控。

全部离线：合成调用通过 ``call_model`` 注入，退避被置零，不联网也不建库。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from apps.agent.services.chat import aggregate
from apps.agent.services.chat.aggregate import (
    AGGREGATE_SYSTEM_PROMPT,
    MAX_CANDIDATES,
    STRICT_RETRY_SUFFIX,
    SYNTHESIS_MAX_ATTEMPTS,
    SYNTHESIS_MAX_TOKENS,
    SYNTHESIS_RETRY_TEMPERATURE,
    SYNTHESIS_TEMPERATURE,
    Candidate,
    SynthesisReply,
    build_aggregate_messages,
    partition_candidates,
    strip_code_fences,
    synthesize,
    validate_reply,
)
from apps.core.llm.exceptions import LLMError

_TASK = "对方逾期付款，我方能否主张解除合同并要求违约金？"

_STATUTE = "依据《民法典》第五百八十四条，损失赔偿额应当相当于因违约造成的损失。"
# 引用串形状与真实案号一致（citing 正则要能抓到），但内容是虚构的。
_CASE_QUOTE = "（2023）京0105民初1234号"  # privacy-allow 虚构案号
_CASE_NO = f"参考{_CASE_QUOTE}，法院支持了违约金调整。"


def _reply(content: str = "综合后的结论 [来源：pi]", model: str = "judge-x") -> SynthesisReply:
    return SynthesisReply(content=content, model=model, prompt_tokens=11, completion_tokens=7, total_tokens=18)


class _Recorder:
    """记录每次调用的 messages / model / temperature，按脚本返回或抛错。"""

    def __init__(self, script: Sequence[SynthesisReply | BaseException]) -> None:
        self.script = list(script)
        self.calls: list[tuple[list[dict[str, str]], str, float]] = []

    async def __call__(self, messages: list[dict[str, str]], model: str, temperature: float) -> SynthesisReply:
        self.calls.append((messages, model, temperature))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """退避是生产行为；单测里置零，避免每次失败真等 0.5s+。"""
    monkeypatch.setattr(aggregate, "_backoff_seconds", lambda attempt: 0.0)


def _user_content(messages: list[dict[str, str]]) -> str:
    return messages[1]["content"]


class TestBuildAggregateMessages:
    def test_each_candidate_carries_lane_and_model_header(self) -> None:
        messages = build_aggregate_messages(
            _TASK,
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="dsh", model="glm53", text=_CASE_NO),
            ],
        )

        assert messages[0] == {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT}
        content = _user_content(messages)
        assert "【pi · kimi-2.6】" in content
        assert "【dsh · glm53】" in content
        # 序号是"进 prompt 之后的序号"，从 1 开始连续
        assert "1. 【pi · kimi-2.6】" in content
        assert "2. 【dsh · glm53】" in content

    def test_model_missing_never_guesses_a_model_name(self) -> None:
        messages = build_aggregate_messages(_TASK, [Candidate(lane="pi", model="", text=_STATUTE)])

        assert f"【pi · {aggregate.UNKNOWN_MODEL_LABEL}】" in _user_content(messages)

    def test_system_prompt_demands_source_anchors(self) -> None:
        """来源锚点是契约 §C4 的形状（``[来源：栏名]``），不能被改成别的写法。"""
        assert "[来源：栏名]" in AGGREGATE_SYSTEM_PROMPT

    def test_empty_candidate_is_dropped_and_absent_from_prompt(self) -> None:
        candidates = [
            Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
            Candidate(lane="dsh", model="glm53", text="   \n"),
        ]
        used, dropped = partition_candidates(candidates)

        assert [candidate.lane for candidate in used] == ["pi"]
        assert [(item.lane, item.reason) for item in dropped] == [("dsh", "empty")]

        content = _user_content(build_aggregate_messages(_TASK, candidates))
        assert "【pi · kimi-2.6】" in content
        assert "dsh" not in content
        assert "glm53" not in content

    def test_failed_lane_is_dropped_as_failed(self) -> None:
        """``text=None`` = 该栏本轮没落库正文（跑了但失败），与"空回答"不是一回事。"""
        _used, dropped = partition_candidates(
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="openai-agents", model="glm53", text=None),
            ]
        )

        assert [(item.lane, item.reason) for item in dropped] == [("openai-agents", "failed")]

    def test_long_candidate_goes_in_whole(self) -> None:
        """长候选**原样**进 prompt（2026-11-22 起不截断）。

        截断的唯一后果是聚合者读不到后文论证，却仍然写出一段看似完整的结论——
        静默降级比报错危险。上限交给模型上下文窗口，超了网关会 400。
        """
        long_text = "甲" * 50_000
        messages = build_aggregate_messages(_TASK, [Candidate(lane="pi", model="kimi-2.6", text=long_text)])

        content = _user_content(messages)
        assert "甲" * 50_000 in content
        assert "已截断" not in content

    def test_absurdly_long_candidate_is_kept_not_dropped(self) -> None:
        """曾经的 2.4 万字硬上限已取消：整栏丢弃会让 `lanes_used` 说假话。"""
        huge = "乙" * 300_000
        candidates = [
            Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
            Candidate(lane="dsh", model="glm53", text=huge),
        ]
        used, dropped = partition_candidates(candidates)

        assert [candidate.lane for candidate in used] == ["pi", "dsh"]
        assert dropped == []
        content = _user_content(build_aggregate_messages(_TASK, candidates))
        assert "乙" * 1000 in content
        assert "2. 【dsh · glm53】" in content

    def test_no_usable_candidate_raises_instead_of_calling_model_with_empty_prompt(self) -> None:
        with pytest.raises(ValueError, match="没有可综合的候选"):
            build_aggregate_messages(_TASK, [Candidate(lane="pi", model="kimi-2.6", text="")])

    def test_more_candidates_than_cap_is_rejected_not_silently_dropped(self) -> None:
        candidates = [Candidate(lane=f"lane{index}", model="m", text=_STATUTE) for index in range(MAX_CANDIDATES + 1)]

        with pytest.raises(ValueError, match="一次最多综合"):
            partition_candidates(candidates)


class TestSynthesize:
    @pytest.mark.asyncio
    async def test_returns_synthesis_with_lanes_dropped_and_citations(self) -> None:
        recorder = _Recorder([_reply()])

        synthesis = await synthesize(
            _TASK,
            [
                Candidate(lane="pi", model="kimi-2.6", text=_STATUTE),
                Candidate(lane="dsh", model="glm53", text=_CASE_NO),
                Candidate(lane="openai-agents", model="glm53", text=None),
            ],
            model="judge-x",
            call_model=recorder,
        )

        assert synthesis.text == "综合后的结论 [来源：pi]"
        assert synthesis.model == "judge-x"
        # lanes_used 与 dropped 互斥且并集 = 请求的栏
        assert synthesis.lanes_used == ["pi", "dsh"]
        assert [(item.lane, item.reason) for item in synthesis.dropped] == [("openai-agents", "failed")]
        # 引用锚点从各栏原文抽：法条按栏记、案号按栏记，不合并到"某栏"
        assert [(item.lane, item.quote) for item in synthesis.citations] == [
            ("pi", "《民法典》第五百八十四条"),
            ("dsh", _CASE_QUOTE),
        ]
        assert synthesis.tokens == {"prompt": 11, "completion": 7, "total": 18}
        assert len(synthesis.synthesis_id) == 32

    @pytest.mark.asyncio
    async def test_code_fences_are_stripped_from_text(self) -> None:
        recorder = _Recorder([_reply(content="```markdown\n结论正文 [来源：pi]\n```")])

        synthesis = await synthesize(
            _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
        )

        assert synthesis.text == "结论正文 [来源：pi]"

    @pytest.mark.asyncio
    async def test_all_candidates_unusable_skips_the_model_call(self) -> None:
        recorder = _Recorder([])

        synthesis = await synthesize(
            _TASK,
            [
                Candidate(lane="pi", model="kimi-2.6", text=None),
                Candidate(lane="dsh", model="glm53", text=""),
            ],
            model="judge-x",
            call_model=recorder,
        )

        assert recorder.calls == []
        assert synthesis.text == ""
        assert synthesis.lanes_used == []
        assert [(item.lane, item.reason) for item in synthesis.dropped] == [("pi", "failed"), ("dsh", "empty")]

    @pytest.mark.asyncio
    async def test_retry_switches_temperature_then_raises_after_cap(self) -> None:
        recorder = _Recorder([LLMError("上游 502"), LLMError("上游又 502")])

        with pytest.raises(LLMError):
            await synthesize(
                _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
            )

        assert len(recorder.calls) == SYNTHESIS_MAX_ATTEMPTS
        assert [temperature for _, _, temperature in recorder.calls] == [
            SYNTHESIS_TEMPERATURE,
            SYNTHESIS_RETRY_TEMPERATURE,
        ]

    @pytest.mark.asyncio
    async def test_second_attempt_success_is_returned(self) -> None:
        recorder = _Recorder([LLMError("上游 502"), _reply(content="第二次成功 [来源：pi]")])

        synthesis = await synthesize(
            _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
        )

        assert synthesis.text == "第二次成功 [来源：pi]"
        assert len(recorder.calls) == 2

    @pytest.mark.asyncio
    async def test_empty_reply_is_treated_as_failure_and_retried(self) -> None:
        """空正文不能当成结论落库：转成重试，两次都空就抛错。"""
        recorder = _Recorder([_reply(content="   "), _reply(content="```\n```")])

        with pytest.raises(LLMError, match="综合结论为空"):
            await synthesize(
                _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
            )

        assert len(recorder.calls) == 2


class TestStripCodeFences:
    @pytest.mark.parametrize(
        "raw",
        ["```\n正文\n```", "```markdown\n正文\n```", "  ```python\n正文\n```  "],
    )
    def test_wrapped_content_is_unwrapped(self, raw: str) -> None:
        assert strip_code_fences(raw) == "正文"

    def test_plain_content_is_kept(self) -> None:
        assert strip_code_fences("  正文 [来源：pi]  ") == "正文 [来源：pi]"


class TestOutputGates:
    """真机缺陷回归：推理型模型把思考过程当正文吐出来。

    真跑（2026-11-21，kimi-2.6）拿到的正文是「我们需要回答用户问题……需要综合三份
    候选……」，并且 ``completion_tokens == 2048 == SYNTHESIS_MAX_TOKENS``——输出预算
    被思考过程吃光，正文停在半句上。这两条闸门就是为它加的。
    """

    @pytest.mark.parametrize(
        ("text", "completion", "expected"),
        [
            ("结论 [来源：pi]", 100, ""),
            ("我们需要回答用户问题", 100, "no_anchor"),
            ("结论 [来源：pi]", SYNTHESIS_MAX_TOKENS, "truncated"),
            ("结论 [来源：pi]", SYNTHESIS_MAX_TOKENS + 50, "truncated"),
        ],
    )
    def test_validate_reply(self, text: str, completion: int, expected: str) -> None:
        assert validate_reply(text, completion) == expected

    @pytest.mark.asyncio
    async def test_reasoning_leak_is_retried_with_stricter_instruction(self) -> None:
        """第一次吐思考过程（无锚点）→ 重试时 system 追加加强语 → 第二次合格。"""
        recorder = _Recorder(
            [
                _reply(content="我们需要回答用户问题。先看三份候选分别说了什么。"),
                _reply(content="结论正文 [来源：pi、dsh]"),
            ]
        )

        synthesis = await synthesize(
            _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
        )

        assert synthesis.text == "结论正文 [来源：pi、dsh]"
        assert len(recorder.calls) == 2
        # 第一次没加强语，第二次有——加强语只在失败之后才追加
        first_system = recorder.calls[0][0][0]["content"]
        second_system = recorder.calls[1][0][0]["content"]
        assert STRICT_RETRY_SUFFIX not in first_system
        assert STRICT_RETRY_SUFFIX in second_system
        # 两次都只改温度，不动候选正文
        assert recorder.calls[0][0][1]["content"] == recorder.calls[1][0][1]["content"]

    @pytest.mark.asyncio
    async def test_truncated_output_never_becomes_the_answer(self) -> None:
        """顶到输出上限 = 没写完：两次都截断就报错，绝不当结论返回。"""
        truncated = SynthesisReply(
            content="综合结论写到一半 [来源：pi]",
            model="judge-x",
            prompt_tokens=10,
            completion_tokens=SYNTHESIS_MAX_TOKENS,
            total_tokens=10 + SYNTHESIS_MAX_TOKENS,
        )
        recorder = _Recorder([truncated, truncated])

        with pytest.raises(LLMError, match="被截断"):
            await synthesize(
                _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
            )

        assert len(recorder.calls) == 2

    @pytest.mark.asyncio
    async def test_single_reasoning_leak_fails_with_anchor_message(self) -> None:
        """两次都缺锚点 → 报错文案点明「疑似思考过程」，律师不会拿到一段自我对话。"""
        recorder = _Recorder([_reply(content="我们需要回答用户问题"), _reply(content="我们需要再想想")])

        with pytest.raises(LLMError, match="来源锚点"):
            await synthesize(
                _TASK, [Candidate(lane="pi", model="kimi-2.6", text=_STATUTE)], model="judge-x", call_model=recorder
            )
