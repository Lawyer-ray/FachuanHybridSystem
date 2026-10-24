"""案件进展日志 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_case_logs(case_id: int, limit: int = 10) -> dict[str, Any]:
    """查询指定案件的进展日志，按时间倒序排列。

    日志条目以中文为主,JSON 转义后实测 ~1.8KB/条——默认取最近 10 条
    （≈18KB,贴着 pi 20KB 截断线）留在线内;要看更早的日志显式调大 limit。
    REST 端点 limit 上限 200。工具侧统一包成 ``{total, items}`` 信封
    (SDK 会把裸 list 逐项拆成独立文本块,空列表更是变成零内容块)。
    """
    return list_result(client.get("/cases/logs", params={"case_id": case_id, "limit": limit + 1}), limit=limit)


def create_case_log(case_id: int, content: str) -> dict[str, Any]:
    """为案件添加进展日志。content 为日志内容，支持多行文本。"""
    return client.post("/cases/logs", json={"case_id": case_id, "content": content})  # type: ignore[no-any-return]


def get_case_log(log_id: int) -> dict[str, Any]:
    """获取单条进展日志详情。"""
    return client.get(f"/cases/logs/{log_id}")  # type: ignore[no-any-return]


def update_case_log(log_id: int, content: str | None = None) -> dict[str, Any]:
    """修改一条进展日志的内容。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    return client.put(f"/cases/logs/{log_id}", json=payload)  # type: ignore[no-any-return]


def delete_case_log(log_id: int) -> None:
    """删除一条进展日志——硬删除,不可恢复。若日志带附件/材料引用,先确认。"""
    client.delete(f"/cases/logs/{log_id}")
