"""Services init — fetcher 工厂。"""

from __future__ import annotations

from apps.message_hub.services.base import MessageFetcher


def get_fetcher(source_type: str) -> MessageFetcher:
    from apps.message_hub.models import SourceType
    from apps.message_hub.services.court.court_fetcher import CourtInboxFetcher
    from apps.message_hub.services.court.court_schedule_fetcher import CourtScheduleFetcher
    from apps.message_hub.services.imap.imap_fetcher import ImapFetcher

    if source_type == SourceType.IMAP:
        return ImapFetcher()
    if source_type == SourceType.COURT_INBOX:
        return CourtInboxFetcher()
    if source_type == SourceType.COURT_SCHEDULE:
        return CourtScheduleFetcher()
    raise ValueError(f"未知来源类型: {source_type}")


__all__ = ["MessageFetcher", "get_fetcher"]
