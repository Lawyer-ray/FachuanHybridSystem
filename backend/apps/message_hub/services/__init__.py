"""Services init — fetcher 工厂。

IMAP 与通用能力由本 app 提供；「一张网收件箱 / 庭审日程」适配器
由 plugins/message_hub/services/court/ 提供（懒加载）。
"""

from __future__ import annotations

from apps.message_hub.services.base import MessageFetcher


def get_fetcher(source_type: str) -> MessageFetcher:
    from apps.message_hub.models import SourceType
    from apps.message_hub.services.imap.imap_fetcher import ImapFetcher

    if source_type == SourceType.IMAP:
        return ImapFetcher()

    if source_type == SourceType.MANUAL_UPLOAD:
        from apps.message_hub.services.manual_upload_service import ManualUploadFetcher

        return ManualUploadFetcher()

    # 一张网适配器位于 plugins（独立子模块），按需懒加载
    from plugins.message_hub.services.court.court_fetcher import CourtInboxFetcher
    from plugins.message_hub.services.court.court_schedule_fetcher import CourtScheduleFetcher

    if source_type == SourceType.COURT_INBOX:
        return CourtInboxFetcher()
    if source_type == SourceType.COURT_SCHEDULE:
        return CourtScheduleFetcher()
    raise ValueError(f"未知来源类型: {source_type}")


__all__ = ["MessageFetcher", "get_fetcher"]
