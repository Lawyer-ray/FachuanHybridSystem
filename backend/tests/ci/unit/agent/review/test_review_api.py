"""``POST/GET /agent/sessions/{id}/review``：三栏端到端落库 + 刷新回放 + options。

DoD ② 的证据在这里：一次三栏会话（pi / dsh / openai-agents）跑完整 jury →
逐条 verdict + 立场成团落 ``AgentReview`` → 按 turn 回读，review_id、21 条判定与簇
完全一致。judge 用桩（``_llm_judge`` 的门面被替换），不联网、不调真实模型。
“judge 模型可省略”的四条解析分支（契约 §C2）也在这里测。
"""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from ninja.errors import HttpError

from apps.agent.api import review_api
from apps.agent.api.review_api import ReviewIn
from apps.agent.models import AgentMessage, AgentReview, AgentSession
from apps.agent.services.review import judge_client
from apps.agent.services.review.judge_models import JUDGE_MODELS_ENV
from apps.agent.services.review.rubric import DEFAULT_RUBRIC_ID
from apps.organization.models import LawFirm, Lawyer

_LANES = ("pi", "dsh", "openai-agents")
_TURN = 1
#: 3 栏 × 7 条 rubric = 21 次打分调用；3 栏两两 × 2 方向 = 6 次判等调用。
_SCORING_CALLS = 3 * 7
_ENTAIL_CALLS = 6


class _FakeJudgeService:
    """打分按 criterion 的分值符号决定 true/false；判等一律"等价"。"""

    def __init__(self) -> None:
        self.calls = 0

    async def achat(self, **kwargs: Any) -> Any:
        self.calls += 1
        prompt = kwargs["messages"][0]["content"]
        if '"entails"' in prompt:
            content = '{"entails": true, "why": "结论一致"}'
        else:
            # 负分项判"未发生"（false）；正分项判"满足"（true）。
            met = "[-1]" not in prompt and "[-2]" not in prompt
            content = f'{{"criteria_met": {str(met).lower()}, "explanation": "满足", "evidence_quote": "第 3 条"}}'
        return SimpleNamespace(
            content=content,
            model=kwargs["model"],
            prompt_tokens=11,
            completion_tokens=4,
            total_tokens=15,
        )


def _request(user: Any) -> SimpleNamespace:
    return SimpleNamespace(auth=user)


def _make_user(username: str = "review_api_user") -> Any:
    firm = LawFirm.objects.create(name=f"评审测试所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret（测试固定口令，非真实凭证）
        law_firm=firm,
    )


def _make_three_lane_session(user: Any, models: Sequence[str] = ()) -> AgentSession:
    """建一个三栏会话；``models`` 依次写进各栏消息的 ``metadata["model"]``（§C2 第 3 条）。"""
    session = AgentSession.objects.create(user=user, title="三栏评审")
    AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content="请审查合同第 3 条")
    for index, lane in enumerate(_LANES):
        AgentMessage.objects.create(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            agent_kind=lane,
            content=f"【脱敏样例】{lane} 对第 3 条的回答：建议将违约金改为日万分之五。",
            metadata={"model": models[index]} if index < len(models) else {},
        )
    return session


def _install_fake_judge(monkeypatch: pytest.MonkeyPatch) -> _FakeJudgeService:
    """把 judge 的 async 门面换成桩（不联网、不调真模型）。"""
    service = _FakeJudgeService()

    async def _fake_async_service() -> _FakeJudgeService:
        return service

    monkeypatch.setattr(judge_client, "_async_llm_service", _fake_async_service)
    return service


