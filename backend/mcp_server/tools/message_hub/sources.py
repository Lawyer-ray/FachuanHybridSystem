"""消息来源 MCP tools"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_message_sources() -> dict[str, Any]:
    """查询所有消息来源（邮箱等账号配置）列表。"""
    return list_result(client.get("/inbox/sources"))


def get_message_source(source_id: int) -> dict[str, Any]:
    """获取单个消息来源的详细配置（不含密码明文）。"""
    return client.get(f"/inbox/sources/{source_id}")  # type: ignore[no-any-return]


def create_message_source(
    display_name: Annotated[str, Field(description="来源显示名称")],
    source_type: Annotated[
        Literal["imap", "manual_upload", "court_inbox", "court_schedule", "client_upload"],
        Field(description="来源类型:imap IMAP 邮箱(没有 email 这个值)/manual_upload 前端手动上传/court_inbox 一张网收件箱/court_schedule 一张网庭审日程"),
    ],
    credential_id: Annotated[int, Field(description="关联 Organization 的账号凭证 ID", ge=1)],
    is_enabled: Annotated[bool, Field(description="是否启用(启用后按间隔轮询同步)")] = True,
    poll_interval_minutes: Annotated[int, Field(description="同步间隔分钟数(默认 30)", ge=1)] = 30,
    sync_since: Annotated[str | None, Field(description="仅同步该日期之后的邮件,YYYY-MM-DD(可选)")] = None,
    imap_host: Annotated[str | None, Field(description="IMAP 服务器地址(source_type=imap 时用,可选)")] = None,
    imap_account: Annotated[str | None, Field(description="IMAP 账号(source_type=imap 时用,可选)")] = None,
    sender_whitelist: Annotated[str | None, Field(description="发件人白名单(可选,逗号分隔)")] = None,
    sender_blacklist: Annotated[str | None, Field(description="发件人黑名单(可选,逗号分隔)")] = None,
) -> dict[str, Any]:
    """创建消息来源。credential_id 关联 Organization 中的账号凭证；poll_interval_minutes 为同步间隔。

    source_type 取值（**没有 ``email`` 这个值**,邮箱收件是 ``imap``）:
    ``imap`` IMAP 邮箱 / ``manual_upload`` 前端手动上传 /
    ``court_inbox`` 一张网收件箱 / ``court_schedule`` 一张网庭审日程 /
    ``client_upload`` 客户链接上传。

    ``client_upload`` 由系统在首次使用客户上传链接时自动创建，**一般不需要
    手动建**；列在这里是为了 schema 与 `SourceType` 保持同源（模型加值而工具
    漏加，调用方会收到「取值非法」却看不出该传什么）。
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
    source_id: Annotated[int, Field(description="消息来源 ID", ge=1)],
    display_name: Annotated[str | None, Field(description="显示名称(不改不传)")] = None,
    is_enabled: Annotated[bool | None, Field(description="是否启用(停用后不再轮询;不改不传)")] = None,
    poll_interval_minutes: Annotated[int | None, Field(description="轮询间隔分钟数", ge=1)] = None,
    sync_since: Annotated[str | None, Field(description="只同步该日期之后的邮件,YYYY-MM-DD")] = None,
    imap_host: Annotated[str | None, Field(description="IMAP 服务器地址")] = None,
    imap_account: Annotated[str | None, Field(description="IMAP 账号(与登录凭证可不同)")] = None,
    sender_whitelist: Annotated[str | None, Field(description="发件人白名单(逗号分隔;空=不限)")] = None,
    sender_blacklist: Annotated[str | None, Field(description="发件人黑名单(逗号分隔)")] = None,
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
