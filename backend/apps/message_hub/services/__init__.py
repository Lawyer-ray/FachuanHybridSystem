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

    # S42-01（2026-11-23 二轮审计）：原实现只给 MANUAL_UPLOAD 建了分支，客户链接上传
    # （CLIENT_UPLOAD）落到最后的 `raise ValueError("未知来源类型")`，于是律师打开
    # 「客户链接上传」产生的材料包、点任意附件预览/下载必 500。
    # CLIENT_UPLOAD 与手动上传同构：附件已经由 `save_upload_files_as_metas` 落到本地
    # media（`manual_upload_service.py`），`download_attachment` 只是按
    # `attachments_meta[].local_path` 读回字节，没有任何 IMAP/网络拉取动作，故直接复用。
    if source_type in (SourceType.MANUAL_UPLOAD, SourceType.CLIENT_UPLOAD):
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