@pytest.mark.django_db(transaction=True)
def test_three_lane_review_persists_and_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    session = _make_three_lane_session(user)
    service = _install_fake_judge(monkeypatch)

    review = async_to_sync(review_api.review_session)(
        _request(user),
        str(session.session_id),
        ReviewIn(turn=_TURN, agents=list(_LANES), rubric_id=DEFAULT_RUBRIC_ID, judge_models=["judge-a"]),
    )

    assert [lane.lane for lane in review.lanes] == list(_LANES)
    assert len(review.verdicts) == 3 * 7
    assert all(lane.valid == 7 for lane in review.lanes)
    assert all(lane.score == pytest.approx(1.0) for lane in review.lanes)
    assert review.stage == "shadow"
    # tokens 只记打分阶段（判等成本不进 Review.tokens，见 lane B 汇报的“未做到”）。
    assert review.tokens == {
        "prompt": _SCORING_CALLS * 11,
        "completion": _SCORING_CALLS * 4,
        "total": _SCORING_CALLS * 15,
    }
    assert service.calls == _SCORING_CALLS + _ENTAIL_CALLS

    # 三栏答案实质等价 → 一簇，代表是第一栏（成团在打分之后跑）。
    assert [(cluster.member_ids, cluster.representative_id, cluster.tie) for cluster in review.clusters] == [
        (_LANES, _LANES[0], False)
    ]
    assert review.clusters_error == ""

    record = AgentReview.objects.get(session=session, turn=_TURN)
    assert record.review_id == review.review_id
    assert record.rubric_id == DEFAULT_RUBRIC_ID
    assert len(record.verdicts) == _SCORING_CALLS
    assert {item["lane"] for item in record.verdicts} == set(_LANES)
    assert record.clusters == [{"member_ids": list(_LANES), "representative_id": _LANES[0], "tie": False}]
    assert record.clusters_error == ""

    replay = async_to_sync(review_api.get_session_review)(_request(user), str(session.session_id), _TURN)
    assert replay.review_id == review.review_id
    assert [verdict.model_dump() for verdict in replay.verdicts] == [
        verdict.model_dump() for verdict in review.verdicts
    ]
    # 回放必须把 clusters 一起还原（否则刷新后共识/分歧整块消失）。
    assert replay.clusters == review.clusters
    assert replay.clusters_error == ""


