"""单平台多 Key 槽位管理。

供 ``OpenAICompatibleBackend`` 使用，统一「每 Key 并发上限」的语义，
避免各调用点各自实现一套轮询规则。

## 什么错误才算「这把 Key 坏了」（2026-11-21 对齐 LiteLLM 后的定案）

旧实现是**二值** ``release(success=False)``：任何异常（含一次参数错、一次上下文
超长、一次内容审核）都会让该 ``(Key, 模型)`` 冷却 30 秒。后果是**自伤**：

- 一次用户传的超长 prompt 触发 400，``for _ in range(len(pool.keys))`` 会把这个
  请求在**每把 Key 上重放一遍**，于是整池一起进冷却；
- 下一个正常用户拿到 `_raise_no_key_available` →「该平台全部 API Key 均不可用」。

LiteLLM 的做法是**状态码白名单**（``router_utils/cooldown_handlers.py``
``_is_cooldown_required``：只有 429/401/402/408/404 与 5xx 才冷却，其余 4XX 一律
不冷却），因为「客户端错不该怪 deployment」。本模块照此实现，并按我们自己的
语义微调：**403 在我们这里是「该 Key 没有这个模型的权限」，是真问题** → 冷却。

另外两条同样来自 LiteLLM：

- **不是一次就冷却**：默认连续 ``FAILS_BEFORE_COOLDOWN=2`` 次才冷却
  （LiteLLM 的 ``allowed_fails`` 默认 3；我们池子小、key 少，取 2）；
- **冷却时长可被 ``retry-after`` 覆盖**且夹在 ``[5, 300]`` 秒
  （网关实测 429 会带 ``retry-after: 60``，比写死的 30 秒长——30 秒后放回轮转
  只会让同一把 Key 反复挨打）。

## 为什么 Agent 通道（copilot）不做 rpm/tpm

``configure_limits`` 的 rpm/tpm 只在**本模块能看到请求边界**时才有意义：
它记账的单位是「60 秒窗口内的请求数 / token 数」，而这两个数都要求调用方在
**每次 model 调用**前后各报一次（``acquire`` 记请求、``release`` 补 token）。

服务通道（诉状生成、合同审查等）满足这个前提；Agent 通道不满足：

- pi / dsh / openai-agents / antigravity 的 model 调用都在**外部进程内部**发生，
  Django 侧只拿到「一轮对话开始 / 结束」，看不到中间的 N 次 tool → model 往返；
- 按轮次近似会把「一轮 = 20 次 model 调用」记成 1 次，阈值实际放宽 20 倍。
  这种「看着有限流、其实没限」比不设限更危险——它会让人相信一个不存在的保护。

另一条实测依据（``TECH-DEBT.md`` ⑤）：连「精确在飞计数」也**买不到容量**——
40 并发压测下租约模式拿到的 429 比现状更多，瓶颈是总槽位（Key 数 × 每 Key 并发），
不是「选得不准」。同理，rpm/tpm 只承诺给**能看到请求边界**的服务通道
（运维可见的文案在 ``gateway_profile.RATE_LIMIT_CHANNEL_NOTE``，Admin 表单直接引用它）；
Agent 通道要提高容量，正确动作是加 Key。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any

import httpx

from apps.core.infrastructure.cache import CACHE_ERRORS

logger = logging.getLogger(__name__)

#: 只有这些状态码说明「这把 Key 本身有问题」，才值得冷却（LiteLLM 白名单微调版）。
#: 403 纳入的理由：律所网关按 Key 授权模型，403 = 这把 Key 没有该模型权限。
COOLABLE_STATUS: frozenset[int] = frozenset({401, 402, 403, 404, 408, 429})

#: rpm/tpm 的执行模式：默认**只观测不拒绝**（记日志 + 快照），确认阈值合理后再开。
#: 依据：额度没有探测手段（网关的 x-ratelimit-* 头我们没解析），填错就拒绝会误伤医生。
ENFORCE_ENV = "FACHUAN_KEY_RATE_LIMIT_ENFORCE"

#: 无状态码的异常里，只有「网络/超时」这类可能是 Key 侧问题。
#: 其余（解析失败、ValueError、业务校验）与 Key 无关 → 不冷却、也不该换 Key 重试。
_TRANSPORT_ERROR_NAMES: frozenset[str] = frozenset(
    {
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "TimeoutException",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "ReadError",
        "WriteTimeout",
        "PoolTimeout",
        "RemoteProtocolError",
    }
)


def _env_float(name: str, default: float, low: float, high: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(low, min(float(raw), high))
    except ValueError:
        logger.warning("%s 不是数字（%r），按默认 %s 处理", name, raw, default)
        return default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    return int(_env_float(name, float(default), float(low), float(high)))


def _exception_status(exc: BaseException | None) -> int | None:
    """沿异常链找 HTTP 状态码（SDK 常把它挂在 ``.status_code`` 或 ``.response``）。"""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(current, "response", None)
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
        current = current.__cause__ or current.__context__
    return None


def rate_limit_enforce() -> bool:
    """rpm/tpm 是否**真的拒绝**（否则只观测）。"""
    return (os.getenv(ENFORCE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_key_fault(exc: BaseException | None) -> bool:
    """这个异常是否该算在「Key 头上」（→ 冷却 + 换下一把）。

    判定顺序与 LiteLLM 的 ``_is_cooldown_required`` 同构：**默认不冷却**，
    只有明确属于 Key 侧或网关侧的失败才为真。
    """
    if exc is None:
        return True
    status = _exception_status(exc)
    if status is not None:
        return status in COOLABLE_STATUS or status >= 500
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)):
        return True
    return type(exc).__name__ in _TRANSPORT_ERROR_NAMES


def cooldown_hint(exc: BaseException | None) -> float | None:
    """从 ``retry-after`` 头取建议冷却秒数（夹在 ``[5, 300]``）；取不到返回 ``None``。"""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("x-ratelimit-reset-requests")
    if not raw:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        return None  # 也可能是 HTTP-date，这里不解析：宁可用默认冷却
    return max(5.0, min(seconds, 300.0))


#: 生产拓扑里的「会同时向网关发请求的进程数」（2 个 web worker + 1 个共享 MCP）。
#:
#: 并发记账是**进程内**的（见 ``KeyScheduler`` 与 ``shared_pool`` 的论证），所以
#: Admin 里填的 ``concurrency_per_key=3`` 在 3 个进程下会让网关看到最多 9 个在途，
#: 直接吃 429。把单进程上限按进程数折算是最省的补救：
#: ``FACHUAN_LLM_PROCESS_COUNT`` 默认 1（单进程/测试），部署侧设成 3。
PROCESS_COUNT_ENV = "FACHUAN_LLM_PROCESS_COUNT"


def process_count() -> int:
    raw = (os.getenv(PROCESS_COUNT_ENV) or "").strip()
    if not raw:
        return 1
    try:
        return max(1, min(int(raw), 32))
    except ValueError:
        logger.warning("%s=%r 不是整数，按 1 个进程处理", PROCESS_COUNT_ENV, raw)
        return 1


def effective_limit(configured: int) -> int:
    """把「每 Key 并发上限」按进程数折算成**单进程真实可用**的槽位数。

    ``configured=3`` + 3 个进程 → 1；``configured=0``（不限）保持 0。
    """
    if configured <= 0:
        return 0
    return max(1, int(configured) // process_count())


class KeyPool:
    """单平台多 Key 槽位管理：按模型过滤候选、轮询分配、每 Key 并发上限、失败冷却。

    - 并发上限为 0 表示不限制；
    - 全部候选 Key 处于并发上限时超限使用（保证请求可用）；
    - 失败后的 ``(Key, 模型)`` 组合进入冷却，冷却**按组合而非按 Key** 记账，
      避免某模型的无权限 403 误伤同一 Key 对其他模型的正常请求；
    - ``scopes`` 为 ``{key: [model, ...]}``，未出现的 Key 表示不限模型。

    线程安全：``acquire`` / ``release`` 由内部锁保护，可在多线程与多事件循环下共用。
    """

    #: 冷却秒数。30 是保守默认；命中 429 的 ``retry-after`` 时以网关给的为准。
    COOLDOWN_SECONDS: float = _env_float("FACHUAN_KEY_COOLDOWN_SECONDS", 30.0, 5.0, 300.0)
    #: 连续多少次「Key 侧失败」才冷却（LiteLLM ``allowed_fails`` 的同族语义）。
    FAILS_BEFORE_COOLDOWN: int = _env_int("FACHUAN_KEY_FAILS_BEFORE_COOLDOWN", 2, 1, 10)

    def __init__(
        self,
        keys: list[str],
        concurrency_per_key: int = 0,
        scopes: dict[str, list[str]] | None = None,
        provider: str = "",
    ) -> None:
        #: 平台名：跨进程 Key 健康记账的一维键（``key_health`` 用它拼缓存键）
        self.provider = (provider or "").strip()
        self.keys = list(keys)
        self.limit = max(0, int(concurrency_per_key or 0))
        self.scopes: dict[str, list[str]] = {key: list(models) for key, models in (scopes or {}).items()}
        self._active = [0] * len(self.keys)
        self._failed_until: dict[tuple[int, str], float] = {}
        self._fails: dict[tuple[int, str], int] = {}
        self._reason: dict[tuple[int, str], str] = {}
        self._cursor = 0
        #: 每 Key 的 (时间戳, tokens) 滑窗（60 秒）。**滑动窗口而不是分钟桶**：
        #: 固定窗口在 12:00:59 与 12:01:01 的瞬时速率可以翻倍（LiteLLM 敢用分钟桶是因为
        #: 它有单请求 token 预检兜底，我们没有）。
        self._window: dict[int, deque[tuple[float, int]]] = {}
        self._rpm_limit = 0
        self._tpm_limit = 0
        self._lock = threading.Lock()

    def configure_limits(self, *, rpm: int = 0, tpm: int = 0) -> None:
        """设置该池的 rpm/tpm 上限（0 = 不限）。由 ``shared_pool`` 按平台配置注入。"""
        self._rpm_limit = max(0, int(rpm or 0))
        self._tpm_limit = max(0, int(tpm or 0))

    def _window_totals(self, idx: int, now: float) -> tuple[int, int]:
        """该 Key 最近 60 秒的 ``(请求数, tokens)``（顺手清掉过期样本）。"""
        window = self._window.get(idx)
        if not window:
            return 0, 0
        cutoff = now - 60.0
        while window and window[0][0] < cutoff:
            window.popleft()
        return len(window), sum(tokens for _, tokens in window)

    def rate_snapshot(self) -> list[dict[str, Any]]:
        """各 Key 的 60 秒窗口用量（只读；用于诊断与「观察模式」日志）。"""
        now = time.monotonic()
        with self._lock:
            rows = []
            for idx in range(len(self.keys)):
                requests, tokens = self._window_totals(idx, now)
                if requests or tokens:
                    rows.append({"index": idx + 1, "requests_60s": requests, "tokens_60s": tokens})
            return rows

    def _over_limit(self, idx: int, now: float) -> str:
        """该 Key 是否超 rpm/tpm；返回原因（未超返空串）。"""
        if not (self._rpm_limit or self._tpm_limit):
            return ""
        requests, tokens = self._window_totals(idx, now)
        if self._rpm_limit and requests >= self._rpm_limit:
            return f"rpm {requests}/{self._rpm_limit}"
        if self._tpm_limit and tokens >= self._tpm_limit:
            return f"tpm {tokens}/{self._tpm_limit}"
        return ""

    def _eligible(self, model: str) -> list[int]:
        """返回可用于该模型的 Key 下标（未声明白名单的 Key 视为不限模型）。"""
        used = (model or "").strip()
        if not used:
            return list(range(len(self.keys)))
        return [i for i, key in enumerate(self.keys) if not self.scopes.get(key) or used in self.scopes[key]]

    def has_key_for(self, model: str = "") -> bool:
        """是否存在可用于该模型的 Key（不校验并发与冷却状态）。"""
        return bool(self._eligible(model))

    def acquire(self, model: str = "") -> int | None:
        """在可用于该模型的 Key 中选中一个下标并占用；无候选或全部冷却时返回 None。"""
        used = (model or "").strip()
        shared = self._shared_cooling()
        with self._lock:
            candidates = self._eligible(used)
            total = len(candidates)
            if total == 0:
                return None
            now = time.monotonic()
            for _ in range(total):
                idx = candidates[self._cursor % total]
                self._cursor += 1
                if self._failed_until.get((idx, used), 0.0) > now:
                    continue
                if self.keys[idx] in shared:
                    continue
                if rate_limit_enforce() and self._over_limit(idx, now):
                    continue
                if self.limit and self._active[idx] >= self.limit:
                    continue
                self._active[idx] += 1
                self._window.setdefault(idx, deque()).append((now, 0))
                over = self._over_limit(idx, now)
                if over and not rate_limit_enforce():
                    logger.info("Key rpm/tpm 观察：第 %d 把超限（%s），当前仅记录不拒绝", idx + 1, over)
                return idx
            # 全部处于并发上限：超限使用下一个「未冷却」的 Key，保证请求可用。
            # 两趟：先挑本地与**跨进程**都没判坏的；实在没有才退到「只避开本地冷却」。
            # 只查本地会让别的进程刚判死的 Key（多见于 401/429）被当成可用而复活。
            for ignore_shared in (False, True):
                for _ in range(total):
                    idx = candidates[self._cursor % total]
                    self._cursor += 1
                    if self._failed_until.get((idx, used), 0.0) > now:
                        continue
                    if not ignore_shared and self.keys[idx] in shared:
                        continue
                    self._active[idx] += 1
                    self._window.setdefault(idx, deque()).append((now, 0))
                    return idx
            return None

    def release(
        self,
        idx: int,
        *,
        success: bool,
        model: str = "",
        error: BaseException | None = None,
        cooldown_seconds: float | None = None,
        tokens: int = 0,
    ) -> None:
        """归还槽位，并按失败类型决定是否冷却该 ``(Key, 模型)``。

        Args:
            idx: :meth:`acquire` 返回的下标。
            success: 本次调用是否成功。客户端断连/取消应传 ``True``（不是 Key 的错）。
            model: 本轮使用的模型名（冷却按 ``(Key, 模型)`` 组合记账）。
            error: 失败时的原始异常。**由池统一判定「是否 Key 故障」**——调用方
                不要在外部自己判，否则每个调用点会各写一份漂移的白名单。
            cooldown_seconds: 覆盖本次冷却时长（通常来自 ``retry-after``）。
        """
        used = (model or "").strip()
        key = (idx, used)
        with self._lock:
            if 0 <= idx < len(self._active):
                self._active[idx] = max(0, self._active[idx] - 1)
            api_key = self.keys[idx] if 0 <= idx < len(self.keys) else ""
            if tokens > 0 and 0 <= idx < len(self.keys):
                window = self._window.setdefault(idx, deque())
                window.append((time.monotonic(), int(tokens)))
            if success:
                self._failed_until.pop(key, None)
                self._fails.pop(key, None)
                self._reason.pop(key, None)
                self._clear_shared(api_key)
                return
            if not is_key_fault(error):
                # 与 Key 无关的失败（400 参数错 / 上下文超长 / 内容审核 / 解析失败）：
                # 不计数、不冷却、不换 Key。
                self._reason[key] = f"non-key: {type(error).__name__ if error else 'unknown'}"
                return
            strikes = self._fails.get(key, 0) + 1
            if strikes < self.FAILS_BEFORE_COOLDOWN:
                self._fails[key] = strikes
                self._reason[key] = f"失败 {strikes}/{self.FAILS_BEFORE_COOLDOWN}"
                return
            seconds = cooldown_seconds if cooldown_seconds is not None else self.COOLDOWN_SECONDS
            self._failed_until[key] = time.monotonic() + max(1.0, seconds)
            self._fails.pop(key, None)
            self._reason[key] = f"{type(error).__name__ if error else '失败'}（冷却 {seconds:.0f}s）"
            self._mark_shared(api_key, seconds, self._reason[key])

    def _shared_cooling(self) -> dict[str, Any]:
        """别的进程判定的冷却 Key（fail-open：读不到就当全健康）。"""
        if not self.provider or not self.keys:
            return {}
        try:
            from apps.core.llm.key_health import cooling_map

            return dict(cooling_map(self.provider, self.keys))
        except CACHE_ERRORS:  # pragma: no cover - 缓存/Django 不可用时降级为进程内
            logger.debug("跨进程 Key 健康不可用，仅用进程内冷却", exc_info=True)
            return {}

    def _mark_shared(self, api_key: str, seconds: float, reason: str) -> None:
        if not self.provider or not api_key:
            return
        try:
            from apps.core.llm.key_health import mark_cooling

            mark_cooling(self.provider, api_key, seconds, reason)
        except CACHE_ERRORS:  # pragma: no cover
            logger.debug("写跨进程 Key 健康失败", exc_info=True)

    def _clear_shared(self, api_key: str) -> None:
        if not self.provider or not api_key:
            return
        try:
            from apps.core.llm.key_health import clear_cooling

            clear_cooling(self.provider, api_key)
        except CACHE_ERRORS:  # pragma: no cover
            logger.debug("清跨进程 Key 健康失败", exc_info=True)

    def is_cooling(self, idx: int, model: str = "") -> bool:
        """该 ``(Key, 模型)`` 组合是否处于失败冷却中。"""
        with self._lock:
            return self._failed_until.get((idx, (model or "").strip()), 0.0) > time.monotonic()

    @property
    def active_counts(self) -> list[int]:
        """各 Key 当前占用的槽位数（只读快照，供日志与监控观察池饱和度）。"""
        with self._lock:
            return list(self._active)

    def snapshot(self) -> list[dict[str, Any]]:
        """冷却/失败的只读快照（**不含 key 明文**，只用下标，供 Admin/日志观测）。

        运维最常问的两个问题——「第 3 把 Key 是不是废了」「现在几把在飞」——
        以前只能靠 grep 日志里重启即变号的别名。
        """
        now = time.monotonic()
        with self._lock:
            rows: list[dict[str, Any]] = []
            keys = set(self._failed_until) | set(self._reason) | set(self._fails)
            for idx, model in sorted(keys):
                until = self._failed_until.get((idx, model), 0.0)
                rows.append(
                    {
                        "index": idx + 1,
                        "model": model or "*",
                        "active": self._active[idx] if 0 <= idx < len(self._active) else 0,
                        "cooling": until > now,
                        "cooling_remaining": round(max(0.0, until - now), 1),
                        "fails": self._fails.get((idx, model), 0),
                        "reason": self._reason.get((idx, model), ""),
                    }
                )
            return rows


# ─── 进程级池注册表 ──────────────────────────────────────────────────────────

_shared_pools: dict[tuple[Any, ...], KeyPool] = {}
_shared_pools_lock = threading.Lock()


def _pool_cache_key(
    name: str,
    keys: list[str],
    concurrency_per_key: int,
    scopes: dict[str, list[str]] | None,
) -> tuple[Any, ...]:
    """池的内容寻址键：配置变了就换池，配置没变就复用同一个池。"""
    return (
        name,
        tuple(keys),
        max(0, int(concurrency_per_key or 0)),
        tuple(sorted((key, tuple(models)) for key, models in (scopes or {}).items())),
    )


def shared_pool(
    name: str,
    keys: list[str],
    concurrency_per_key: int = 0,
    scopes: dict[str, list[str]] | None = None,
    *,
    rpm_limit: int = 0,
    tpm_limit: int = 0,
) -> KeyPool:
    """返回进程内共享的 Key 池，按配置内容寻址。

    **两条路径必须共用同一个池**：服务路径与 Agent 路径若各持一份，
    「每 Key 并发上限」会被放大成两倍，直接顶穿网关限额。同时 Agent 路径的
    ``build_model`` 是每请求调用一次，若每次新建池，上限会随请求数无限放大。

    同平台的旧配置池在重建时一并清理，避免反复调整配置时堆积。
    """
    cache_key = _pool_cache_key(name, keys, concurrency_per_key, scopes)
    with _shared_pools_lock:
        pool = _shared_pools.get(cache_key)
        if pool is None:
            for stale in [k for k in _shared_pools if k[0] == name]:
                del _shared_pools[stale]
            pool = KeyPool(keys, effective_limit(concurrency_per_key), scopes, provider=name)
            pool.configure_limits(rpm=rpm_limit, tpm=tpm_limit)
            _shared_pools[cache_key] = pool
        return pool


def reset_shared_pools() -> None:
    """清空进程级池注册表。

    仅供测试在用例间隔离失败冷却与在途计数——池是跨用例共享的进程级状态，
    前一个用例把 ``(Key, 模型)`` 打进 30 秒冷却后，后一个用例会选不到该 Key。
    """
    with _shared_pools_lock:
        _shared_pools.clear()
