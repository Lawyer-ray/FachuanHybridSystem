"""jury 编排：失败票不进 valid、多数门槛、全局并发闸门。

DoD ③：某栏整栏报错 → 该栏 ``valid == 0`` 且 ``score is None``；**不能**把
失败票折算成"答错"，也不能让整次评审跟着失败。全部离线：判定调用走注入的
``call_judge``。
"""

from __future__ import annotations

import asyncio

import pytest

from apps.agent.services.review import jury
from apps.agent.services.review.judge_client import JudgeReply
from apps.agent.services.review.rubric import DEFAULT_RUBRIC_ID, RubricItem, load_rubric

_ITEMS = [
    RubricItem(id="a", criterion="加分 A", points=2),
    RubricItem(id="b", criterion="加分 B", points=2),
    RubricItem(id="neg", criterion="负分 不该发生", points=-1),
]


class _ScriptedJudge:
    """按 prompt 内容决定判定；``bad`` 栏整栏抛错。"""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.called_channels: list[str] = []

    async def __call__(self, prompt: str, judge_model: str) -> JudgeReply:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            for channel in ("bad", "mixed", "good"):
                if f"[BEGIN {channel} (" in prompt:
                    self.called_channels.append(channel)
                    break
            if "[BEGIN bad (" in prompt:
                raise RuntimeError("judge down")
            # 只认 rubric 条件本身（prompt 的规则文本里也有"负分"二字，不能拿它当判据）。
            met = not ("[BEGIN mixed (" in prompt and "加分 B" in prompt) and "负分 不该发生" not in prompt
            return JudgeReply(
                content=f'{{"criteria_met": {str(met).lower()}, "explanation": "ok", "evidence_quote": "q"}}',
                model=judge_model,
            )
        finally:
            self.active -= 1


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("apps.agent.services.review.judge_client._backoff_seconds", lambda attempt: 0.0)


class TestRunJury:
    @pytest.mark.asyncio
    async def test_failed_lane_does_not_enter_valid_and_is_none_not_zero(self) -> None:
        judge = _ScriptedJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers={"good": "回答", "bad": "回答"},
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        lanes = {lane.lane: lane for lane in review.lanes}
        assert lanes["good"].valid == 3
        assert lanes["good"].score == pytest.approx(1.0)
        assert lanes["bad"].valid == 0
        assert lanes["bad"].score is None, "整栏报错必须是 None，不是 0 分"
        assert all(v.criteria_met is None for v in review.verdicts if v.lane == "bad")
        assert all(v.unscored_reason == "judge_error" for v in review.verdicts if v.lane == "bad")

    @pytest.mark.asyncio
    async def test_majority_threshold_is_strict(self) -> None:
        judge = _ScriptedJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers={"mixed": "回答"},
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        lane = review.lanes[0]
        # a=true / b=false / neg=false → 2 张有利票、3 条有效 → 4 > 3 通过。
        assert (lane.yes, lane.valid) == (2, 3)
        assert "多数通过" in review.headline

    @pytest.mark.asyncio
    async def test_missing_answer_lane_skips_judge_and_is_unscored(self) -> None:
        judge = _ScriptedJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers={"good": "回答", "empty": "   "},
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        lanes = {lane.lane: lane for lane in review.lanes}
        assert lanes["empty"].valid == 0
        assert lanes["empty"].score is None
        assert judge.calls == len(_ITEMS), "空栏不该产生 judge 调用"
        assert all(v.unscored_reason == "empty_response" for v in review.verdicts if v.lane == "empty")

    @pytest.mark.asyncio
    async def test_review_contract_shape_and_tokens(self) -> None:
        judge = _ScriptedJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=2,
            task="问题",
            answers={"good": "回答"},
            rubric=load_rubric(DEFAULT_RUBRIC_ID),
            judge_models=["judge-a"],
            call_judge=judge,
        )

        assert review.stage == "shadow"
        assert review.turn == 2
        assert len(review.lanes) == 1
        assert len(review.verdicts) == 7
        assert review.tokens == {"prompt": 0, "completion": 0, "total": 0}
        assert review.headline


class TestGlobalSemaphore:
    @pytest.mark.asyncio
    async def test_concurrent_judge_calls_are_capped(self) -> None:
        judge = _ScriptedJudge(delay=0.01)
        answers = {f"lane-{index}": "回答" for index in range(3)}

        await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers=answers,
            rubric=load_rubric(DEFAULT_RUBRIC_ID),
            judge_models=["judge-a"],
            call_judge=judge,
        )

        assert jury.JUDGE_CONCURRENCY == 8
        assert judge.max_active <= jury.JUDGE_CONCURRENCY
        assert judge.max_active > 1, "闸门不应把并发压成串行"
