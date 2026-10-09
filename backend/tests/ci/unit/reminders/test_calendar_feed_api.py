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


# ===================================================================
# ICS 订阅令牌闲置轮换（安全审计 M-4 后半）
# ===================================================================


class TestFeedTokenIdleRotation:
    """令牌原先一次生成永久有效，泄露后无感知、无止损手段。

    改为「闲置超期自动轮换」：轮换而非拒绝，用户的日历订阅不会突然失效。
    """

    @pytest.mark.django_db(transaction=True)
    def test_fresh_token_is_not_rotated(self, feed_user: Any) -> None:
        from apps.reminders.services.calendar_feed_service import CalendarFeedService

        feed_token = CalendarFeedToken.objects.create(user=feed_user, token="fresh-token-value")
        service = CalendarFeedService()

        service._touch_or_rotate(feed_token)
        feed_token.refresh_from_db()

        assert feed_token.token == "fresh-token-value"
        assert feed_token.last_used_at is not None

    @pytest.mark.django_db(transaction=True)
    def test_idle_token_is_rotated_and_last_used_recorded(self, feed_user: Any) -> None:
        """闲置超期：令牌换发 + 记录拉取时间，且本次请求仍能拿到数据。"""
        from apps.reminders.services.calendar_feed_service import CalendarFeedService

        old_token = "idle-token-value"
        feed_token = CalendarFeedToken.objects.create(user=feed_user, token=old_token)
        # created_at 是 auto_now_add，create() 里传会被忽略；用 update 事后改写
        CalendarFeedToken.objects.filter(id=feed_token.id).update(
            created_at=timezone.now() - datetime.timedelta(days=400)
        )
        feed_token.refresh_from_db()
        service = CalendarFeedService()

        service._touch_or_rotate(feed_token)
        feed_token.refresh_from_db()

        assert feed_token.token != old_token
        assert feed_token.last_used_at is not None
        # 旧令牌即时失效
        assert not CalendarFeedToken.objects.filter(token=old_token).exists()

    @pytest.mark.django_db(transaction=True)
    def test_fetch_feed_data_rotates_and_still_serves(self, feed_user: Any, feed_reminder: Any) -> None:
        """端到端：用闲置令牌拉 Feed，数据照常返回，令牌已被换发。"""
        from apps.reminders.services.calendar_feed_service import CalendarFeedService

        old_token = "idle-fetch-token"
        feed_token = CalendarFeedToken.objects.create(user=feed_user, token=old_token)
        CalendarFeedToken.objects.filter(id=feed_token.id).update(
            created_at=timezone.now() - datetime.timedelta(days=400)
        )
        service = CalendarFeedService()

        result = service.fetch_feed_data(old_token)

        assert result is not None
        user, reminders = result
        assert user.id == feed_user.id
        assert len(reminders) >= 1
        # 旧令牌已失效，再次拉取必须失败
        assert service.fetch_feed_data(old_token) is None

    @pytest.mark.django_db(transaction=True)
    def test_active_token_survives_repeated_fetches(self, feed_user: Any, feed_reminder: Any) -> None:
        """活跃订阅（日历 App 定期拉取）不得被轮换打断。"""
        from apps.reminders.services.calendar_feed_service import CalendarFeedService

        feed_token = CalendarFeedToken.objects.create(user=feed_user, token="active-token-value")
        service = CalendarFeedService()

        for _ in range(3):
            service._touch_or_rotate(feed_token)
            feed_token.refresh_from_db()

        assert feed_token.token == "active-token-value"

    @pytest.mark.django_db(transaction=True)
    def test_regenerate_clears_last_used(self, feed_user: Any) -> None:
        """用户主动换发后，last_used_at 清空，避免继承旧时间戳立刻又被判闲置。"""
        from apps.reminders.services.calendar_feed_service import CalendarFeedService

        feed_token = CalendarFeedToken.objects.create(
            user=feed_user,
            token="old-active-token",
            last_used_at=timezone.now(),
        )
        service = CalendarFeedService()

        renewed = service.regenerate_token(feed_user)

        assert renewed.token != "old-active-token"
        assert renewed.last_used_at is None

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_token_endpoint_exposes_last_used_at(self, feed_user: Any) -> None:
        feed_token = await sync_to_async(CalendarFeedToken.objects.create)(user=feed_user, token="expose-token")
        seen = timezone.now()
        await sync_to_async(lambda: CalendarFeedToken.objects.filter(id=feed_token.id).update(last_used_at=seen))()

        result = await get_or_create_token(_session_request(feed_user))

        assert result["last_used_at"] is not None
