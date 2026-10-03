"""ICS 日历订阅 Feed 端点。

日历 App（Apple Calendar / Google Calendar / Outlook）可通过订阅 URL 自动同步提醒：
  GET /api/v1/reminders/ics/feed?token=<token>

Token 由 CalendarFeedToken 模型管理，一对一分配给每个用户。
业务逻辑（令牌管理 + 按访问范围查询提醒 + ICS 渲染）在
apps/reminders/services/calendar_feed_service.py，本层只做参数组装与
sync_to_async 调用。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.reminders.services.calendar_feed_service import CalendarFeedService

logger = logging.getLogger(__name__)

router = Router(tags=["日历订阅"])


class _SessionAuth:
    """仅使用 Django Session 认证（用于 Admin 后台 AJAX 调用）。"""

    openapi_scheme: str = "session"

    def authenticate(self, request: Any) -> Any:
        if hasattr(request, "user") and request.user and request.user.is_authenticated:
            return request.user
        return None

    def __call__(self, request: Any) -> Any:
        return self.authenticate(request)


_session_auth = _SessionAuth()


# ── 服务工厂（ORM 调用经 sync_to_async 包装） ─────────────────


def _get_calendar_feed_service() -> CalendarFeedService:
    """工厂函数：创建日历订阅 Feed 服务实例"""
    return CalendarFeedService()


# ── 端点 ─────────────────────────────────────────────────────


@router.get("/ics/feed")
@rate_limit_from_settings("CALENDAR_FEED", by_user=False, key_func=lambda r: r.META.get("REMOTE_ADDR", ""))
async def calendar_feed(request: Any, token: str = "") -> HttpResponse:
    """ICS 日历订阅端点。

    日历 App 订阅此 URL 后会定期拉取，自动同步所有未来提醒。

    Query params:
        token: 用户订阅令牌（必填）
    """
    if not token:
        return HttpResponse("missing token", status=400)

    service = _get_calendar_feed_service()
    result = await sync_to_async(service.fetch_feed_data)(token)
    if result is None:
        return HttpResponse("invalid token", status=403)

    user, reminders = result
    now = timezone.now()

    ics_bytes = service.render_ics_feed(reminders, str(user))

    response = HttpResponse(ics_bytes, content_type="text/calendar; charset=utf-8")
    # 告诉日历 App 每 4 小时重新拉取
    response["Cache-Control"] = "public, max-age=14400"
    response["Last-Modified"] = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return response


def _require_session_user(request: Any) -> Any | None:
    """检查请求是否带有 Django Session 认证的用户。返回 user 或 None。"""
    if hasattr(request, "user") and request.user and request.user.is_authenticated:
        return request.user
    return None


@router.get("/ics/feed/token")
async def get_or_create_token(request: Any) -> dict[str, str]:
    """获取当前用户的日历订阅 Token（不存在则自动创建）。"""
    user = _require_session_user(request)
    if user is None:
        raise HttpError(401, "Authentication required")

    feed_token = await sync_to_async(_get_calendar_feed_service().get_or_create_token)(user)

    # 构造完整订阅 URL
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    feed_url = f"{scheme}://{host}/api/v1/reminders/ics/feed?token={feed_token.token}"

    return {
        "token": feed_token.token,
        "feed_url": feed_url,
        "created_at": feed_token.created_at.isoformat(),
    }


@router.post("/ics/feed/token/regenerate")
async def regenerate_token(request: Any) -> dict[str, str]:
    """重新生成当前用户的日历订阅 Token（旧 Token 立即失效）。"""
    user = _require_session_user(request)
    if user is None:
        raise HttpError(401, "Authentication required")

    feed_token = await sync_to_async(_get_calendar_feed_service().regenerate_token)(user)

    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    feed_url = f"{scheme}://{host}/api/v1/reminders/ics/feed?token={feed_token.token}"

    return {
        "token": feed_token.token,
        "feed_url": feed_url,
        "created_at": feed_token.created_at.isoformat(),
    }
