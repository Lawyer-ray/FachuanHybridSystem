"""消息来源 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_message_sources() -> list[dict[str, Any]]:
    """查询所有消息来源（邮箱配置）列表。"""
    return client.get("/inbox/sources")  # type: ignore[return-value]


def get_message_source(source_id: int) -> dict[str, Any]:
    """获取单个消息来源的详细配置信息。"""
    return client.get(f"/inbox/sources/{source_id}")  # type: ignore[return-value]


def create_message_source(
    display_name: str,
    source_type: str,
    credential_id: int,
    is_enabled: bool = True,
    poll_interval_minutes: int = 30,
    sync_since: str | None = None,
    imap_host: str | None = None,
    imap_account: str | None = None,
    sender_whitelist: str | None = None,
    sender_blacklist: str | None = None,
) -> dict[str, Any]:
    """创建消息来源。source_type 为 email 等；credential_id 关联 Organization 中的账号凭证；poll_interval_minutes 为同步间隔。"""
    payload: dict[str, Any] = {
        "display_name": display_name,
        "source_type": source_type,
        "credential_id": credential_id,
        "is_enabled": is_enabled,
        "poll_interval_minutes": poll_interval_minutes,
    }
    if sync_since:
        payload["sync_since"] = sync_since
    if imap_host:
        payload["imap_host"] = imap_host
    if imap_account:
        payload["imap_account"] = imap_account
    if sender_whitelist:
        payload["sender_whitelist"] = sender_whitelist
    if sender_blacklist:
        payload["sender_blacklist"] = sender_blacklist
    return client.post("/inbox/sources", json=payload)  # type: ignore[return-value]


def update_message_source(
    source_id: int,
    display_name: str | None = None,
    is_enabled: bool | None = None,
    poll_interval_minutes: int | None = None,
    sync_since: str | None = None,
    imap_host: str | None = None,
    imap_account: str | None = None,
    sender_whitelist: str | None = None,
    sender_blacklist: str | None = None,
) -> dict[str, Any]:
    """更新消息来源配置。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if display_name is not None:
        payload["display_name"] = display_name
    if is_enabled is not None:
        payload["is_enabled"] = is_enabled
    if poll_interval_minutes is not None:
        payload["poll_interval_minutes"] = poll_interval_minutes
    if sync_since is not None:
        payload["sync_since"] = sync_since
    if imap_host is not None:
        payload["imap_host"] = imap_host
    if imap_account is not None:
        payload["imap_account"] = imap_account
    if sender_whitelist is not None:
        payload["sender_whitelist"] = sender_whitelist
    if sender_blacklist is not None:
        payload["sender_blacklist"] = sender_blacklist
    return client.put(f"/inbox/sources/{source_id}", json=payload)  # type: ignore[return-value]


def delete_message_source(source_id: int) -> None:
    """删除指定消息来源。此操作不可逆。"""
    client.delete(f"/inbox/sources/{source_id}")


def sync_message_source(source_id: int) -> dict[str, Any]:
    """手动触发单个消息来源的同步任务。异步执行，返回任务状态。"""
    return client.post(f"/inbox/sources/{source_id}/sync")  # type: ignore[return-value]


def sync_all_message_sources() -> dict[str, Any]:
    """手动触发所有已启用的消息来源同步任务。异步执行。"""
    return client.post("/inbox/sources/sync-all")  # type: ignore[return-value]
