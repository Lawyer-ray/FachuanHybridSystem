"""联系人域 tools 导出"""

from mcp_server.tools.contacts.contacts import (
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
    search_contacts,
    update_contact,
)

__all__ = [
    "list_contacts",
    "create_contact",
    "search_contacts",
    "get_contact",
    "update_contact",
    "delete_contact",
]
