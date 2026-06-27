"""ICS 日历订阅 Feed 端点。

日历 App（Apple Calendar / Google Calendar / Outlook）可通过订阅 URL 自动同步提醒：
  GET /api/v1/reminders/ics/feed?token=<token>

Token 由 CalendarFeedToken 模型管理，一对一分配给每个用户。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router

class SessionAuth:
    """仅使用 Django Session 认证（用于 Admin 后台 AJAX 调用）"""
    openapi_scheme: str = "session"

    def authenticate(self, request: Any) -> Any:
        if hasattr(request, "user") and request.user and request.user.is_authenticated:
            return request.user
        return None

    def __call__(self, request: Any) -> Any:
        return self.authenticate(request)

from apps.reminders.models import CalendarFeedToken, Reminder, ReminderType

logger = logging.getLogger(__name__)

router = Router(tags=["日历订阅"])


def _build_ics_feed(reminders: list[Reminder], user_display: str) -> bytes:
    """将 Reminder 列表渲染为 iCalendar (.ics) 字节流。"""
    from icalendar import Calendar

    cal = Calendar()
    cal.add("prodid", "-//法穿AI Copilot//Calendar Feed//CN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGOR")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"法穿提醒 - {user_display}")
    cal.add("x-wr-timezone", "Asia/Shanghai")

    now = timezone.now()

    for r in reminders:
        due_local = timezone.localtime(r.due_at)
        metadata = r.metadata if isinstance(r.metadata, dict) else {}

        # ── VEVENT ──
        vevent: dict[str, Any] = {
            "uid": f"reminder-{r.id}@fachuan-system",
            "dtstart": due_local,
            "dtstamp": now,
            "status": "CONFIRMED",
        }

        # summary
        vevent["summary"] = r.content

        # duration (默认 1 小时，支持 metadata.end_at)
        end_at = metadata.get("end_at")
        if end_at:
            try:
                end_dt = datetime.fromisoformat(str(end_at))
                if end_dt.tzinfo is None:
                    end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
                vevent["dtend"] = timezone.localtime(end_dt)
            except (ValueError, TypeError):
                vevent["dtend"] = due_local + timedelta(hours=1)
        else:
            vevent["dtend"] = due_local + timedelta(hours=1)

        # categories
        type_label = dict(ReminderType.choices).get(r.reminder_type, r.reminder_type)
        vevent["categories"] = str(type_label)

        # location
        location = metadata.get("courtroom", "") or metadata.get("location", "")
        if location and location != "missing value":
            vevent["location"] = str(location)

        # description
        desc_parts: list[str] = []
        if r.contract_id is not None and r.contract:
            desc_parts.append(f"合同: {r.contract.name}")
        if r.case_id is not None and r.case:
            desc_parts.append(f"案件: {r.case.name}")
        if r.case_log_id is not None and r.case_log:
            desc_parts.append(f"案件日志: #{r.case_log_id}")
        note = metadata.get("note", "")
        if note:
            desc_parts.append(f"备注: {note}")
        if desc_parts:
            vevent["description"] = "\n".join(desc_parts)

        # alarm: 开庭前 1 天提醒
        if r.reminder_type == ReminderType.HEARING:
            from icalendar import Alarm

            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", r.content)
            alarm.add("trigger", timedelta(days=-1))
            vevent_obj = _make_vevent(vevent)
            vevent_obj.add_component(alarm)
            cal.add_component(vevent_obj)
        else:
            cal.add_component(_make_vevent(vevent))

    return bytes(cal.to_ical())


def _make_vevent(props: dict[str, Any]) -> Any:
    """从字典构建 iCal Event 对象。"""
    from icalendar import Event

    ev = Event()
    for key, value in props.items():
        ev.add(key, value)
    return ev


@router.get("/ics/feed")
def calendar_feed(request: Any, token: str = "") -> HttpResponse:
    """ICS 日历订阅端点。

    日历 App 订阅此 URL 后会定期拉取，自动同步所有未来提醒。

    Query params:
        token: 用户订阅令牌（必填）
    """
    if not token:
        return HttpResponse("missing token", status=400)

    # 验证 token
    try:
        feed_token = CalendarFeedToken.objects.select_related("user").get(token=token)
    except CalendarFeedToken.DoesNotExist:
        return HttpResponse("invalid token", status=403)

    user = feed_token.user

    # 查询该用户有权访问的案件 ID（指派 + 授权访问）
    from apps.cases.models import CaseAssignment, CaseAccessGrant

    user_case_ids = list(
        CaseAssignment.objects.filter(lawyer=user)
        .values_list("case_id", flat=True)
        .union(
            CaseAccessGrant.objects.filter(grantee=user).values_list("case_id", flat=True)
        )
    )

    now = timezone.now()
    cutoff = now + timedelta(days=365)  # 未来 1 年

    reminders = (
        Reminder.objects.select_related("contract", "case", "case_log", "case_log__case")
        .filter(
            Q(due_at__gte=now) & Q(due_at__lte=cutoff),
            Q(case_id__in=user_case_ids) | Q(case_id__isnull=True),
        )
        .order_by("due_at", "id")
    )

    ics_bytes = _build_ics_feed(list(reminders), str(user))

    response = HttpResponse(ics_bytes, content_type="text/calendar; charset=utf-8")
    # 告诉日历 App 每 4 小时重新拉取
    response["Cache-Control"] = "public, max-age=14400"
    response["Last-Modified"] = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return response


@router.get("/ics/feed/token", auth=SessionAuth())
def get_or_create_token(request: Any) -> dict[str, str]:
    """获取当前用户的日历订阅 Token（不存在则自动创建）。"""
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    feed_token = CalendarFeedToken.get_or_create_for_user(ctx.user)

    # 构造完整订阅 URL
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    feed_url = f"{scheme}://{host}/api/v1/reminders/ics/feed?token={feed_token.token}"

    return {
        "token": feed_token.token,
        "feed_url": feed_url,
        "created_at": feed_token.created_at.isoformat(),
    }


@router.post("/ics/feed/token/regenerate", auth=SessionAuth())
def regenerate_token(request: Any) -> dict[str, str]:
    """重新生成当前用户的日历订阅 Token（旧 Token 立即失效）。"""
    import secrets

    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    new_token = secrets.token_urlsafe(48)

    CalendarFeedToken.objects.filter(user=ctx.user).update(token=new_token)

    # 重新获取
    feed_token = CalendarFeedToken.objects.get(user=ctx.user)

    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    feed_url = f"{scheme}://{host}/api/v1/reminders/ics/feed?token={feed_token.token}"

    return {
        "token": feed_token.token,
        "feed_url": feed_url,
        "created_at": feed_token.created_at.isoformat(),
    }
