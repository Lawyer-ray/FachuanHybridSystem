"""Agent 路径共用的 HTTP 客户端。

要同时满足两个约束，缺一不可：

1. **不能每请求新建客户端**。``build_model`` 是每次请求都会调用的，原先每次都
   ``httpx2.AsyncClient(...)`` 并追加进一个只增不减的全局列表 —— 长跑必然耗尽
   文件描述符。
2. **不能简单地做成全局单例**。httpx 的连接池与**首次使用它的那个事件循环**
   绑定，跨循环复用会抛 ``RuntimeError: Event loop is closed``（已实测：同一客户端
   在第二个 ``asyncio.run()`` 里就失败）。而 ``build_model`` 是在 ``sync_to_async``
   的线程池里构造客户端的（那里没有运行中的循环），pytest-asyncio 还会给每个用例
   新建循环。

因此：**客户端进程级单例，把连接池下沉到按事件循环持有的 transport 里**。
每个循环各得一个池（与原先"每请求一个客户端"的连接复用能力等价甚至更好），
跨循环复用不再有隐患，总量也不再增长。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

import httpx2

logger = logging.getLogger(__name__)


class LoopScopedTransport(httpx2.AsyncBaseTransport):
    """按事件循环持有底层 transport 的包装器（每个循环各自一个连接池）。"""

    def __init__(self, factory: Callable[[], httpx2.AsyncBaseTransport]) -> None:
        """初始化。

        Args:
            factory: 为单个事件循环创建底层 transport 的工厂，按需调用。
        """
        self._factory = factory
        self._by_loop: dict[int, tuple[asyncio.AbstractEventLoop, httpx2.AsyncBaseTransport]] = {}

    @property
    def pool_count(self) -> int:
        """已建立的连接池数量（等于用过的存活事件循环数），供测试与监控观察。"""
        return len(self._by_loop)

    def _for_running_loop(self) -> httpx2.AsyncBaseTransport:
        loop = asyncio.get_running_loop()
        entry = self._by_loop.get(id(loop))
        if entry is None:
            inner = self._factory()
            # 同时持有 loop 引用：id() 会在对象回收后被复用，只存 id 会张冠李戴
            self._by_loop[id(loop)] = (loop, inner)
            return inner
        return entry[1]

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await self._for_running_loop().handle_async_request(request)

    async def aclose(self) -> None:
        """尽力关闭各循环的连接池；已结束的循环其连接随循环销毁，跳过即可。"""
        pending = list(self._by_loop.values())
        self._by_loop.clear()
        for loop, inner in pending:
            if loop.is_closed():
                continue
            try:
                await inner.aclose()
            except RuntimeError:
                logger.debug("跳过已失效事件循环的连接池关闭", exc_info=True)


_client: httpx2.AsyncClient | None = None
_client_lock = threading.Lock()


def shared_http_client() -> httpx2.AsyncClient:
    """返回 Agent 路径共用的 HTTP 客户端（进程级单例）。

    注意：**不要在请求结束后关闭它**。它是全进程共用的，关掉会让后续请求全部失败；
    连接池由 :class:`LoopScopedTransport` 按事件循环管理。
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx2.AsyncClient(transport=LoopScopedTransport(httpx2.AsyncHTTPTransport))
    return _client


def shared_transport() -> LoopScopedTransport | None:
    """返回当前共享客户端所用的 :class:`LoopScopedTransport`。

    供测试与诊断确认「按事件循环隔离连接池」这条接线确实生效；
    客户端尚未创建时返回 ``None``。
    """
    client = _client
    if client is None:
        return None
    transport = client._transport  # 本模块自己装配的 transport
    return transport if isinstance(transport, LoopScopedTransport) else None


def reset_shared_http_client() -> None:
    """丢弃单例，下次调用时重建。

    仅供测试。**不关闭**旧客户端：它的连接池属于可能已经结束的事件循环，
    在别的循环里 await 关闭会抛 ``RuntimeError: Event loop is closed``。
    """
    global _client
    with _client_lock:
        _client = None
