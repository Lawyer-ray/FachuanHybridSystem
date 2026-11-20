"""judge 调用：显式超时、最多 2 次、退避换 judge、失败落 unscored。

全部离线：判定调用通过 ``call_judge`` 注入，失败路径（字符串 "true"、末行翻供、
超时、整栏报错）都不联网。``_llm_judge`` 本身只测"传给门面的参数对不对"，
门面用桩替换。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.services.review import judge_client
from apps.agent.services.review.judge_client import JUDGE_MAX_ATTEMPTS, JudgeReply, judge_once, judge_with_retry
from apps.core.llm.exceptions import LLMTimeoutError

_GOOD = '{"criteria_met": true, "explanation": "满足", "evidence_quote": "第 3 条"}'
_FLIP = '{"criteria_met": true, "explanation": "满足"}\nVerdict: false'


def _reply(content: str, model: str = "judge-a") -> JudgeReply:
    return JudgeReply(content=content, model=model, prompt_tokens=10, completion_tokens=5, total_tokens=15)


class _Recorder:
    """记录每次判定调用的模型与 prompt，用来断言"换 judge"和"换 nonce"。"""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, prompt: str, judge_model: str) -> JudgeReply:
        self.calls.append((prompt, judge_model))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """退避是生产行为；单测里置零，避免每次失败真等 0.5s+。"""
    monkeypatch.setattr(judge_client, "_backoff_seconds", lambda attempt: 0.0)


class TestJudgeWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        recorder = _Recorder([_reply(_GOOD)])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is True
        assert outcome.attempts == 1
        assert outcome.judge_model == "judge-a"
        assert outcome.total_tokens == 15
        assert len(recorder.calls) == 1

    @pytest.mark.asyncio
    async def test_parse_failure_retries_with_next_judge_and_new_nonce(self) -> None:
        recorder = _Recorder([_reply(_FLIP, "judge-a"), _reply(_GOOD, "judge-b")])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a", "judge-b"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is True
        assert outcome.attempts == 2
        assert outcome.judge_model == "judge-b"
        assert [model for _, model in recorder.calls] == ["judge-a", "judge-b"]
        assert recorder.calls[0][0] != recorder.calls[1][0], "重试必须换 nonce/新 prompt"

    @pytest.mark.asyncio
    async def test_string_true_is_unscored_never_coerced(self) -> None:
        # DoD ①：judge 返回字符串 "true" → unscored，不折算成 true。
        recorder = _Recorder([_reply('{"criteria_met": "true"}'), _reply('{"criteria_met": "true"}')])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is None
        assert outcome.parsed.unscored_reason == "parse_failed"
        assert outcome.attempts == JUDGE_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_flip_flop_is_parse_failed(self) -> None:
        # DoD ②：末行翻供 → parse_failed。
        recorder = _Recorder([_reply(_FLIP), _reply(_FLIP)])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is None
        assert outcome.parsed.unscored_reason == "parse_failed"

    @pytest.mark.asyncio
    async def test_timeout_then_success(self) -> None:
        recorder = _Recorder([LLMTimeoutError("slow"), _reply(_GOOD)])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a", "judge-b"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is True
        assert outcome.attempts == 2

    @pytest.mark.asyncio
    async def test_all_timeouts_are_unscored_timeout(self) -> None:
        recorder = _Recorder([LLMTimeoutError("slow"), TimeoutError("slow")])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is None
        assert outcome.parsed.unscored_reason == "timeout"
        assert len(recorder.calls) == JUDGE_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_empty_content_is_empty_response(self) -> None:
        recorder = _Recorder([_reply("   "), _reply("")])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["judge-a"],
            call_judge=recorder,
        )

        assert outcome.parsed.criteria_met is None
        assert outcome.parsed.unscored_reason == "empty_response"

    @pytest.mark.asyncio
    async def test_no_judge_models_is_unscored_without_calling(self) -> None:
        recorder = _Recorder([])

        outcome = await judge_with_retry(
            channel="pi",
            task="问题",
            submission="候选",
            criterion="[2] 标准",
            judge_models=["  "],
            call_judge=recorder,
        )

        assert outcome.parsed.unscored_reason == "judge_error"
        assert outcome.attempts == 0
        assert recorder.calls == []


class TestLlmJudgeWiring:
    """``_llm_judge`` 只验"门面参数对不对"，不验模型输出。"""

    @pytest.mark.asyncio
    async def test_passes_explicit_timeout_temperature_and_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        class _FakeResponse:
            content = _GOOD
            model = "judge-real"
            prompt_tokens = 7
            completion_tokens = 3
            total_tokens = 10

        class _FakeService:
            async def achat(self, **kwargs: Any) -> _FakeResponse:
                captured.update(kwargs)
                return _FakeResponse()

        async def _fake_async_service():  # 测试替身：judge 现在走 async 门面

            return _FakeService()

        monkeypatch.setattr(judge_client, "_async_llm_service", _fake_async_service)

        reply = await judge_once(prompt="PROMPT", judge_model="judge-real")

        assert reply.content == _GOOD
        assert reply.total_tokens == 10
        assert captured["model"] == "judge-real"
        assert captured["temperature"] == 0.0
        assert captured["timeout_seconds"] == judge_client.JUDGE_TIMEOUT_SECONDS
        assert captured["caller"] == "agent.review.judge"
        assert captured["messages"] == [{"role": "user", "content": "PROMPT"}]
