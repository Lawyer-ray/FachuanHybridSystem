"""催收提醒 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_all_reminders(
    contract_id: int | None = None,
    case_log_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """查询提醒列表,可按 contract_id（合同ID）或 case_log_id（案件日志ID）过滤,
    都不传则返回可见范围全部（提醒 DTO 较肥,实测 ~0.72KB/条,默认截前 20 条
    留在 pi 20KB 截断线内;``total`` 是完整条数）。跨案件的到期汇总请用
    ``list_upcoming_deadlines``,按目标精确查（含 case_id）请用
    ``list_reminders_by_target``。"""
    params: dict[str, Any] = {}
    if contract_id is not None:
        params["contract_id"] = contract_id
    if case_log_id is not None:
        params["case_log_id"] = case_log_id
    return list_result(client.get("/reminders/list", params=params), limit=limit)


def get_reminder(reminder_id: int) -> dict[str, Any]:
    """获取单个提醒详情（类型、内容、关联对象、状态）。"""
    return client.get(f"/reminders/{reminder_id}")  # type: ignore[no-any-return]


def create_new_reminder(
    reminder_type: str,
    content: str,
    due_at: str,
    contract_id: int | None = None,
    case_log_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建提醒。due_at 为到期时间（ISO格式如 2026-03-15T10:00:00）；reminder_type 常用值：call（电话）、visit（上门）、letter（律师函）。"""
    payload: dict[str, Any] = {
        "reminder_type": reminder_type,
        "content": content,
        "due_at": due_at,
    }
    if contract_id is not None:
        payload["contract_id"] = contract_id
    if case_log_id is not None:
        payload["case_log_id"] = case_log_id
    if metadata is not None:
        payload["metadata"] = metadata
    return client.post("/reminders/create", json=payload)  # type: ignore[no-any-return]


def update_reminder(
    reminder_id: int,
    reminder_type: str | None = None,
    content: str | None = None,
    due_at: str | None = None,
) -> dict[str, Any]:
    """更新提醒（改内容/时间/类型）。只传需要修改的字段。

    完成/取消完成走 ``complete_reminders``（批量接口）——旧签名的
    ``is_done`` 参数从未生效（端点 ``ReminderUpdate`` 无此字段,
    2026-10-25 移除）。

    Args:
        reminder_id: 提醒 ID。
        reminder_type: 提醒类型(如 deadline/hearing——同 list_all_reminders 返回的取值)。
        content: 提醒内容文本。
        due_at: 到期时间,ISO 8601(如 2026-11-01T09:00:00)。
    """
    payload: dict[str, Any] = {}
    if reminder_type is not None:
        payload["reminder_type"] = reminder_type
    if content is not None:
        payload["content"] = content
    if due_at is not None:
        payload["due_at"] = due_at
    return client.put(f"/reminders/{reminder_id}", json=payload)  # type: ignore[no-any-return]


def delete_reminder(reminder_id: int) -> None:
    """删除提醒——硬删除,不可恢复。"""
    client.delete(f"/reminders/{reminder_id}")


def list_reminder_types() -> dict[str, Any]:
    """获取支持的提醒类型枚举——创建提醒前查合法值。"""
    return list_result(client.get("/reminders/types"))


def parse_reminders_from_text(text: str) -> dict[str, Any]:
    """从自由文本中解析提醒条目。返回 {total, items} 信封（items 每条含 content、type、due_at）。"""
    return list_result(client.post("/reminders/parse", json={"text": text}))


def get_target_options(q: str = "") -> dict[str, Any]:
    """搜索可关联提醒的目标（合同、案件、案件日志）。q 为关键词筛选。"""
    params: dict[str, Any] = {}
    if q:
        params["q"] = q
    return client.get("/reminders/target-options", params=params)  # type: ignore[no-any-return]
