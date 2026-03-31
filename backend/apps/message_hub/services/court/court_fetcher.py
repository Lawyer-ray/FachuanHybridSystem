"""一张网收件箱 fetcher — 占位，待实现。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.message_hub.services.base import MessageFetcher

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource


class CourtInboxFetcher(MessageFetcher):
    """一张网（zxfw.court.gov.cn）收件箱拉取器，待实现。"""

    def fetch_new_messages(self, source: MessageSource) -> int:
        raise NotImplementedError("一张网收件箱功能尚未实现")
