"""``POST/GET /agent/sessions/{id}/review``：三栏端到端落库 + 刷新回放。

DoD ② 的证据在这里：一次三栏会话（pi / dsh / openai-agents）跑完整 jury →
逐条 verdict 落 ``AgentReview`` → 按 turn 回读，review_id 与 21 条判定完全一致。
judge 用桩（``_llm_judge`` 的门面被替换），不联网、不调真实模型。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from ninja.errors import HttpError

from apps.agent.api import review_api
from apps.agent.api.review_api import ReviewIn
from apps.agent.models import AgentMessage, AgentReview, AgentSession
from apps.agent.services.review import judge_client
from apps.agent.services.review.rubric import DEFAULT_RUBRIC_ID
from apps.organization.models import LawFirm, Lawyer

_LANES = ("pi", "dsh", "openai-agents")
_TURN = 1


class _FakeJudgeService:
    """按 criterion 的分值符号决定 true/false；记录调用次数。"""

    def __init__(self) -> None:
        self.calls = 0

    async def achat(self, **kwargs: Any) -> Any:
        self.calls += 1
        prompt = kwargs["messages"][0]["content"]
        # 负分项判"未发生"（false）；正分项判"满足"（true）。
        met = "[-1]" not in prompt and "[-2]" not in prompt
        return SimpleNamespace(
            content=f'{{"criteria_met": {str(met).lower()}, "explanation": "满足", "evidence_quote": "第 3 条"}}',
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


def _make_three_lane_session(user: Any) -> AgentSession:
    session = AgentSession.objects.create(user=user, title="三栏评审")
    AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content="请审查合同第 3 条")
    for lane in _LANES:
        AgentMessage.objects.create(
            session=session,
            role=AgentMessage.Role.ASSISTANT,
            agent_kind=lane,
            content=f"【脱敏样例】{lane} 对第 3 条的回答：建议将违约金改为日万分之五。",
        )
    return session


@pytest.mark.django_db(transaction=True)
def test_three_lane_review_persists_and_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _make_user()
    session = _make_three_lane_session(user)
    service = _FakeJudgeService()

    async def _fake_async_service():  # 测试替身：judge 现在走 async 门面
        return service

    monkeypatch.setattr(judge_client, "_async_llm_service", _fake_async_service)

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
    assert review.tokens == {"prompt": 21 * 11, "completion": 21 * 4, "total": 21 * 15}
    assert service.calls == 21

    record = AgentReview.objects.get(session=session, turn=_TURN)
    assert record.review_id == review.review_id
    assert record.rubric_id == DEFAULT_RUBRIC_ID
    assert len(record.verdicts) == 21
    assert {item["lane"] for item in record.verdicts} == set(_LANES)

    replay = async_to_sync(review_api.get_session_review)(_request(user), str(session.session_id), _TURN)
    assert replay.review_id == review.review_id
    assert [verdict.model_dump() for verdict in replay.verdicts] == [
        verdict.model_dump() for verdict in review.verdicts
    ]


@pytest.mark.django_db(transaction=True)
def test_review_rejects_foreign_session_with_404(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _make_user("review_owner")
    intruder = _make_user("review_intruder")
    session = _make_three_lane_session(owner)

    async def _fake_async_service():  # 测试替身：judge 现在走 async 门面
        return _FakeJudgeService()

    monkeypatch.setattr(judge_client, "_async_llm_service", _fake_async_service)

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

    async def _fake_async_service():  # 测试替身：judge 现在走 async 门面
        return _FakeJudgeService()

    monkeypatch.setattr(judge_client, "_async_llm_service", _fake_async_service)

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

    client = Client()
    url = "/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000/review"
    response = client.post(
        url,
        data=json.dumps({"turn": 1, "agents": ["pi"], "rubric_id": DEFAULT_RUBRIC_ID, "judge_models": ["judge-a"]}),
        content_type="application/json",
    )
    assert response.status_code == 401
    assert client.get(url).status_code == 401
