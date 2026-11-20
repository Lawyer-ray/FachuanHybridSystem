"""``POST /agent/reviews/{id}/adopt`` + ``GET .../adoption``：采纳埋点与影子开关。

DoD 证据：

1. 采纳落库 + 回读一致（POST 返回值 == 库里的行 == GET 回显）；
2. 同一 review 二次采纳只更新同一行（不产生第二行，``adopted_at`` 刷新）；
3. 他人 token 与不存在的 review_id 一律 404（错误体带原因）；
4. 影子开关开着/关着，评审端点都**零自动动作**：把 ``record_adoption`` 换成
   探针，断言评审流程从未调用它，且库里没有采纳行；
5. 迁移 0022 的验证是命令级的（``migrate`` + ``makemigrations --check``）。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from django.db import IntegrityError, transaction
from ninja.errors import HttpError

from apps.agent.api import review_api
from apps.agent.api.review_api import AdoptIn, ReviewIn
from apps.agent.models import AgentMessage, AgentReview, AgentReviewAdoption, AgentSession
from apps.agent.services.adjudication.contracts import LaneReview, Review
from apps.agent.services.review.adoption import auto_path_allowed, shadow_enabled
from apps.agent.services.review.rubric import DEFAULT_RUBRIC_ID
from apps.organization.models import LawFirm, Lawyer


def _request(user: Any) -> SimpleNamespace:
    return SimpleNamespace(auth=user)


def _make_user(username: str) -> Any:
    firm = LawFirm.objects.create(name=f"采纳测试所-{username}")
    return Lawyer.objects.create_user(
        username=username, password="x-test-12345678", law_firm=firm  # pragma: allowlist secret（测试固定口令，非真实凭证）
    )  # pragma: allowlist secret（测试固定口令，非真实凭证）


def _make_review(user: Any) -> AgentReview:
    """直接落一条评审快照（采纳埋点不依赖 jury，不联网）。"""
    session = AgentSession.objects.create(user=user, title="采纳测试")
    return AgentReview.objects.create(
        session=session,
        user=user,
        review_id="a" * 32,
        turn=1,
        rubric_id=DEFAULT_RUBRIC_ID,
        lanes=[{"lane": "pi", "valid": 7, "yes": 6, "score": 0.86, "one_line": "先催告"}],
    )


def _adopt(user: Any, review: AgentReview, **payload: Any) -> Any:
    return async_to_sync(review_api.adopt_review)(_request(user), review.review_id, AdoptIn(**payload))


def _read_adoption(user: Any, review: AgentReview) -> Any:
    return async_to_sync(review_api.get_review_adoption)(_request(user), review.review_id)


@pytest.mark.django_db(transaction=True)
def test_adopt_persists_and_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    # 影子开着（默认）也必须允许律师显式采纳：开关只当前置条件，不拦显式动作。
    monkeypatch.setenv("FACHUAN_REVIEW_SHADOW", "1")
    user = _make_user("adopt_owner")
    review = _make_review(user)

    out = _adopt(user, review, lane=" pi ", merged=False, note=" 先催告更稳 ")

    assert out.review_id == review.review_id
    assert out.lane == "pi"  # 空白已归一
    assert out.merged is False
    assert out.note == "先催告更稳"
    row = AgentReviewAdoption.objects.get(review=review)
    assert row.user_id == user.pk
    assert row.lane == "pi"
    assert row.note == "先催告更稳"
    assert row.adopted_at.isoformat() == out.adopted_at

    replay = _read_adoption(user, review)
    assert replay.adoption is not None
    assert replay.adoption.model_dump() == out.model_dump()


@pytest.mark.django_db(transaction=True)
def test_repeat_adoption_updates_single_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACHUAN_REVIEW_SHADOW", "1")
    user = _make_user("adopt_repeat")
    review = _make_review(user)

    first = _adopt(user, review, lane="pi", note="先选 pi")
    first_at = AgentReviewAdoption.objects.get(review=review).adopted_at
    second = _adopt(user, review, lane="dsh", note="看过原文改选 dsh")
    third = _adopt(user, review, lane=None, merged=True, note="三栏合并")

    assert AgentReviewAdoption.objects.filter(review=review).count() == 1
    row = AgentReviewAdoption.objects.get(review=review)
    assert row.lane is None
    assert row.merged is True
    assert row.note == "三栏合并"
    assert row.adopted_at >= first_at
    assert datetime.fromisoformat(second.adopted_at) >= datetime.fromisoformat(first.adopted_at)
    assert datetime.fromisoformat(third.adopted_at) >= datetime.fromisoformat(second.adopted_at)

    replay = _read_adoption(user, review)
    assert replay.adoption is not None
    assert replay.adoption.model_dump() == third.model_dump()


@pytest.mark.django_db(transaction=True)
def test_adoption_is_scoped_to_review_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACHUAN_REVIEW_SHADOW", "1")
    owner = _make_user("adopt_scope_owner")
    intruder = _make_user("adopt_scope_intruder")
    review = _make_review(owner)

    assert _read_adoption(owner, review).adoption is None  # 未采纳不是错误

    with pytest.raises(HttpError) as denied:
        _adopt(intruder, review, lane="pi")
    assert denied.value.status_code == 404
    assert denied.value.message == "评审不存在"

    with pytest.raises(HttpError) as denied_read:
        _read_adoption(intruder, review)
    assert denied_read.value.status_code == 404
    assert denied_read.value.message == "评审不存在"

    with pytest.raises(HttpError) as unknown:
        async_to_sync(review_api.get_review_adoption)(_request(owner), "0" * 32)
    assert unknown.value.status_code == 404
    assert unknown.value.message == "评审不存在"

    assert not AgentReviewAdoption.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("shadow_value", ["1", "0"])
def test_review_endpoint_never_auto_adopts(monkeypatch: pytest.MonkeyPatch, shadow_value: str) -> None:
    """影子开关的两种取值下，评审端点都不许走任何自动采纳路径。"""
    monkeypatch.setenv("FACHUAN_REVIEW_SHADOW", shadow_value)
    user = _make_user(f"adopt_shadow_{shadow_value}")
    session = AgentSession.objects.create(user=user, title="影子探针")
    AgentMessage.objects.create(session=session, role=AgentMessage.Role.USER, content="请审查第 3 条")
    AgentMessage.objects.create(
        session=session,
        role=AgentMessage.Role.ASSISTANT,
        agent_kind="pi",
        content="建议把违约金改为日万分之五。",
    )

    calls: list[dict[str, Any]] = []

    async def _probe(**kwargs: Any) -> Any:
        calls.append(kwargs)
        raise AssertionError("评审端点不得自动采纳（影子期零自动动作）")

    async def _fake_jury(**_kwargs: Any) -> Review:
        return Review(
            review_id="c" * 32,
            session_id=str(session.session_id),
            turn=1,
            rubric_id=DEFAULT_RUBRIC_ID,
            lanes=[LaneReview(lane="pi", valid=1, yes=1, score=1.0, one_line="先催告")],
        )

    monkeypatch.setattr(review_api, "record_adoption", _probe)
    monkeypatch.setattr(review_api, "run_jury", _fake_jury)

    review = async_to_sync(review_api.review_session)(
        _request(user),
        str(session.session_id),
        ReviewIn(turn=1, agents=["pi"], rubric_id=DEFAULT_RUBRIC_ID, judge_models=["judge-a"]),
    )

    assert review.stage == "shadow"
    assert AgentReview.objects.filter(session=session).count() == 1
    assert calls == []
    assert AgentReviewAdoption.objects.count() == 0
    # 开关本身只改变"自动路径前置条件"，不改变显式采纳能力。
    assert shadow_enabled() is (shadow_value == "1")
    assert auto_path_allowed() is (shadow_value == "0")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("off", False),
        (" 0 ", False),
    ],
)
def test_shadow_switch_parsing(monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: bool) -> None:
    if raw is None:
        monkeypatch.delenv("FACHUAN_REVIEW_SHADOW", raising=False)
    else:
        monkeypatch.setenv("FACHUAN_REVIEW_SHADOW", raw)
    assert shadow_enabled() is expected
    assert auto_path_allowed() is (not expected)


@pytest.mark.django_db
def test_adoption_model_is_one_row_per_review() -> None:
    user = _make_user("adopt_model")
    review = _make_review(user)
    AgentReviewAdoption.objects.create(review=review, user=user, lane="pi")

    assert AgentReviewAdoption._meta.get_field("review").one_to_one is True
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AgentReviewAdoption.objects.create(review=review, user=user, lane="dsh")


@pytest.mark.django_db
def test_adoption_routes_are_registered_and_require_auth() -> None:
    """路径存在性：未认证访问必须是 401，而不是 404（404 说明路由没挂上）。"""
    import json

    from django.test import Client

    from apiSystem.api import api_v1

    schema = api_v1.get_openapi_schema()
    assert any(path.endswith("/agent/reviews/{review_id}/adopt") for path in schema["paths"])
    assert any(path.endswith("/agent/reviews/{review_id}/adoption") for path in schema["paths"])

    client = Client()
    review_id = "0" * 32
    adopt_url = f"/api/v1/agent/reviews/{review_id}/adopt"
    response = client.post(adopt_url, data=json.dumps({"lane": "pi"}), content_type="application/json")
    assert response.status_code == 401
    assert client.get(f"/api/v1/agent/reviews/{review_id}/adoption").status_code == 401
