"""``POST /agent/messages/{id}/rating``：律师反馈落 ``AgentMessage.metadata``。

为什么要有这层（而不只测 service）：前端 `MessageActions` 早就在调这个路径，
后端缺路由时是「乐观更新后 404 回滚」——界面表现为点了没反应。这里守的是
HTTP 契约本身：200 落地、越权 404（不是 403）、``none`` 撤销。

404 而不是 403 是刻意的：403 等于承认「这条消息存在，只是不是你的」，
对任何拿到 message_id 的人都成了无成本的存在性探测。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.agent.models import AgentMessage, AgentSession
from apps.testing.factories import LawyerFactory

pytestmark = pytest.mark.django_db


def _client_for(user: Any) -> Client:
    from ninja_jwt.tokens import RefreshToken

    client = Client()
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {RefreshToken.for_user(user).access_token}"
    return client


def _message(*, user: Any, **metadata: Any) -> AgentMessage:
    session = AgentSession.objects.create(title="反馈测试", user=user)
    return AgentMessage.objects.create(
        session=session,
        role=AgentMessage.Role.ASSISTANT,
        content="回答正文",
        metadata=metadata,
    )


def _rate(client: Client, message_id: int, rating: str) -> Any:
    return client.post(
        f"/api/v1/agent/messages/{message_id}/rating",
        data={"rating": rating},
        content_type="application/json",
    )


class TestRateMessage:
    def test_up_returns_200_and_persists_rating(self) -> None:
        lawyer = LawyerFactory(username="rating-owner")
        message = _message(user=lawyer, model="kimi-2.6")

        response = _rate(_client_for(lawyer), message.pk, "up")

        assert response.status_code == 200
        assert response.json() == {"message_id": message.pk, "rating": "up"}
        message.refresh_from_db()
        # JSONField 整袋重写：既有键不能被反馈顺手抹掉
        assert message.metadata == {"model": "kimi-2.6", "rating": "up"}

    def test_other_lawyers_message_is_404_not_403(self) -> None:
        owner = LawyerFactory(username="rating-owner")
        intruder = LawyerFactory(username="rating-intruder")
        message = _message(user=owner, rating="down")

        response = _rate(_client_for(intruder), message.pk, "up")

        assert response.status_code == 404
        message.refresh_from_db()
        assert message.metadata == {"rating": "down"}, "越权请求不得改动别人的反馈"

    def test_none_revokes_by_deleting_the_key(self) -> None:
        lawyer = LawyerFactory(username="rating-owner")
        message = _message(user=lawyer, model="kimi-2.6")
        client = _client_for(lawyer)
        assert _rate(client, message.pk, "down").status_code == 200

        response = _rate(client, message.pk, "none")

        assert response.status_code == 200
        assert response.json() == {"message_id": message.pk, "rating": ""}
        message.refresh_from_db()
        assert "rating" not in message.metadata, "撤销是删键，不是写第三种取值"
        assert message.metadata["model"] == "kimi-2.6"


def _history(client: Client, message: AgentMessage) -> dict[str, Any]:
    """回放该消息所属会话，返回目标消息那一行（后端 `MessageOut` 形状）。"""
    response = client.get(f"/api/v1/agent/sessions/{message.session.session_id}/messages")
    assert response.status_code == 200
    rows = [row for row in response.json() if row["message_id"] == message.pk]
    assert len(rows) == 1
    return rows[0]


class TestHistoryReplayRating:
    """刷新后点赞态不能丢：反馈要出现在回放的**顶层** ``rating`` 字段里。

    只留在 ``metadata`` 里等于要求前端每次自己挖 JSON；顶层字段是回放契约，
    前端 hydration 直接读它。
    """

    def test_rated_message_replays_its_rating(self) -> None:
        lawyer = LawyerFactory(username="rating-owner")
        message = _message(user=lawyer, model="kimi-2.6")
        client = _client_for(lawyer)
        assert _rate(client, message.pk, "down").status_code == 200

        row = _history(client, message)

        assert row["rating"] == "down"
        # metadata 里的原键保留：顶层字段是提升，不是搬家
        assert row["metadata"]["rating"] == "down"

    def test_unrated_message_replays_empty_string(self) -> None:
        lawyer = LawyerFactory(username="rating-owner")
        message = _message(user=lawyer, model="kimi-2.6")

        assert _history(_client_for(lawyer), message)["rating"] == ""

    def test_revoked_rating_replays_empty_string(self) -> None:
        lawyer = LawyerFactory(username="rating-owner")
        message = _message(user=lawyer, model="kimi-2.6")
        client = _client_for(lawyer)
        assert _rate(client, message.pk, "up").status_code == 200
        assert _rate(client, message.pk, "none").status_code == 200

        assert _history(client, message)["rating"] == ""
