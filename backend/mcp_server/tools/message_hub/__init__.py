"""收件箱域 tools 导出"""

from mcp_server.tools.message_hub.inbox import (
    download_inbox_attachment,
    get_inbox_message,
    list_inbox_messages,
    preview_inbox_attachment,
    rename_inbox_attachment,
)
from mcp_server.tools.message_hub.sources import (
    create_message_source,
    delete_message_source,
    get_message_source,
    list_message_sources,
    sync_all_message_sources,
    sync_message_source,
    update_message_source,
)

__all__ = [
    # 收件箱消息
    "list_inbox_messages",
    "get_inbox_message",
    "rename_inbox_attachment",
    "download_inbox_attachment",
    "preview_inbox_attachment",
    # 消息来源
    "list_message_sources",
    "get_message_source",
    "create_message_source",
    "update_message_source",
    "delete_message_source",
    "sync_message_source",
    "sync_all_message_sources",
]
