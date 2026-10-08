"""calendar_feed_api 端点单元测试。

直接调用 async 视图函数（Ninja 端点在注册前即普通协程函数），
覆盖：缺 token 400、无效 token 403、有效 token 200 + ICS 响应头、
Session 认证器、token 获取/重签端点的 401 与 200 分支。

async 视图内的 ORM 经 sync_to_async 在独立线程连接上执行，测试数据
在同步 fixture 里造好、读校验同样经 sync_to_async 提交到线程执行；
django_db(transaction=True) 让 fixture 数据真实提交可见（同
test_cloud_storage_account_service / test_solution_tasks_async 模式）。
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.utils import timezone
from ninja.errors import HttpError

from apps.reminders.api.calendar_feed_api import (
    _get_calendar_feed_service,
    _require_session_user,
    _session_auth,
    calendar_feed,
    get_or_create_token,
    regenerate_token,
)
from apps.reminders.models import CalendarFeedToken, Reminder
from apps.reminders.services.calendar_feed_service import CalendarFeedService
from apps.testing.factories import LawyerFactory


def _feed_request() -> SimpleNamespace:
    """构造 calendar_feed 所需的最小 request 替身（限流 key 只读 META）。"""
    return SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.1"})


def _session_request(user: Any | None, *, secure: bool = False, host: str = "testserver") -> Any:
    """构造 token 端点所需的 request 替身：user/is_secure/get_host 可控。"""

    class _Req:
        def __init__(self) -> None:
            self.user = user

        def is_secure(self) -> bool:
            return secure

        def get_host(self) -> str:
            return host

    return _Req()


@pytest.fixture
def feed_user(db: None):
    return LawyerFactory()


@pytest.fixture
def feed_reminder(db: None):
    """无案件/合同挂载的提醒：Feed 可见性口径的第三分支（对所有人可见）。"""
    return Reminder.objects.create(
        reminder_type="hearing",
        content="feed 端点开庭提醒",
        due_at=timezone.now() + datetime.timedelta(days=1),
    )


class TestSessionFactory:
    def test_factory_returns_calendar_feed_service(self) -> None:
        service = _get_calendar_feed_service()
        assert isinstance(service, CalendarFeedService)


class TestSessionAuth:
    def test_authenticate_returns_user_when_authenticated(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        request = SimpleNamespace(user=user)
        assert _session_auth.authenticate(request) is user

    def test_authenticate_returns_none_for_anonymous(self) -> None:
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert _session_auth.authenticate(request) is None

    def test_authenticate_returns_none_without_user_attr(self) -> None:
        assert _session_auth.authenticate(SimpleNamespace()) is None

    def test_call_delegates_to_authenticate(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        assert _session_auth(SimpleNamespace(user=user)) is user

    def test_openapi_scheme_is_session(self) -> None:
        assert _session_auth.openapi_scheme == "session"


class TestRequireSessionUser:
    def test_returns_user_when_authenticated(self) -> None:
        user = SimpleNamespace(is_authenticated=True)
        assert _require_session_user(SimpleNamespace(user=user)) is user

    def test_returns_none_for_anonymous_or_missing(self) -> None:
        assert _require_session_user(SimpleNamespace(user=SimpleNamespace(is_authenticated=False))) is None
        assert _require_session_user(SimpleNamespace()) is None


@pytest.mark.django_db(transaction=True)
class TestCalendarFeedEndpoint:
    @pytest.mark.asyncio
    async def test_missing_token_returns_400(self) -> None:
        response = await calendar_feed(_feed_request(), token="")
        assert isinstance(response, HttpResponse)
        assert response.status_code == 400
        assert response.content == b"missing token"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_403(self) -> None:
        response = await calendar_feed(_feed_request(), token="tk")
        assert response.status_code == 403
        assert response.content == b"invalid token"

    @pytest.mark.asyncio
    async def test_valid_token_returns_ics_bytes(self, feed_user, feed_reminder) -> None:
        await sync_to_async(CalendarFeedToken.objects.create)(user=feed_user, token="tk")

        response = await calendar_feed(_feed_request(), token="tk")

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/calendar")
        # 安全审计 2026Q4 M-4：ICS 是个人日程数据，必须 private（原为 public，
        # 允许共享缓存/代理保存该用户日程）
        assert response["Cache-Control"] == "private, max-age=14400"
        assert "Last-Modified" in response
        body = response.content.decode("utf-8")
        assert body.startswith("BEGIN:VCALENDAR")
        assert "feed 端点开庭提醒" in body


@pytest.mark.django_db(transaction=True)
class TestGetOrCreateTokenEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_raises_401(self) -> None:
        with pytest.raises(HttpError) as exc_info:
            await get_or_create_token(_session_request(None))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_token_and_http_feed_url(self, feed_user) -> None:
        payload = await get_or_create_token(_session_request(feed_user, secure=False, host="cal.example.com"))

        assert payload["token"]
        assert payload["feed_url"] == f"http://cal.example.com/api/v1/reminders/ics/feed?token={payload['token']}"
        assert payload["created_at"]
        exists = await sync_to_async(CalendarFeedToken.objects.filter)(user=feed_user, token=payload["token"])
        assert await sync_to_async(lambda: exists.exists())()

    @pytest.mark.asyncio
    async def test_reuses_existing_token(self, feed_user) -> None:
        await sync_to_async(CalendarFeedToken.objects.create)(user=feed_user, token="tk")

        payload = await get_or_create_token(_session_request(feed_user))

        assert payload["token"] == "tk"
        tokens = await sync_to_async(
            lambda: list(CalendarFeedToken.objects.filter(user=feed_user).values_list("token", flat=True))
        )()
        assert tokens == ["tk"]


@pytest.mark.django_db(transaction=True)
class TestRegenerateTokenEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_raises_401(self) -> None:
        with pytest.raises(HttpError) as exc_info:
            await regenerate_token(_session_request(None))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_replaces_token_and_builds_https_url(self, feed_user) -> None:
        await sync_to_async(CalendarFeedToken.objects.create)(user=feed_user, token="tk")

        payload = await regenerate_token(_session_request(feed_user, secure=True, host="secure.example.com"))

        assert payload["token"] != "tok-old"
        assert payload["feed_url"] == f"https://secure.example.com/api/v1/reminders/ics/feed?token={payload['token']}"
        fetch = sync_to_async(CalendarFeedService().fetch_feed_data)
        assert await fetch("tok-old") is None
        assert await fetch(payload["token"]) is not None

    @pytest.mark.asyncio
    async def test_creates_token_when_missing(self, feed_user) -> None:
        payload = await regenerate_token(_session_request(feed_user))
        assert payload["token"]
        count = await sync_to_async(lambda: CalendarFeedToken.objects.filter(user=feed_user).count())()
        assert count == 1
