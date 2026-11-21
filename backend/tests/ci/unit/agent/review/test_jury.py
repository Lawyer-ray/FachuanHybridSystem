"""jury 编排：失败票不进 valid、多数门槛、全局并发闸门、打分后的立场成团。

DoD ③：某栏整栏报错 → 该栏 ``valid == 0`` 且 ``score is None``；**不能**把
失败票折算成"答错"，也不能让整次评审跟着失败。成团失败同理：``clusters=[]`` +
``clusters_error``，绝不展示成"三份全异"。全部离线：判定与判等调用都走注入的
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

#: 判等 prompt 的唯一标记（见 ``entail.build_entail_prompt`` 的输出契约）。
_ENTAIL_MARKER = '"entails"'


def _is_entail_prompt(prompt: str) -> bool:
    """这份 prompt 是不是判等请求（打分 prompt 里只会有 ``criteria_met``）。"""
    return _ENTAIL_MARKER in prompt


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
            if _is_entail_prompt(prompt):
                # 判等请求不含栏名标记：这套桩一律判"不等价"，本文件关心的是打分那条链。
                return JudgeReply(content='{"entails": false, "why": "桩"}', model=judge_model)
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


class _ClusteringJudge:
    """打分一律通过；判等按注入的回答表（或抛注入的异常）回答。

    要看"判不了"就传一段非 JSON 文本；要看"judge 本身挂了"就传 ``entail_error``
    （``RuntimeError`` = 预期内的 judge down，``TypeError`` = 我们自己写错的 bug）。
    """

    def __init__(
        self,
        *,
        entail_reply: str = '{"entails": true, "why": "结论一致"}',
        entail_error: BaseException | None = None,
    ) -> None:
        self.entail_reply = entail_reply
        self.entail_error = entail_error
        self.calls = 0
        self.entail_calls = 0

    async def __call__(self, prompt: str, judge_model: str) -> JudgeReply:
        self.calls += 1
        if not _is_entail_prompt(prompt):
            return JudgeReply(
                content='{"criteria_met": true, "explanation": "ok", "evidence_quote": "q"}',
                model=judge_model,
            )
        self.entail_calls += 1
        if self.entail_error is not None:
            raise self.entail_error
        return JudgeReply(content=self.entail_reply, model=judge_model)


_LANES = {"pi": "回答一：建议把违约金改为日万分之五。", "dsh": "回答二：违约金按日万分之五。", "oai": "回答三：同上。"}


class TestClustering:
    """成团接在打分之后：三栏等价 → 一簇；失败 → clusters_error；单栏 → 不跑。"""

    @pytest.mark.asyncio
    async def test_equivalent_lanes_form_one_cluster(self) -> None:
        judge = _ClusteringJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers=_LANES,
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        assert [(cluster.member_ids, cluster.representative_id, cluster.tie) for cluster in review.clusters] == [
            (("pi", "dsh", "oai"), "pi", False)
        ]
        assert review.clusters_error == ""
        # 3 栏 = C(3,2) × 2 方向 = 6 次判等调用，与打分调用分开计数。
        assert judge.entail_calls == 6

    @pytest.mark.asyncio
    async def test_cluster_judge_down_reports_error_not_all_distinct(self) -> None:
        judge = _ClusteringJudge(entail_error=RuntimeError("judge down"))

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers=_LANES,
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        # 打分不受影响（成团失败只影响 clusters / clusters_error 两个字段）。
        assert all(lane.valid == len(_ITEMS) for lane in review.lanes)
        assert review.clusters == [], '失败不许伪造成"三份全异"，也不许留半成品簇'
        assert "judge_error" in review.clusters_error
        assert len(review.clusters_error) <= jury.CLUSTERS_ERROR_LIMIT

    @pytest.mark.asyncio
    async def test_unexpected_cluster_error_is_not_swallowed(self) -> None:
        judge = _ClusteringJudge(entail_error=TypeError("我们自己的 bug"))

        # TypeError / AttributeError 这类是我们写错，不该被静默降级成 clusters_error。
        with pytest.raises(TypeError):
            await jury.run_jury(
                session_id="s-1",
                turn=1,
                task="问题",
                answers=_LANES,
                rubric=_ITEMS,
                judge_models=["judge-a"],
                call_judge=judge,
            )

    @pytest.mark.asyncio
    async def test_unjudgeable_entail_reports_incomplete(self) -> None:
        judge = _ClusteringJudge(entail_reply="这两段我看不出来")

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers=_LANES,
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        # 判等一条都没结论时，equivalence 会诚实地给"全是单例 + tie"，但那与"真的全异"
        # 是两件事：必须整段作废并写明原因。
        assert review.clusters == []
        assert review.clusters_error.startswith("判等未完成：6/6 条判不了")
        assert "parse_failed" in review.clusters_error
        assert len(review.clusters_error) <= jury.CLUSTERS_ERROR_LIMIT

    @pytest.mark.asyncio
    async def test_single_lane_skips_clustering(self) -> None:
        judge = _ClusteringJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers={"good": "回答", "empty": "   "},
            rubric=_ITEMS,
            judge_models=["judge-a"],
            call_judge=judge,
        )

        # 只有 1 栏有正文：没有跨栏立场可判，不跑、也**不算失败**。
        assert review.clusters == []
        assert review.clusters_error == ""
        assert judge.entail_calls == 0
        assert judge.calls == len(_ITEMS), "空栏不该产生 judge 调用"

    @pytest.mark.asyncio
    async def test_missing_judge_models_is_reported_not_silently_empty(self) -> None:
        judge = _ClusteringJudge()

        review = await jury.run_jury(
            session_id="s-1",
            turn=1,
            task="问题",
            answers=_LANES,
            rubric=_ITEMS,
            judge_models=[],
            call_judge=judge,
        )

        assert review.clusters == []
        assert review.clusters_error == "无可用评审模型"
