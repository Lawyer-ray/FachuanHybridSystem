"""ICS 日历订阅 Feed 服务。

承载 calendar_feed_api 下沉的业务：订阅令牌（CalendarFeedToken）的
获取/签发/重签、按用户可访问范围（案件 + 合同口径）查询提醒数据、
以及 ICS 字节流渲染。API 层只做参数组装与 sync_to_async 调用。
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone
from icalendar import Alarm, Calendar, Event

from apps.reminders.models import CalendarFeedToken, Reminder, ReminderType

logger = logging.getLogger(__name__)

# 订阅 Feed 的最大前瞻窗口（与既有 API 行为一致：未来一年）
FEED_LOOKAHEAD_DAYS = 365


class CalendarFeedService:
    """日历订阅 Feed 的数据访问与令牌管理。"""

    def fetch_feed_data(self, token: str) -> tuple[Any, list[Reminder]] | None:
        """验证 token 并查询提醒数据。返回 (user, reminders) 或 None（token 无效）。"""
        from apps.cases.models import CaseAccessGrant, CaseAssignment
        from apps.contracts.models import Contract, ContractAssignment

        try:
            feed_token = CalendarFeedToken.objects.select_related("user").get(token=token)
        except CalendarFeedToken.DoesNotExist:
            return None

        user = feed_token.user

        # 两次查询 + set 合并（比 union 更可靠）
        assigned = set(CaseAssignment.objects.filter(lawyer=user).values_list("case_id", flat=True))
        granted = set(CaseAccessGrant.objects.filter(grantee=user).values_list("case_id", flat=True))
        user_case_ids = assigned | granted

        # 合同可访问集合（与 ContractAccessPolicy 口径一致：直接指派 + 合同关联案件的办案成员）
        contract_assigned = set(ContractAssignment.objects.filter(lawyer=user).values_list("contract_id", flat=True))
        contract_via_case = set(Contract.objects.filter(cases__assignments__lawyer=user).values_list("id", flat=True))
        user_contract_ids = contract_assigned | contract_via_case

        now = timezone.now()
        cutoff = now + timedelta(days=FEED_LOOKAHEAD_DAYS)

        reminders = list(
            Reminder.objects.select_related("contract", "case", "case_log", "case_log__case")
            .filter(
                Q(due_at__gte=now) & Q(due_at__lte=cutoff),
                Q(case_id__in=user_case_ids)
                | Q(case_id__isnull=True, contract_id__in=user_contract_ids)
                | Q(case_id__isnull=True, contract_id__isnull=True),
            )
            .order_by("due_at", "id")
        )

        return user, reminders

    def get_or_create_token(self, user: Any) -> CalendarFeedToken:
        """获取当前用户的订阅令牌，不存在则自动创建。"""
        return CalendarFeedToken.get_or_create_for_user(user)

    def regenerate_token(self, user: Any) -> CalendarFeedToken:
        """重新生成用户的订阅令牌（旧令牌立即失效）。"""
        new_token = secrets.token_urlsafe(48)

        obj, created = CalendarFeedToken.objects.get_or_create(
            user=user,
            defaults={"token": new_token},
        )
        if not created:
            obj.token = new_token
            obj.save(update_fields=["token", "updated_at"])
        return obj

    def render_ics_feed(self, reminders: list[Reminder], user_display: str) -> bytes:
        """将 Reminder 列表渲染为 iCalendar (.ics) 字节流。"""
        cal = Calendar()
        cal.add("prodid", "-//法穿SI Copilot//Calendar Feed//CN")
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
                # 已完成的用 iCal 标准的 COMPLETED，订阅方（Apple/Google 日历）保留事件但不视为待办
                "status": "COMPLETED" if getattr(r, "is_completed", False) else "CONFIRMED",
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


def _make_vevent(props: dict[str, Any]) -> Event:
    """从字典构建 iCal Event 对象。"""
    ev = Event()
    for key, value in props.items():
        ev.add(key, value)
    return ev
