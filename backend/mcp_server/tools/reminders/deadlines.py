"""重要期限 MCP tools —— 跨案件/合同/日志的到期事项汇总。

## 为什么需要专用工具

``Reminder`` 是本系统唯一承载法定期限的模型，``reminder_type`` 已覆盖律师
真正在意的全部场景：

    开庭 hearing / 财产保全到期 asset_preservation_expires / 举证到期 evidence_deadline
    上诉期 appeal_deadline / 诉讼时效 statute_limitations / 缴费期限 payment_deadline
    补正提交 submission_deadline / 其他 other

但原有的 ``list_all_reminders`` 要求必须传 ``contract_id`` 或 ``case_log_id``，
且只认这两种目标（漏了 ``case_id``）。于是「未来 7 天全所到期事项」这种
律师最常问的问题无法回答——工具层面根本表达不出来。

本模块补两个能力：

- ``list_upcoming_deadlines(days, ...)``：按时间窗口跨案件/合同/日志聚合
- ``list_reminders_by_target``：按单个目标查（补齐 ``case_id``）

权限口径完全复用后端 ``reminder_read_scope``（可见案件/合同 + 本人创建的
全局提醒 + 管理员全量），不做任何放宽。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone

from mcp_server.client import client


def _parse_iso_date(value: str, field: str) -> date:
    """解析 YYYY-MM-DD（也接受完整 ISO 时间）。格式错时给出可读错误。"""
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:  # pragma: no cover - 由调用方参数校验兜底
        raise ValueError(f"{field} 须为 YYYY-MM-DD 格式，收到 {value!r}") from exc


def _deadline_brief(item: dict[str, Any]) -> dict[str, Any]:
    """把 Reminder 记录压成一行摘要，模型不用读整包 JSON。"""
    due_raw = str(item.get("due_at") or "")
    return {
        "id": item.get("id"),
        "type": item.get("reminder_type"),
        "content": item.get("content"),
        "due_at": due_raw,
        "is_completed": item.get("is_completed"),
        "case_id": item.get("case_id"),
        "contract_id": item.get("contract_id"),
        "case_log_id": item.get("case_log_id"),
    }


def list_upcoming_deadlines(
    days: int = 7,
    include_completed: bool = False,
    reminder_type: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """汇总未来 N 天内到期的全部重要日期（开庭、上诉期、保全到期、缴费期限等）。

    跨案件、合同、案件日志统一聚合，按到期时间升序返回。这是回答
    「未来一周有什么到期事项」「明天有开庭吗」这类问题的正确工具。

    Args:
        days: 向前看的天数，默认 7。传 0 表示只看今天。
        include_completed: 是否包含已完成的事项（默认 False，只看未完成）。
        reminder_type: 可选，只查某一类型（hearing / appeal_deadline /
            asset_preservation_expires / payment_deadline / evidence_deadline /
            statute_limitations / submission_deadline / other）。
        limit: 最多返回条数，默认 200。

    Returns:
        ``{from_date, to_date, days, total, items}``，``items`` 按 due_at 升序；
        每项含 ``id/type/content/due_at/is_completed/case_id/contract_id``。
    """
    today = timezone.localdate()
    window_end = today + timedelta(days=max(0, days))

    rows: list[dict[str, Any]] = client.get("/reminders/list", params={})  # type: ignore[assignment]
    if not isinstance(rows, list):
        # 后端形状变化时明确报错，不要静默返回空列表骗模型
        raise RuntimeError(f"/reminders/list 返回了非数组结构: {type(rows).__name__}")

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not include_completed and row.get("is_completed"):
            continue
        if reminder_type and row.get("reminder_type") != reminder_type:
            continue
        due_raw = str(row.get("due_at") or "")
        if not due_raw:
            continue
        try:
            due_date: date = datetime.fromisoformat(due_raw.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if today <= due_date <= window_end:
            items.append(_deadline_brief(row))

    items.sort(key=lambda item: str(item.get("due_at") or ""))
    capped = items[: max(1, limit)]

    return {
        "from_date": today.isoformat(),
        "to_date": window_end.isoformat(),
        "days": max(0, days),
        "total": len(items),
        "returned": len(capped),
        "truncated": len(items) > len(capped),
        "items": capped,
    }


def list_reminders_by_target(
    case_id: int | None = None,
    contract_id: int | None = None,
    case_log_id: int | None = None,
    include_completed: bool = True,
) -> dict[str, Any]:
    """按单个目标查询提醒（案件 / 合同 / 案件日志，三者至多传一个）。

    这是 ``list_all_reminders`` 的替代：后者漏了 ``case_id`` 且强制要求传参。
    三者都不传时返回当前用户可见范围内的全部提醒（与日历同口径）。

    Args:
        case_id: 案件 ID。
        contract_id: 合同 ID。
        case_log_id: 案件日志 ID。
        include_completed: 是否包含已完成（默认 True）。

    Returns:
        ``{total, items}``，``items`` 按 due_at 升序。
    """
    chosen = [value for value in (case_id, contract_id, case_log_id) if value is not None]
    if len(chosen) > 1:
        raise ValueError("case_id / contract_id / case_log_id 至多传一个")

    params: dict[str, Any] = {}
    if case_id is not None:
        params["case_id"] = case_id
    if contract_id is not None:
        params["contract_id"] = contract_id
    if case_log_id is not None:
        params["case_log_id"] = case_log_id

    rows: list[dict[str, Any]] = client.get("/reminders/list", params=params)  # type: ignore[assignment]
    if not isinstance(rows, list):
        raise RuntimeError(f"/reminders/list 返回了非数组结构: {type(rows).__name__}")

    items = [
        _deadline_brief(row)
        for row in rows
        if isinstance(row, dict) and (include_completed or not row.get("is_completed"))
    ]
    items.sort(key=lambda item: str(item.get("due_at") or ""))
    return {"total": len(items), "items": items}


def get_reminder_calendar(year: int = 0, month: int = 0) -> dict[str, Any]:
    """按月获取日历视图（日 → 事件），含工作台统计。

    与 ``list_upcoming_deadlines`` 的区别：本工具按**自然月**返回，且同一庭审
    被多次同步的情况后端已合并去重——做「这个月排期」类汇总时用它更准。

    Args:
        year: 年份，0 表示当前年。
        month: 月份 1-12，0 表示当前月。
    """
    params: dict[str, Any] = {}
    if year:
        params["year"] = year
    if month:
        params["month"] = month
    return client.get("/reminders/calendar", params=params)  # type: ignore[return-value]


def complete_reminders(reminder_ids: list[int], is_completed: bool = True) -> dict[str, Any]:
    """批量把提醒标记为已完成（或取消完成）。

    Args:
        reminder_ids: 提醒 ID 列表。
        is_completed: True 标记完成，False 取消完成。
    """
    return client.post(  # type: ignore[return-value]
        "/reminders/complete",
        json={"reminder_ids": reminder_ids, "is_completed": is_completed},
    )


def delete_reminders(reminder_ids: list[int]) -> dict[str, Any]:
    """批量删除提醒。

    Args:
        reminder_ids: 提醒 ID 列表。
    """
    return client.post("/reminders/delete", json={"reminder_ids": reminder_ids})  # type: ignore[return-value]
