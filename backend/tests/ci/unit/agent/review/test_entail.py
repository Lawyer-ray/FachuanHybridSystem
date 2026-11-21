"""判等实现：三态（true/false/判不了）、超时、垃圾 JSON、重试换模型、闸门与阶段 deadline。

全部离线：judge 调用走注入的 ``call_judge``。重点是**判不了绝不被折算成 True**——
那会把"没判出来"说成"这几家一致"，是法律场景里最贵的一种错。
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from apps.agent.services.chat.equivalence import EntailsFn, cluster_answers
from apps.agent.services.review import entail, judge_client
from apps.agent.services.review.judge_client import JudgeReply

_EQUIVALENT = '{"entails": true, "why": "同一条修改意见"}'
_DIFFERENT = '{"entails": false, "why": "金额口径不同"}'
_UNKNOWN = '{"entails": null, "why": "第二段没有结论"}'
_GARBAGE = "我觉得这两段差不多吧"


class _ScriptedJudge:
    """按注入的回答表逐次返回；记录调用次数、模型顺序与并发峰值。"""

    def __init__(self, *contents: str, delay: float = 0.0, error: BaseException | None = None) -> None:
        self.contents = list(contents) or [_EQUIVALENT]
        self.delay = delay
        self.error = error
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.models: list[str] = []

    async def __call__(self, prompt: str, judge_model: str) -> JudgeReply:
        self.calls += 1
        self.models.append(judge_model)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return JudgeReply(content=self.contents[min(self.calls, len(self.contents)) - 1], model=judge_model)
        finally:
            self.active -= 1


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试的退避在测试里归零（公式本身由 judge_client 自己的测试守）。"""
    monkeypatch.setattr(judge_client, "_backoff_seconds", lambda attempt: 0.0)


def _as_entails_fn(entails: entail.SyncEntails) -> EntailsFn:
    """显式 cast：``EntailsFn`` 声明 ``-> bool``，而判不了是 ``None``（见 entail 模块说明）。"""
    return cast(EntailsFn, entails)


class TestParseEntails:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (_EQUIVALENT, True),
            (_DIFFERENT, False),
            (_UNKNOWN, None),
            ('```json\n{"entails": true, "why": "同"}\n```', True),
            # 协议偏离：字符串/数字都不折算成布尔，只能"判不了"。
            ('{"entails": "true"}', None),
            ('{"entails": 1}', None),
            ('{"why": "忘了给结论"}', None),
            (_GARBAGE, None),
            ("", None),
            ("   ", None),
        ],
    )
    def test_only_json_bool_survives(self, text: str, expected: bool | None) -> None:
        assert entail.parse_entails(text) is expected


