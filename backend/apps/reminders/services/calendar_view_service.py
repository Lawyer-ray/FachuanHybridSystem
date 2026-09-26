"""日历视图：把 Reminder 归一化成「日 → 事件」的日历数据。

这个模块是**首页工作台**与 **Django admin 提醒日历**共用的唯一事实来源。
以前两边各写一份（admin 在 reminder_admin.py，首页在前端 domain.ts），
必然漂移——实际就发现 admin 只按 source_id 合并，漏掉了「同一庭落了
两个相邻案号」那种情况。

这里只做纯逻辑，不碰 HTTP、不碰 Django ORM 查询条件：
调用方给「当月所有 Reminder + 当月上下文」，返回归一化好的日视图与统计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ..models import ReminderType

# ─── 事件类别（前端日历用） ─────────────────────────────────────────────────


class EventKind:
    """日历事件的四个类别。前两类为「紧要」，UI 上用红色强调。"""

    COURT = "court"
    DEADLINE = "deadline"
    MEETING = "meeting"
    FOLLOW = "follow"


#: 后端 ReminderType → 前端日历类别。8 种提醒归到 4 类。
KIND_BY_REMINDER_TYPE: dict[str, str] = {
    ReminderType.HEARING: EventKind.COURT,
    ReminderType.ASSET_PRESERVATION_EXPIRES: EventKind.DEADLINE,
    ReminderType.EVIDENCE_DEADLINE: EventKind.DEADLINE,
    ReminderType.APPEAL_DEADLINE: EventKind.DEADLINE,
    ReminderType.STATUTE_LIMITATIONS: EventKind.DEADLINE,
    ReminderType.PAYMENT_DEADLINE: EventKind.DEADLINE,
    ReminderType.SUBMISSION_DEADLINE: EventKind.DEADLINE,
    ReminderType.OTHER: EventKind.MEETING,
}

#: 类别中文名
KIND_LABEL: dict[str, str] = {
    EventKind.COURT: "庭期",
    EventKind.DEADLINE: "期限",
    EventKind.MEETING: "日程",
    EventKind.FOLLOW: "跟进",
}


def is_key_kind(kind: str) -> bool:
    """是否紧要（庭期 / 期限）"""
    return kind in (EventKind.COURT, EventKind.DEADLINE)


# ─── 归一化后的日历事件 ─────────────────────────────────────────────────────


@dataclass
class CalendarEventItem:
    """日历上的一条事件（已合并同一庭审的多条同步记录）。"""

    id: int
    kind: str
    kind_label: str
    #: 主标题 = 关联对象名，取不到才退回 reminder.content
    title: str
    #: reminder.content 原文（title 走了 target_name 时，这里仍保留）
    content: str
    day: str
    time: str
    time_range: str
    place: str
    person: str
    case_no: str
    hearing_type: str
    target_type: str
    target_name: str
    #: 关联案件 id（前端可据此跳案件详情）
    case_id: int | None
    #: 是否今天
    is_today: bool
    #: 是否已逾期
    is_overdue: bool
    #: 合并了几条原始 reminder（同一庭审被多次同步时 >1）
    members: int = 1
    #: 合并前各 reminder 的 id（点详情时用）
    member_ids: list[int] = field(default_factory=list)
    #: admin 用的编辑链接，由调用方按需填
    url: str = ""


# ─── 统计 ───────────────────────────────────────────────────────────────────


@dataclass
class CalendarStats:
    """工作台头部统计。全部按「合并后」的口径算。"""

    today: int = 0
    deadline_in_7days: int = 0
    month_court: int = 0


# ─── 内部中间态 ─────────────────────────────────────────────────────────────


@dataclass
class _Raw:
    """合并前的单条记录视图。"""

    item: CalendarEventItem
    #: 空串表示不参与合并（非庭审，或缺法庭信息）
    merge_key: str


def _text(value: Any) -> str:
    """metadata 取值：只认非空字符串。"""
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _target_of(reminder: Any) -> tuple[str, str]:
    """取关联对象的「类型 + 名称」。与 admin 口径一致，未绑定给空。"""
    contract = getattr(reminder, "contract", None)
    if getattr(reminder, "contract_id", None) is not None and contract is not None:
        target_name = _text(getattr(contract, "name", ""))
        if target_name:
            return "合同", target_name
    case = getattr(reminder, "case", None)
    if getattr(reminder, "case_id", None) is not None and case is not None:
        target_name = _text(getattr(case, "name", ""))
        if target_name:
            return "案件", target_name
    case_log = getattr(reminder, "case_log", None)
    if getattr(reminder, "case_log_id", None) is not None and case_log is not None:
        case_of_log = getattr(case_log, "case", None)
        case_name = _text(getattr(case_of_log, "name", ""))
        label = f"#{reminder.case_log_id}"
        if case_name:
            label = f"{label} {case_name}"
        return "案件日志", label
    return "", ""


def to_event_item(
    reminder: Any,
    *,
    today: date,
    now: datetime,
    tz: ZoneInfo,
) -> _Raw:
    """一条 Reminder → 归一化事件（未合并）。

    合并键只用「日 + 时段 + 法庭」：实测同一个庭会以多种形态重复同步——
    同 source_id、甚至 source_id 与案号都不同（一张网按律师分别落案）。
    案名在这种情况下不可靠（同庭两个案号的案名长短不一），法庭才是稳定标识。
    没有法庭信息时**不合并**，否则同时刻的手工庭会被并成一条。
    """
    kind = KIND_BY_REMINDER_TYPE.get(reminder.reminder_type, EventKind.FOLLOW)
    due_local = reminder.due_at.astimezone(tz)
    metadata = reminder.metadata if isinstance(reminder.metadata, dict) else {}

    place = _text(metadata.get("courtroom")) or _text(metadata.get("location"))
    content = (reminder.content or "").strip()
    target_type, target_name = _target_of(reminder)

    day = due_local.strftime("%Y-%m-%d")
    time_of_day = due_local.strftime("%H:%M")
    time_range = _text(metadata.get("time_range"))

    item = CalendarEventItem(
        id=reminder.id,
        kind=kind,
        kind_label=KIND_LABEL[kind],
        # title 优先用关联对象名：干净、结构化，且 content 常是工作笔记
        # （实测有 content='明天开庭' / '何伙案件，信宜开庭' 这种）
        title=target_name or content,
        content=content,
        day=day,
        time=time_of_day,
        time_range=time_range,
        place=place,
        person=_text(metadata.get("lawyer_name")) or _text(metadata.get("judge_name")),
        case_no=_text(metadata.get("ajbs")) or _text(metadata.get("ah")) or _text(metadata.get("case_no")),
        hearing_type=_text(metadata.get("hearing_type")),
        target_type=target_type,
        target_name=target_name,
        case_id=reminder.case_id,
        is_today=due_local.date() == today,
        is_overdue=reminder.due_at < now,
        member_ids=[reminder.id],
    )

    merge_key = ""
    if kind == EventKind.COURT and place:
        # 用 time_range 兜时间：有些庭审 due_at 是同步时刻而非开庭时刻
        merge_key = f"hearing|{day}|{time_range or time_of_day}|{place}"

    return _Raw(item=item, merge_key=merge_key)


def merge_events(raws: Iterable[_Raw]) -> list[CalendarEventItem]:
    """合并同一庭审的多条记录。

    - 保留首条的展示字段，律师姓名按出现顺序去重后用「、」聚合
    - 后续记录补首条缺失的字段（place / case_no / 案名 / case_id）
    - member_ids 累积全部原始 id，members 记条数
    """
    merged: list[CalendarEventItem] = []
    index: dict[str, CalendarEventItem] = {}
    persons: dict[str, list[str]] = {}

    for raw in raws:
        item = raw.item
        if not raw.merge_key:
            merged.append(item)
            continue
        hit = index.get(raw.merge_key)
        if hit is None:
            index[raw.merge_key] = item
            if item.person:
                persons.setdefault(raw.merge_key, [item.person])
            merged.append(item)
            continue
        # 已存在同一庭审 → 合并
        hit.members += 1
        hit.member_ids.append(item.id)
        if item.person:
            names = persons.setdefault(raw.merge_key, [])
            if item.person not in names:
                names.append(item.person)
            hit.person = "、".join(names)
        if not hit.place:
            hit.place = item.place
        if not hit.case_no:
            hit.case_no = item.case_no
        if not hit.time_range:
            hit.time_range = item.time_range
        if not hit.target_name:
            # 首条 content 潦草时（如「明天开庭」），用后续记录的案名补上
            hit.target_name = item.target_name
            hit.target_type = hit.target_type or item.target_type
            hit.title = item.target_name or hit.title
        if not hit.case_id:
            hit.case_id = item.case_id

    return merged


def sort_events(events: Iterable[CalendarEventItem]) -> list[CalendarEventItem]:
    """同日按时间升序，紧要事项排在前。"""

    def key(e: CalendarEventItem) -> tuple[int, str, int]:
        return (0 if is_key_kind(e.kind) else 1, e.time, e.id)

    return sorted(events, key=key)


def group_by_day(events: Iterable[CalendarEventItem]) -> dict[str, list[CalendarEventItem]]:
    """按 YYYY-MM-DD 归集；同一天内按时间升序、紧要排前。"""
    grouped: dict[str, list[CalendarEventItem]] = {}
    for e in events:
        grouped.setdefault(e.day, []).append(e)
    for day_events in grouped.values():
        day_events.sort(key=lambda e: (0 if is_key_kind(e.kind) else 1, e.time, e.id))
    return grouped


def compute_stats(events: Iterable[CalendarEventItem], *, today: date) -> CalendarStats:
    """工作台统计。全部基于合并后的事件。

    - today：当天的全部事件条数
    - deadline_in_7days：[today, today+6] 内到期的紧要事项（庭期/期限）
    - month_court：与 today 同月的庭期数
    """
    limit = today.toordinal() + 6
    month_prefix = today.strftime("%Y-%m")
    today_key = today.strftime("%Y-%m-%d")

    stats = CalendarStats()
    for e in events:
        if e.day == today_key:
            stats.today += 1
        if is_key_kind(e.kind):
            try:
                ordinal = datetime.strptime(e.day, "%Y-%m-%d").date().toordinal()
            except ValueError:  # pragma: no cover - day 由内部生成，不会失败
                continue
            if today.toordinal() <= ordinal <= limit:
                stats.deadline_in_7days += 1
        if e.kind == EventKind.COURT and e.day.startswith(month_prefix):
            stats.month_court += 1
    return stats
