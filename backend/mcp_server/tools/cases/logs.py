"""案件进展日志 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_logs(case_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """查询指定案件的进展日志，按时间倒序排列。

    后端 ``/cases/logs`` 声明 ``response=list[CaseLogOut]``，返回裸数组
    （limit 分页,REST 默认 200）。这里默认 100——长案卷动辄数百条日志,
    全量灌进模型上下文会挤爆;需要更早的日志时显式调大 limit。

    早前这里声明 ``dict`` 并用 ``as_items`` 包一层分页壳，但那只是掩盖了
    类型不符（分页壳里的 ``items`` 是模型永远看不到的假结构）。
    """
    return client.get("/cases/logs", params={"case_id": case_id, "limit": limit})  # type: ignore[return-value]


def create_case_log(case_id: int, content: str) -> dict[str, Any]:
    """为案件添加进展日志。content 为日志内容，支持多行文本。"""
    return client.post("/cases/logs", json={"case_id": case_id, "content": content})  # type: ignore[return-value]


def get_case_log(log_id: int) -> dict[str, Any]:
    """获取单条进展日志详情。"""
    return client.get(f"/cases/logs/{log_id}")  # type: ignore[return-value]


def update_case_log(log_id: int, content: str | None = None) -> dict[str, Any]:
    """修改一条进展日志的内容。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    return client.put(f"/cases/logs/{log_id}", json=payload)  # type: ignore[return-value]


def delete_case_log(log_id: int) -> None:
    """删除一条进展日志——硬删除,不可恢复。若日志带附件/材料引用,先确认。"""
    client.delete(f"/cases/logs/{log_id}")
