"""MessageFetcher 抽象基类。"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource


class MessageFetcher(abc.ABC):
    @abc.abstractmethod
    def fetch_new_messages(self, source: MessageSource) -> int:
        """拉取新消息，返回新增数量。"""
        ...

    def download_attachment(self, source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        """
        按需下载附件。

        Returns:
            (content_bytes, filename, content_type)
        """
        raise NotImplementedError
