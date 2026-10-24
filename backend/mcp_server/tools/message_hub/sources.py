"""消息来源 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_message_sources() -> dict[str, Any]:
    """查询所有消息来源（邮箱等账号配置）列表。"""
    return list_result(client.get("/inbox/sources"))


def get_message_source(source_id: int) -> dict[str, Any]:
    """获取单个消息来源的详细配置（不含密码明文）。"""
    return client.get(f"/inbox/sources/{source_id}")  # type: ignore[no-any-return]


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
    """创建消息来源。credential_id 关联 Organization 中的账号凭证；poll_interval_minutes 为同步间隔。

    source_type 取值（**没有 ``email`` 这个值**,邮箱收件是 ``imap``）:
    ``imap`` IMAP 邮箱 / ``manual_upload`` 前端手动上传 /
    ``court_inbox`` 一张网收件箱 / ``court_schedule`` 一张网庭审日程。
    """
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
    return client.post("/inbox/sources", json=payload)  # type: ignore[no-any-return]


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
    """更新消息来源配置。只传需要修改的字段。

    Args:
        source_id: 消息来源 ID。
        display_name: 显示名称。
        is_enabled: 是否启用(停用后不再轮询)。
        poll_interval_minutes: 轮询间隔(分钟)。
        sync_since: 只同步该日期之后的邮件,YYYY-MM-DD。
        imap_host: IMAP 服务器地址。
        imap_account: IMAP 账号(与登录凭证可不同)。
        sender_whitelist: 发件人白名单(逗号分隔;空=不限)。
        sender_blacklist: 发件人黑名单(逗号分隔)。
    """
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
    return client.put(f"/inbox/sources/{source_id}", json=payload)  # type: ignore[no-any-return]


def delete_message_source(source_id: int) -> None:
    """删除消息来源——硬删除;其历史消息保留,但不再同步新消息。"""
    client.delete(f"/inbox/sources/{source_id}")


def sync_message_source(source_id: int) -> dict[str, Any]:
    """手动触发单个消息来源的同步任务。异步执行，返回任务状态。"""
    return client.post(f"/inbox/sources/{source_id}/sync")  # type: ignore[no-any-return]


def sync_all_message_sources() -> dict[str, Any]:
    """手动触发所有已启用的消息来源同步任务。异步执行。"""
    return client.post("/inbox/sources/sync-all")  # type: ignore[no-any-return]
