"""MessageFetcher 抽象基类。"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource


def resolve_media_attachment_path(raw: str) -> Path | None:
    """解析附件 local_path，兼容历史数据里的跨环境绝对路径（WSL ↔ Windows）。

    用户机器可能同时存在 WSL（/mnt/d/...）与 Windows（D:\\...）两套运行环境，
    同一目录在不同进程里坐标不同，绝对路径互相不可见。这里按 MEDIA_ROOT
    归一化后再拼接，两个环境都能命中同一份文件。
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    media_root = Path(settings.MEDIA_ROOT).resolve()
    raw_path = Path(raw)

    # 1. 原样尝试（本环境写入的绝对/相对路径）
    if raw_path.exists():
        return raw_path

    # 2. 历史绝对路径：截取 "/media/" 之后的部分，按当前 MEDIA_ROOT 重拼。
    #    /mnt/d/<proj>/backend/apiSystem/media/xxx ↔ D:\<proj>\backend\apiSystem\media\xxx
    normalized = raw.replace("\\", "/")
    if "/media/" in normalized:
        tail = normalized.split("/media/", 1)[1]
        candidate = media_root / tail
        if candidate.exists():
            return candidate

    # 3. 兜底：当作相对 MEDIA_ROOT 的路径
    candidate = media_root / raw.lstrip("/")
    if candidate.exists():
        return candidate

    return None


def media_relative_path(abs_path: Path) -> str:
    """把附件绝对路径转为相对 MEDIA_ROOT 的 POSIX 相对路径（跨 WSL/Windows 可读）。"""
    try:
        return Path(abs_path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
    except ValueError:
        return str(abs_path)


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
