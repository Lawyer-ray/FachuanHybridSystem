"""页图磁盘缓存：LRU（按 mtime）+ TTL + 总量上限，独立于附件目录。"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

#: 缓存存活时间与磁盘上限。
DEFAULT_CACHE_TTL_SECONDS = 7 * 24 * 3600
DEFAULT_CACHE_MAX_BYTES = 512 * 1024 * 1024

#: 各缓存根目录自上次 evict 以来的累计写入字节数（put 的 evict 节流依据）。
#: 必须跨实例共享：生产路径每次 _cache_store 都经 get_cache() 新建 RenderCache，
#: 实例级计数永远归零，节流会失效。
_pending_writes: dict[Path, int] = {}


class RenderCache:
    """页图磁盘缓存：LRU（按 mtime）+ TTL + 总量上限。

    键 = ``(attachment_id, page_no, dpi, format)`` 摘要成文件名。上传附件每次
    上传都落新 uuid 路径，attachment_id 与物理文件一一对应，不存在同 id 覆盖；
    文件夹引用把源文件 ``size``/``mtime`` 指纹编进 ``attachment_id``
    （见 ``folder_refs.render_folder_file_pages``），源文件更新后旧图自然失配。
    """

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_bytes: int = DEFAULT_CACHE_MAX_BYTES,
    ) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self.max_bytes = max_bytes

    def key(self, attachment_id: str, page_no: int, dpi: int, fmt: str) -> str:
        raw = f"{attachment_id}|{page_no}|{dpi}|{fmt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        # 两级散列目录：单目录塞几十万小文件会让 readdir 变慢
        return self.root / key[:2] / f"{key}.bin"

    def get(self, key: str, *, now: float | None = None) -> tuple[bytes, int, int] | None:
        path = self.path_for(key)
        try:
            stat = path.stat()
        except OSError:
            return None
        current = time.time() if now is None else now
        if current - stat.st_mtime > self.ttl_seconds:
            _unlink(path)
            return None
        try:
            payload = path.read_bytes()
        except OSError:
            return None
        # 首 8 字节存宽高（各 4 字节），省一次图片解码就知道尺寸
        if len(payload) < 8:
            _unlink(path)
            return None
        width = int.from_bytes(payload[0:4], "big")
        height = int.from_bytes(payload[4:8], "big")
        os.utime(path, None)  # 命中即刷新 mtime，实现「最久未用先淘汰」
        return payload[8:], width, height

    def put(self, key: str, image_bytes: bytes, width: int, height: int) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = width.to_bytes(4, "big") + height.to_bytes(4, "big")
        # 先写临时文件再 rename：并发读不会看到半截文件
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(header + image_bytes)
        tmp.replace(path)
        # 节流：累计写入达到总量上限才全目录扫描（原实现每 put 一次 rglob，
        # 渲染 20 页就是 20 次 O(缓存文件数)）。TTL 过期项在 get() 路径即时清理，
        # 磁盘上限本就是软钳制，晚一点扫描不影响渲染结果。
        pending = _pending_writes.get(self.root, 0) + len(header) + len(image_bytes)
        if pending >= self.max_bytes:
            self.evict()
        else:
            _pending_writes[self.root] = pending

    def evict(self, *, now: float | None = None) -> int:
        """按 TTL 删过期，再按 mtime 最旧先删直到总量达标；返回删除的条目数。"""
        _pending_writes.pop(self.root, None)
        current = time.time() if now is None else now
        entries: list[tuple[float, int, Path]] = []
        removed = 0
        for path in self.root.rglob("*.bin") if self.root.exists() else []:
            try:
                stat = path.stat()
            except OSError:
                continue
            if current - stat.st_mtime > self.ttl_seconds:
                _unlink(path)
                removed += 1
                continue
            entries.append((stat.st_mtime, stat.st_size, path))

        total = sum(size for _, size, _ in entries)
        if total <= self.max_bytes:
            return removed
        for _mtime, size, path in sorted(entries):
            _unlink(path)
            removed += 1
            total -= size
            if total <= self.max_bytes:
                break
        return removed

    def clear(self) -> None:
        _pending_writes.pop(self.root, None)
        for path in self.root.rglob("*.bin") if self.root.exists() else []:
            _unlink(path)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        # 缓存清理是尽力而为：文件可能已被其他进程（或上一个请求）先删掉。
        # 这类失败不影响渲染结果，走降级分支正常继续，记 debug 即可。
        logger.debug("删除渲染缓存文件失败（已忽略）: %s", path, exc_info=True)


def cache_root() -> Path:
    """缓存根目录：独立于 ``agent_attachments/``，见包 docstring。"""
    return Path(settings.MEDIA_ROOT) / "agent_attachment_cache"


def get_cache() -> RenderCache:
    return RenderCache(cache_root())


def _cache_lookup(attachment_id: str, page_no: int, dpi: int, fmt: str) -> tuple[bytes, int, int] | None:
    cache = get_cache()
    return cache.get(cache.key(attachment_id, page_no, dpi, fmt))


def _cache_store(attachment_id: str, page_no: int, dpi: int, fmt: str, payload: bytes, width: int, height: int) -> None:
    cache = get_cache()
    cache.put(cache.key(attachment_id, page_no, dpi, fmt), payload, width, height)
