"""元典数据源的数据类型：检索条目、案例详情、会话。

``YuandianSearchItem`` / ``YuandianCaseDetail`` 实现 ``sources/base.py`` 的两个
``runtime_checkable`` Protocol，字段名与威科侧保持一致，executor 无需分支。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class YuandianSearchItem:
    """检索结果条目（对应 ``rh_ptal_search`` 响应的 ``data.lst[]`` 一行）。"""

    doc_id_raw: str
    doc_id_unquoted: str
    detail_url: str
    title_hint: str
    search_id: str
    module: str


@dataclass
class YuandianCaseDetail:
    """案例详情（对应 ``rh_case_details`` 响应的 ``data[0]``）。"""

    doc_id_raw: str
    doc_id_unquoted: str
    detail_url: str
    search_id: str
    module: str
    title: str
    court_text: str
    document_number: str
    judgment_date: str
    case_digest: str
    content_text: str
    raw_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class YuandianSession:
    """元典会话。

    元典是 header 鉴权（``X-API-Key``），**没有登录态**，所以会话里只有 key 池与
    HTTP 客户端：``api_keys`` / ``cursor`` / ``base_url`` 供传输层轮转取 key，
    ``task_id`` 由 executor 写入后用于日志串联。
    """

    api_keys: tuple[str, ...] = field(default=(), repr=False)
    cursor: int = 0
    base_url: str = ""
    task_id: str = ""
    concurrency_per_key: int = 2
    http_client: httpx.Client | None = field(default=None, repr=False)
    _key_slots: dict[str, threading.Semaphore] = field(default_factory=dict, repr=False)
    _key_slots_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def next_api_key(self) -> str:
        """按 ``cursor`` 轮转取下一把 key：限流/重试时请求自然分散到不同 key。"""
        if not self.api_keys:
            raise RuntimeError("元典会话没有可用 API Key")
        api_key = self.api_keys[self.cursor % len(self.api_keys)]
        self.cursor += 1
        return api_key

    @contextmanager
    def key_slot(self, api_key: str) -> Iterator[None]:
        """占用该 key 的一个并发槽位，上限 ``concurrency_per_key``。"""
        limit = max(1, int(self.concurrency_per_key or 1))
        with self._key_slots_lock:
            semaphore = self._key_slots.get(api_key)
            if semaphore is None:
                semaphore = threading.Semaphore(limit)
                self._key_slots[api_key] = semaphore
        semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()

    def close(self) -> None:
        """关闭底层 HTTP 客户端（executor 在 finally 里调用）。"""
        client = self.http_client
        self.http_client = None
        if client is None:
            return
        try:
            client.close()
        except (httpx.HTTPError, OSError, RuntimeError):
            logger.debug("关闭元典 HTTP 客户端失败（已忽略）", exc_info=True)