class TestClusterWithEntails:
    @pytest.mark.asyncio
    async def test_equivalent_answers_form_one_cluster(self) -> None:
        judge = _ScriptedJudge(_EQUIVALENT)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh", "openai-agents"])
        clusters = cluster_answers(["pi", "dsh", "openai-agents"], _as_entails_fn(entails))

        assert [(cluster.member_ids, cluster.representative_id, cluster.tie) for cluster in clusters] == [
            (("pi", "dsh", "openai-agents"), "pi", False)
        ]
        # 3 栏 = C(3,2) × 2 方向 = 6 次调用；契约 §C3 的成本口径。
        assert entails.calls == 6
        assert judge.calls == 6
        assert entails.failed == 0

    @pytest.mark.asyncio
    async def test_different_answers_stay_separate_with_tie(self) -> None:
        judge = _ScriptedJudge(_DIFFERENT)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh", "openai-agents"])
        clusters = cluster_answers(["pi", "dsh", "openai-agents"], _as_entails_fn(entails))

        assert [cluster.member_ids for cluster in clusters] == [("pi",), ("dsh",), ("openai-agents",)]
        # 真全异：tie 且没有代表（不回落成第一条）。
        assert all(cluster.tie for cluster in clusters)
        assert all(cluster.representative_id == "" for cluster in clusters)
        assert entails.failed == 0, "判得出来（只是结论为 false）就不算失败"

    @pytest.mark.asyncio
    async def test_garbage_reply_is_unknown_and_never_true(self) -> None:
        judge = _ScriptedJudge(_GARBAGE)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])
        clusters = cluster_answers(["pi", "dsh"], _as_entails_fn(entails))

        assert [cluster.member_ids for cluster in clusters] == [("pi",), ("dsh",)]
        assert entails.calls == 2
        assert entails.failed == 2
        assert entails.reasons == {"parse_failed": 2}
        # 每个方向重试 1 次（共 2 次尝试）。
        assert judge.calls == 4

    @pytest.mark.asyncio
    async def test_null_reply_is_unknown(self) -> None:
        judge = _ScriptedJudge(_UNKNOWN)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])

        assert entails.failed == 2
        assert entails.reasons == {"parse_failed": 2}

    @pytest.mark.asyncio
    async def test_empty_reply_is_unknown(self) -> None:
        judge = _ScriptedJudge("   ")
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])

        assert entails.failed == 2
        assert entails.reasons == {"empty_response": 2}

    @pytest.mark.asyncio
    async def test_timeout_is_unknown_and_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(entail, "ENTAIL_TIMEOUT_SECONDS", 0.02)
        judge = _ScriptedJudge(_EQUIVALENT, delay=0.5)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])

        assert entails.failed == 2
        assert entails.reasons == {"timeout": 2}
        assert judge.calls == 4, "超时也要重试一次（上限 2 次），不能无限重试"

    @pytest.mark.asyncio
    async def test_retry_swaps_judge_model(self) -> None:
        # 单个方向（不起并发）：第一次判不了 → 换下一个 judge 重试 → 判成立。
        judge = _ScriptedJudge(_GARBAGE, _EQUIVALENT)

        verdict, reason = await entail._entail_direction(
            first="甲 结论：该条款无效",
            second="乙 结论：该条款应认定无效",
            models=["judge-a", "judge-b"],
            call_judge=judge,
            timeout=5.0,
        )

        assert (verdict, reason) == (True, "")
        assert judge.models == ["judge-a", "judge-b"]

    @pytest.mark.asyncio
    async def test_stage_deadline_skips_every_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(entail, "ENTAIL_STAGE_DEADLINE_SECONDS", 0.0)
        judge = _ScriptedJudge(_EQUIVALENT)
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])

        assert judge.calls == 0, "deadline 过线后一次调用都不该发起"
        assert entails.failed == 2
        assert entails.reasons == {"timeout": 2}

    @pytest.mark.asyncio
    async def test_no_judge_models_judges_nothing(self) -> None:
        judge = _ScriptedJudge(_EQUIVALENT)
        entails = entail.make_entails([], call_judge=judge)

        await entails.prefetch(["pi", "dsh"])

        assert judge.calls == 0
        assert entails.failed == 2
        assert entails.reasons == {"judge_error": 2}

    @pytest.mark.asyncio
    async def test_unexpected_error_is_not_swallowed(self) -> None:
        judge = _ScriptedJudge(_EQUIVALENT, error=TypeError("我们自己的 bug"))
        entails = entail.make_entails(["judge-a"], call_judge=judge)

        with pytest.raises(TypeError):
            await entails.prefetch(["pi", "dsh"])


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrency_is_capped(self) -> None:
        judge = _ScriptedJudge(_EQUIVALENT, delay=0.01)
        entails = entail.make_entails(["judge-a"], call_judge=judge)
        lanes = [f"lane-{index}" for index in range(5)]

        await entails.prefetch(lanes)

        assert entail.ENTAIL_CONCURRENCY == 4
        assert judge.max_active <= entail.ENTAIL_CONCURRENCY
        assert judge.max_active > 1, "预取必须真并发，不是一个个排队"
        assert entails.calls == 5 * 4 // 2 * 2, "5 栏 = C(5,2) × 2 = 20 个方向"
