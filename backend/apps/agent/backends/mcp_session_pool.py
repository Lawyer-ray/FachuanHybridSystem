"""openai-agents 的 MCP 连接常驻化：「每轮重连 434 个工具」→「进程内复用」。

## 为什么需要它（实测账）

同一问题三 agent 同问的首字延迟（见任务实测数据）：裸 SDK（MCP 预连）2.82s，
真连 MCP 5.76s —— **建连 + ``initialize`` + ``tools/list`` 花掉约 2.9s**。
每轮 ``async with server`` 都重跑一遍这条链路，而工具面在进程生命周期内几乎不变。

## 红线：Authorization 里是律师 token，连接绝不能跨律师共用

:8011 强制每请求 Bearer（``mcp_server/identity.py``），且**刻意不回退服务账号**
（越权修复）。MCP 的 streamable-http transport 把 ``Authorization`` 写在**连接**
（也就是 ``ClientSession`` 所在的那条 HTTP 客户端）上，不是每个请求现带。所以：

- 池的键是 ``(endpoint URL, sha256(token))`` ——**绝不存明文 token 做键**；
- 不同律师的 token → 不同的桶 → 不同的连接，物理上不存在「拿到别人那条
  连接」的代码路径；
- 同 token 哈希也意味着同一个人换设备/换会话**共用**同一条连接，这是期望行为。

## 为什么是「池」而不是「单连接」

MCP v2（当前 venv 里是 ``mcp 2.2.0``）支持一条会话上并发请求，SDK 的
``_serialize_session_requests = not MCP_V2`` 就是据此决定要不要在客户端串行化。
即便如此这里仍做成**按桶的连接池**而不是「每 token 一条」：

1. 一条连接断掉（服务端重启 / 网关掐长连接）会**同时**毁掉正在用它的所有轮；
   池里有多条时一次只坏一条，其余照跑。
2. 台账（``leases``）让「什么时候可以关」有明确依据，避免「用着被人关掉」。

## 生命周期

- 取用时 ``lease`` +1，释放时 -1；**不立刻关**（立刻关就等于没复用）。
- 桶内空闲连接在 :data:`IDLE_TTL_SECONDS` 后回收（``asyncio`` 定时）；
  桶内最多 :data:`MAX_PER_BUCKET` 条，多的直接关掉。
- 连接失效（``connect()`` 抛异常 / 中途 transport 报错）→ 从池里摘掉、
  关掉、**下一次取用重新建**。不重试本轮：重连要几秒，用户已经等着了，
  失败一次就降级为「本轮无工具」。

## 兜底：失败一律降级为「无工具但能对话」

与 ``_connectable_mcp`` 的原口径一致——工具面缺失是用户可感知的能力变化
（记 warning），但「本来能对话」不能变成「整轮失败」。
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from agents.mcp import MCPServerStreamableHttp

logger = logging.getLogger(__name__)

#: 单条连接空闲多久后可以回收（秒）。取 600s：律师的提问通常集中在几分钟内，
#: 太长会让「换了网关 / MCP 重启」的旧连接一直占着池位；太短则刚热起来就被关。
IDLE_TTL_SECONDS = 600.0

#: 每个 token 桶最多留几条连接。同一律师并发两轮时各拿一条，互不干扰；
#: 再多的并发直接复用已有连接（MCP v2 支持会话内并发请求）。
MAX_PER_BUCKET = 2

#: 单个桶的空闲连接空闲多久后回收。与 ``IDLE_TTL_SECONDS`` 同值，单列出来
#: 是为了让「桶的存在」也有超时：律师下次登录若换了 token，旧桶不该永久留着。
BUCKET_TTL_SECONDS = IDLE_TTL_SECONDS

#: 池里最多几个桶。超过时按「最久没用」淘汰（连同其空闲连接一起关）。
MAX_BUCKETS = 32


def token_fingerprint(user_token: str) -> str:
    """token → 不可逆指纹（sha256 十六进制）。

    用它做池键而不是明文 token：字典键会进 repr、进 ``logging`` 的调试输出、
    进异常栈里的局部变量展示。指纹泄漏也反推不出 token，且做不了「拿指纹当
    Bearer 用」。
    """
    return hashlib.sha256(user_token.encode("utf-8")).hexdigest()


@dataclass
class PooledMCPServer:
    """池里的一条连接及其台账。"""

    server: MCPServerStreamableHttp
    #: 正在使用这条连接的轮数。>0 时**不得**关闭。
    leases: int = 0
    #: 最后一次被取用/释放的单调时间（秒），用于空闲回收。
    last_used: float = field(default_factory=time.monotonic)
    #: 已关闭标记：``cleanup`` 是异步且可能失败，靠这个标记保证只关一次。
    closed: bool = False


@dataclass
class _Bucket:
    servers: list[PooledMCPServer] = field(default_factory=list)
    last_used: float = field(default_factory=time.monotonic)


class McpSessionPool:
    """``(url, token 指纹)`` → 已连接的 ``MCPServerStreamableHttp`` 的进程内池。

    **只在事件循环线程里使用**（``dict`` 的读写不需要额外锁，因为
    ``asyncio`` 单线程执行且这里没有 ``await`` 跨越临界区）。跨线程调用会破坏
    这个前提——所以 :class:`~apps.agent.backends.openai_agents_backend.OpenAiAgentsBackend`
    只在 ``stream()`` 的协程里碰它。
    """

    def __init__(
        self,
        *,
        max_per_bucket: int = MAX_PER_BUCKET,
        max_buckets: int = MAX_BUCKETS,
        idle_ttl_seconds: float = IDLE_TTL_SECONDS,
        bucket_ttl_seconds: float = BUCKET_TTL_SECONDS,
    ) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        # 淘汰桶时摘下来、等下一次 ``sweep``/``close_all`` 真正关闭的连接。
        # 单独一个列表是因为关连接要 ``await``，而摘桶发生在 ``acquire`` 的
        # 无 await 临界区里（见 ``_evict_overflow_buckets``）。
        self._pending_close: list[MCPServerStreamableHttp] = []
        self._max_per_bucket = max(1, max_per_bucket)
        self._max_buckets = max(1, max_buckets)
        self._idle_ttl = idle_ttl_seconds
        self._bucket_ttl = bucket_ttl_seconds

    # ── 观测（测试与诊断） ───────────────────────────────────────────────

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    def connection_count(self, *, url: str, user_token: str) -> int:
        bucket = self._buckets.get((url, token_fingerprint(user_token)))
        return 0 if bucket is None else len(bucket.servers)

    def leased_count(self, *, url: str, user_token: str) -> int:
        bucket = self._buckets.get((url, token_fingerprint(user_token)))
        if bucket is None:
            return 0
        return sum(1 for item in bucket.servers if item.leases > 0 and not item.closed)

    # ── 核心：取用 / 归还 ────────────────────────────────────────────────

    async def acquire(
        self,
        *,
        url: str,
        user_token: str,
        factory: Any,
    ) -> PooledMCPServer | None:
        """取一条**属于该 token** 的已连接会话；建连失败返回 ``None``。

        取用前先 :meth:`sweep`：代码原本只在 docstring 里写「每次取用时顺手
        扫一遍」，但实际从未调用（全仓 0 个调用点）——后果是空闲连接与
        溢出桶永不回收（token 轮换后旧连接在其进程生命周期内一直挂着）。

        Args:
            url: MCP endpoint（``http://host:port/mcp``）。池键的一部分：同一个人
                连不同 endpoint 不能共用连接。
            user_token: 本轮律师的 access token（**不得进日志**，只取其指纹）。
            factory: ``Callable[[], MCPServerStreamableHttp]``，用来新建未连接的
                客户端。抽成参数是为了让测试塞替身，且让本模块不依赖
                ``build_mcp_server`` 的 ``tool_filter`` / 超时常量。

        Returns:
            已 ``connect()`` 的 :class:`PooledMCPServer`（``leases`` 已 +1），
            调用方**必须**在 ``finally`` 里 :meth:`release`。建连失败返回 ``None``
            ——调用方据此降级为「本轮无工具」（与原来 ``port_open`` 为假同口径）。
        """
        # 先把超时空闲连接与溢出桶扫掉（见本方法 docstring）。失败不影响取用：
        # 回收是「收拾房间」，不是「能不能住」的前提。
        with suppress(Exception):
            await self.sweep()

        if not (user_token or "").strip():
            # 无 token 就没有身份可言，连上去只会 401。调用方本应先判，这里再兜一层：
            # 「空 token 也能拿到别人的连接」是最严重的一类串号，宁可不给。
            return None

        key = (url, token_fingerprint(user_token))
        bucket = self._buckets.get(key)
        if bucket is None:
            self._evict_overflow_buckets(keep=key)
            bucket = _Bucket()
            self._buckets[key] = bucket

        # 优先复用空闲的一条；都在用且未到上限就新建（并发两轮各拿一条，
        # 免得它们挤在一条连接上互相拖慢——MCP v2 虽支持会话内并发，
        # 但不代表一条连接上的多个工具调用不会排队在同一个 SSE 流上）。
        idle = next((item for item in bucket.servers if item.leases == 0 and not item.closed), None)
        if idle is not None:
            idle.leases += 1
            idle.last_used = time.monotonic()
            bucket.last_used = idle.last_used
            return idle

        if len(bucket.servers) >= self._max_per_bucket and bucket.servers:
            # 满了：退而求其次复用最久没用的那条（MCP v2 支持并发请求）。
            oldest = min(bucket.servers, key=lambda item: item.last_used)
            oldest.leases += 1
            oldest.last_used = time.monotonic()
            bucket.last_used = oldest.last_used
            return oldest

        server = factory()
        try:
            await server.connect()
        except Exception:
            # 建连失败：把半连上的对象关掉（SDK 的 connect 内部已 cleanup 过一次，
            # 这里再兜一次不会有害——cleanup 是幂等的），然后让调用方降级。
            await self._safe_close(server)
            logger.warning("MCP 连接建立失败，本轮降级为无业务工具（下一轮重试）", exc_info=True)
            return None

        pooled = PooledMCPServer(server=server, leases=1)
        bucket.servers.append(pooled)
        bucket.last_used = pooled.last_used
        return pooled

    def release(self, *, url: str, user_token: str, pooled: PooledMCPServer) -> None:
        """归还一条连接（**不关闭**，只把台账减一）。

        刻意不在这里 ``await cleanup()``：关掉就等于没有复用。真正关闭发生在
        空闲超时回收、桶淘汰、或连接自身失效时（见 :meth:`_safe_close`）。
        """
        key = (url, token_fingerprint(user_token))
        bucket = self._buckets.get(key)
        now = time.monotonic()
        if bucket is not None:
            bucket.last_used = now
        if pooled.leases > 0:
            pooled.leases -= 1
        pooled.last_used = now

    async def discard(self, *, url: str, user_token: str, pooled: PooledMCPServer) -> None:
        """连接已失效：从池里摘掉并关闭。

        调用方在 ``call_tool`` / ``list_tools`` 出现 transport 错误时调用——
        留着一条坏连接只会让下一轮也失败一次（每次失败都要等超时）。
        """
        self.release(url=url, user_token=user_token, pooled=pooled)
        key = (url, token_fingerprint(user_token))
        bucket = self._buckets.get(key)
        if bucket is not None:
            bucket.servers = [item for item in bucket.servers if item is not pooled]
        await self._safe_close(pooled.server)

    # ── 回收 / 关闭 ─────────────────────────────────────────────────────

    async def sweep(self, *, now: float | None = None) -> int:
        """回收空闲超时的连接与空桶；返回被关掉的数量。

        不跑后台定时任务，而是**在每次取用时顺手扫一遍**：进程里没有「谁负责
        定时」的问题（也不需要为测试注入假时钟），代价是一次几十项的列表遍历。
        """
        now = time.monotonic() if now is None else now
        closed = 0
        pending, self._pending_close = self._pending_close, []
        for server in pending:
            await self._safe_close(server)
            closed += 1
        for key in list(self._buckets):
            bucket = self._buckets[key]
            keep: list[PooledMCPServer] = []
            for item in bucket.servers:
                idle_too_long = item.leases == 0 and (now - item.last_used) >= self._idle_ttl
                if item.closed or idle_too_long:
                    if not item.closed:
                        await self._safe_close(item.server)
                        closed += 1
                    continue
                keep.append(item)
            bucket.servers = keep
            empty_too_long = not keep and (now - bucket.last_used) >= self._bucket_ttl
            if empty_too_long:
                self._buckets.pop(key, None)
        return closed

    async def close_all(self) -> None:
        """关掉并清空池（进程退出 / 测试收尾用）。"""
        buckets = list(self._buckets.values())
        self._buckets.clear()
        pending, self._pending_close = self._pending_close, []
        for server in pending:
            await self._safe_close(server)
        for bucket in buckets:
            for item in bucket.servers:
                await self._safe_close(item.server)

    def _evict_overflow_buckets(self, *, keep: tuple[str, str]) -> None:
        """桶数超过上限时，丢掉最久没用的一个（其连接留给 ``sweep`` 关）。

        这里不 ``await``（``acquire`` 的临界区里不能有 await 让出点，否则
        「先把连接标记为 console」与「真的关掉」之间会被别的协程插进来，
        它拿到的是一条正在被关的连接）。所以只摘桶、把连接交给
        ``sweep``/``close_all`` 收尾——GC 前它们仍是「已连接但没人用」的状态，
        不影响正确性。
        """
        if len(self._buckets) < self._max_buckets:
            return
        victim = min(
            (k for k in self._buckets if k != keep),
            key=lambda k: self._buckets[k].last_used,
            default=None,
        )
        if victim is None:
            return
        bucket = self._buckets.pop(victim)
        for item in bucket.servers:
            # 只摘不关：真正的 ``cleanup`` 是协程，这里不能 await。
            item.closed = True
            item.leases = 0
            self._pending_close.append(item.server)

    @staticmethod
    async def _safe_close(server: MCPServerStreamableHttp) -> None:
        """关连接，失败只记 debug：关闭失败不该覆盖本轮已经吐给用户的内容。"""
        try:
            await server.cleanup()
        except Exception:
            logger.debug("关闭 MCP 连接失败（忽略）", exc_info=True)


_pool = McpSessionPool()


def get_mcp_session_pool() -> McpSessionPool:
    """进程级 MCP 连接池单例。"""
    return _pool
