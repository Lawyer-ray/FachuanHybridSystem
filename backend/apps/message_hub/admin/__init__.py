"""Admin init."""

from apps.message_hub.admin.inbox_message_admin import InboxMessageAdmin
from apps.message_hub.admin.message_source_admin import MessageSourceAdmin

__all__ = ["InboxMessageAdmin", "MessageSourceAdmin"]