@pytest.mark.django_db(transaction=True)
def test_review_rejects_foreign_session_with_404(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _make_user("review_owner")
    intruder = _make_user("review_intruder")
    session = _make_three_lane_session(owner)
    _install_fake_judge(monkeypatch)

    with pytest.raises(HttpError) as exc:
        async_to_sync(review_api.review_session)(
            _request(intruder),
            str(session.session_id),
            ReviewIn(turn=_TURN, agents=list(_LANES), rubric_id=DEFAULT_RUBRIC_ID, judge_models=["judge-a"]),
        )

    assert exc.value.status_code == 404
    assert not AgentReview.objects.filter(session=session).exists()


@pytest.mark.django_db(transaction=True)
def test_review_rejects_unknown_rubric_and_out_of_range_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user("review_bad_input")
    session = _make_three_lane_session(user)
    _install_fake_judge(monkeypatch)

    with pytest.raises(HttpError) as unknown:
        async_to_sync(review_api.review_session)(
            _request(user),
            str(session.session_id),
            ReviewIn(turn=_TURN, agents=list(_LANES), rubric_id="no-such-rubric", judge_models=["judge-a"]),
        )
    assert unknown.value.status_code == 404

    with pytest.raises(HttpError) as out_of_range:
        async_to_sync(review_api.review_session)(
            _request(user),
            str(session.session_id),
            ReviewIn(turn=9, agents=list(_LANES), rubric_id=DEFAULT_RUBRIC_ID, judge_models=["judge-a"]),
        )
    assert out_of_range.value.status_code == 404


@pytest.mark.django_db
def test_agent_review_model_defaults_and_index() -> None:
    session = AgentSession.objects.create(title="模型测试")
    record = AgentReview.objects.create(session=session, review_id="r" * 32, turn=1, rubric_id="rubric")

    assert record.stage == AgentReview.Stage.SHADOW
    assert record.lanes == []
    assert record.verdicts == []
    assert record.unverified == []
    assert record.tokens == {}
    assert "agent_review_session_turn_idx" in {index.name for index in AgentReview._meta.indexes}


@pytest.mark.django_db
def test_route_is_registered_and_requires_auth() -> None:
    """路径存在性：未认证访问必须是 401，而不是 404（404 说明路由没挂上）。"""
    import json

    from django.test import Client

    from apiSystem.api import api_v1

    schema = api_v1.get_openapi_schema()
    assert any(path.endswith("/agent/sessions/{session_id}/review") for path in schema["paths"])
    assert any(path.endswith("/agent/review/options") for path in schema["paths"])

    client = Client()
    url = "/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000/review"
    response = client.post(
        url,
        data=json.dumps({"turn": 1, "agents": ["pi"], "rubric_id": DEFAULT_RUBRIC_ID, "judge_models": ["judge-a"]}),
        content_type="application/json",
    )
    assert response.status_code == 401
    assert client.get(url).status_code == 401
    assert client.get("/api/v1/agent/review/options").status_code == 401


class TestJudgeModelResolution:
    """契约 §C2 的四条解析分支（``judge_models`` 可省略）。"""

    @pytest.mark.django_db(transaction=True)
    def test_request_models_win(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = _make_user("review_request_models")
        session = _make_three_lane_session(user, models=("turn-a", "turn-b", "turn-c"))
        _install_fake_judge(monkeypatch)
        monkeypatch.setenv(JUDGE_MODELS_ENV, "env-a")

        async_to_sync(review_api.review_session)(
            _request(user),
            str(session.session_id),
            ReviewIn(turn=_TURN, agents=list(_LANES), judge_models=["judge-a"]),
        )

        assert AgentReview.objects.get(session=session, turn=_TURN).judge_models == ["judge-a"]

    @pytest.mark.django_db(transaction=True)
    def test_configured_models_used_when_request_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = _make_user("review_env_models")
        session = _make_three_lane_session(user, models=("turn-a", "turn-b", "turn-c"))
        _install_fake_judge(monkeypatch)
        monkeypatch.setenv(JUDGE_MODELS_ENV, " env-a , env-b ,")

        async_to_sync(review_api.review_session)(
            _request(user), str(session.session_id), ReviewIn(turn=_TURN, agents=list(_LANES))
        )

        # 逗号分隔 + 去空白；平台配置优先于本轮模型。
        assert AgentReview.objects.get(session=session, turn=_TURN).judge_models == ["env-a", "env-b"]

    @pytest.mark.django_db(transaction=True)
    def test_turn_models_used_when_nothing_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = _make_user("review_turn_models")
        session = _make_three_lane_session(user, models=("kimi-2.6", "glm53", "gpt-5.1"))
        _install_fake_judge(monkeypatch)
        monkeypatch.delenv(JUDGE_MODELS_ENV, raising=False)

        async_to_sync(review_api.review_session)(
            _request(user), str(session.session_id), ReviewIn(turn=_TURN, agents=list(_LANES))
        )

        # 本轮各栏真的跑过的模型，去重保序后**最多 2 个**（§C2 第 3 条）。
        assert AgentReview.objects.get(session=session, turn=_TURN).judge_models == ["kimi-2.6", "glm53"]

    @pytest.mark.django_db(transaction=True)
    def test_no_judge_model_anywhere_is_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = _make_user("review_no_models")
        # 消息里不写 metadata["model"]：三处都拿不到模型。
        session = _make_three_lane_session(user)
        service = _install_fake_judge(monkeypatch)
        monkeypatch.delenv(JUDGE_MODELS_ENV, raising=False)

        with pytest.raises(HttpError) as exc:
            async_to_sync(review_api.review_session)(
                _request(user), str(session.session_id), ReviewIn(turn=_TURN, agents=list(_LANES))
            )

        assert exc.value.status_code == 422
        assert "未配置评审模型" in exc.value.message
        assert service.calls == 0, "解析不出 judge 模型时一次 LLM 调用都不该发起"
        assert not AgentReview.objects.filter(session=session).exists()

    def test_review_in_defaults_let_frontend_omit_both_fields(self) -> None:
        payload = ReviewIn(turn=1, agents=["pi"])

        assert payload.rubric_id == DEFAULT_RUBRIC_ID
        assert payload.judge_models == []


class TestReviewOptions:
    """``GET /agent/review/options``（契约 §C1）：前端不许自己猜模型名。"""

    def test_lists_rubrics_models_and_lane_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(review_api, "_available_models", lambda: ["kimi-2.6", "glm53"])

        options = async_to_sync(review_api.review_options)(_request(SimpleNamespace(id=1)))

        assert options.rubric_ids == [DEFAULT_RUBRIC_ID]
        assert options.judge_models == ["kimi-2.6", "glm53"]
        assert options.max_lanes == review_api.MAX_ANSWERS

    def test_empty_platform_models_is_an_empty_list_not_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(review_api, "_available_models", lambda: [])

        options = async_to_sync(review_api.review_options)(_request(SimpleNamespace(id=1)))

        assert options.judge_models == []
