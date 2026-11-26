"""解析凭证池：多凭证轮询 + 每凭证并发上限 + 分档冷却 + 日配额记账。

同一解析平台（DocumentParseProvider）在多任务间共享一个凭证池（模块级单例），
从而支持「多 Key 并发 + 自动替换 + 异步并发」：

- 并发上限为 0 表示不限制；全部凭证都到并发上限时**超限使用**未冷却、未耗尽额度的
  凭证（保证请求可用，与升级前完全一致）；
- 失败按原因分三档冷却（``REASON_TRANSIENT`` / ``REASON_AUTH`` / ``REASON_QUOTA``）：
  瞬时抖动仍只冷却 30 秒，鉴权失效冷却 30 分钟，**额度耗尽冷却到下一个配额重置点**；
- 每凭证按天记账已用页数（``OCR_CREDENTIAL_DAILY_PAGES``），达上限即跳过；
  翻页按 ``settings.TIME_ZONE`` 的本地日期清零。

## 为什么必须分档（升级动机）

「免费额度 + 注册多账号」场景下，已耗尽今日额度的 Key 与「临时抖动」的 Key 若被
同等对待，就会每 30 秒重试一次、永远失败，而每次重试都要白传一整批页——多账号在
工程上等价于「同一把 Key 被反复锤」。分档 + 配额记账是这条路线的前置地基。

## 跨进程共享

状态（冷却截止时间、今日已用页数）存在 ``django.core.cache``：

- ``CACHES['default']`` 指向 Redis（配了 ``REDIS_URL``）→ **多 worker 共享同一份状态**：
  一把 Key 在 worker A 被判死，worker B 不会再挑它；
- 未配 Redis（``LocMemCache``）→ **自动退化为进程内**：状态只在当前进程有效，与升级前
  行为一致（不会更差）。日志与指标口径两种情况相同。

只有**带 provider 标识**的池（``provider_key`` 非空，即 ``get_credential_pool`` 创建的池）
才读写共享状态：缓存键要靠「平台 + 凭证」这个稳定身份才能在跨进程对齐。直接
``CredentialPool(creds, n)`` 构造的一次性池（显式传入 api_key / app_id+secret 的脚本、
单凭证直用）保持纯进程内：它没有平台归属，把状态写进全局缓存反而会让「脚本里拿坏
Key 试一下」污染生产池。

并发槽位（``_active``）**只在本进程内计数**：并发上限的语义本来就是「本进程同时在飞
几个请求」，跨进程持有实时计数需要分布式租约，收益不抵复杂度。

## 三条红线

1. **fail-open**：cache 读写失败一律降级为进程内账本，绝不打断解析主流程；只捕获
   ``CACHE_ERRORS``（Django cache / Redis 相关异常 + ``ValueError``），不用宽捕获。
2. **凭证不派生出任何可回读片段**：缓存键里只有 PBKDF2 派生摘要（见 ``_credential_digest``）；
   日志里只出现槽位序号（``槽#2``），**连尾 4 位都不打**——尾 4 位同样是凭证的一部分，
   落进日志系统就等于泄漏（CodeQL ``py/clear-text-logging-sensitive-data`` 报的就是
   「脱敏后仍源自凭证」这种写法）。
3. **时间口径**：冷却用墙钟 ``time.time()``（``time.monotonic()`` 无法跨进程比较），
   配额日期用 ``settings.TIME_ZONE`` 的本地日期。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from datetime import time as dt_time
from datetime import timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.core.infrastructure.cache import CACHE_ERRORS

logger = logging.getLogger(__name__)

# ── 失败档位（由调用方按真实异常传进 ``release``，见 ``classify_failure_reason``）──

#: 瞬时失败：网络抖动、5xx、超时。重试一次通常就好。
REASON_TRANSIENT = "transient"
#: 鉴权失败：401/403、凭证失效。重试一万次也不会自愈。
REASON_AUTH = "auth"
#: 额度耗尽：429、「免费额度已用完」等。要等平台重置配额。
REASON_QUOTA = "quota"

#: 401/403 一律按鉴权失败处理（不看文案）。
_AUTH_STATUS_CODES = frozenset({401, 403})

#: 额度/配额类失败文案（HTTP 429 之外，「额度耗尽」多数还是 HTTP 200 + 业务码）。
_QUOTA_HINTS: tuple[str, ...] = (
    "429",
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "额度",
    "配额",
    "次数已用完",
    "余额不足",
)

#: 鉴权类失败文案（状态码缺失/SDK 自定义异常时的兜底判据）。
_AUTH_HINTS: tuple[str, ...] = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "invalid token",
    "invalid api key",
    "鉴权",
    "认证失败",
)


def _env_seconds(name: str, default: float) -> float:
    """env 覆盖的时长（秒）；空值/非法值/非正数一律回落默认值（不抛，import 期也不能炸）。"""
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r 不是数字，按默认值 %.0fs 处理", name, raw, default)
        return default
    if value <= 0:
        logger.warning("%s=%r 不是正数，按默认值 %.0fs 处理", name, raw, default)
        return default
    return value


#: 瞬时抖动冷却时长。
#:
#: 默认 30 秒 = 升级前的固定值：这类失败重试一次通常就好，等太久只是拖慢队列。
TRANSIENT_COOLDOWN_SECONDS = _env_seconds("OCR_CREDENTIAL_COOLDOWN_TRANSIENT_SECONDS", 30.0)

#: 鉴权失败冷却时长。
#:
#: 默认 30 分钟：401/403 重试再多次也不会自愈，沿用 30 秒只会把同一把坏 Key 反复
#: 打爆（每次白传一整批页）；30 分钟又足够短，管理员在管理页换好凭证/平台恢复后
#: 不需要重启进程即可自愈。
AUTH_COOLDOWN_SECONDS = _env_seconds("OCR_CREDENTIAL_COOLDOWN_AUTH_SECONDS", 1800.0)

#: 额度耗尽冷却的额外余量（秒）。
#:
#: 冷却到「下一个本地零点 + 该余量」而不是固定时长：配额按自然日重置，固定 30 秒
#: 等于「每秒撞一次墙」。余量用于吸收「本地零点已过、平台侧还没重置」的时钟差，
#: 避免刚解冻的凭证立刻又被打回 quota 档。
QUOTA_COOLDOWN_GRACE_SECONDS = _env_seconds("OCR_CREDENTIAL_QUOTA_GRACE_SECONDS", 60.0)

#: 每凭证每日页数上限的 env 名；0/未设 = 不限（单账号或未启用配额时行为与升级前一致）。
DAILY_PAGES_ENV = "OCR_CREDENTIAL_DAILY_PAGES"

#: 缓存键前缀。键名对运维/``KEYS`` 完全可见，所以只能出现摘要，不能出现凭证。
_CACHE_KEY_PREFIX = "ocr:credpool"
#: provider 名是中文（「律所 MinerU」）时直接拼进键会让 Django 抛 ``CacheKeyWarning``。
_CACHE_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


# ── cache 替身：全部失败都降级（fail-open），捕获 CACHE_ERRORS 而非宽捕获 ─────────


def _cache() -> Any | None:
    """Django cache；不可用时返回 None（调用方降级为进程内）。"""
    try:
        from django.core.cache import cache

        return cache
    except CACHE_ERRORS:  # pragma: no cover - Django 未就绪（脚本/单测早期）
        logger.debug("Django cache 不可用，凭证池状态降级为进程内", exc_info=True)
        return None


def _cache_get_many(keys: list[str]) -> dict[str, Any]:
    """一次批量读（避免每把凭证一次往返）；失败返回空字典 → 调用方用进程内账本。"""
    cache = _cache()
    if cache is None or not keys:
        return {}
    try:
        return dict(cache.get_many(keys))
    except CACHE_ERRORS:
        logger.debug("读取凭证池状态失败（降级为进程内）", exc_info=True)
        return {}


def _cache_set(key: str, value: Any, timeout: int) -> None:
    """写单键；失败只记 debug（进程内账本仍然生效，主流程不受影响）。"""
    cache = _cache()
    if cache is None:
        return
    try:
        cache.set(key, value, timeout=timeout)
    except CACHE_ERRORS:
        logger.debug("写入凭证池状态失败（仅本进程生效）", exc_info=True)


def _cache_add_pages(key: str, pages: int, timeout: int) -> None:
    """跨进程原子累加已用页数；失败只记 debug（调用方保留进程内账本）。

    先 ``add`` 再 ``incr``：Django 的 ``incr`` 遇到不存在的键会抛 ``ValueError``；
    Redis/LocMem 的 ``incr`` 本身是原子的，多 worker 并发记账不会丢。
    """
    cache = _cache()
    if cache is None:
        return
    try:
        cache.add(key, 0, timeout=timeout)
        cache.incr(key, pages)
    except CACHE_ERRORS:
        logger.debug("累加凭证已用页数失败（仅本进程生效）", exc_info=True)


# ── 键派生（禁止明文）────────────────────────────────────────────────────────


def _provider_segment(provider_key: str) -> str:
    """provider → 缓存键安全片段：可读前缀（仅 ASCII）+ 8 位摘要，中文名也不会撞。"""
    raw = (provider_key or "").strip() or "default"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{_CACHE_KEY_UNSAFE.sub('_', raw)[:40]}-{digest}"


#: 摘要派生的固定盐与迭代数。**只**用于把凭证变成稳定的缓存键片段，不参与口令校验。
_DIGEST_SALT = b"fachuan.credential-pool.v1"
_DIGEST_ITERATIONS = 100_000


@lru_cache(maxsize=512)
def _credential_digest(credential: str) -> str:
    """凭证的缓存键片段：PBKDF2-HMAC-SHA256 派生后截短到 16 位十六进制。

    缓存键会被 ``KEYS`` 打印、被慢查询日志记录、被运维看到，所以**禁止**出现凭证明文。
    64 bit 的摘要足以区分同一平台下的多把 Key；碰撞的最坏后果只是两把 Key 共用一份
    冷却/配额账本，不会串到别的平台（键里还有 provider 段）。

    为什么不用 ``sha256``：它是快速哈希，CodeQL 的 ``py/weak-sensitive-data-hashing``
    会把「对敏感值用快速哈希」直接判成 high（PR #697 就是这么红的）。PBKDF2 是 KDF，
    不在该规则的黑名单里；代价也可控——摘要只在建池时按凭证各算一次，且带 ``lru_cache``
    兜住「同一条凭证反复建池」，不进 acquire/release 热路径。
    """
    return hashlib.pbkdf2_hmac(
        "sha256",
        (credential or "").encode("utf-8"),
        _DIGEST_SALT,
        _DIGEST_ITERATIONS,
    ).hex()[:16]


def _slot_label(idx: int) -> str:
    """日志用槽位标签（``槽#1`` 起，1-based）：日志里不出现凭证的任何片段。

    以前打的是 ``****abcd``（尾 4 位），但尾 4 位仍是凭证的一部分，进了日志系统就等于
    泄漏；而且 CodeQL 无法把自定义脱敏函数当成净化器，照样报 clear-text logging。
    要人工对应「是哪把 Key」，按凭证池配置里的顺序数槽位即可。
    """
    return f"槽#{idx + 1}"


# ── 时间口径 ────────────────────────────────────────────────────────────────


def _now() -> float:
    """当前墙钟时间（秒）。独立成函数是为了让测试替换时钟（全局 patch ``time.time`` 会伤到别人）。"""
    return time.time()


def _local_zone() -> ZoneInfo:
    return ZoneInfo(str(getattr(settings, "TIME_ZONE", "") or "UTC"))


def _local_now() -> datetime:
    """``settings.TIME_ZONE`` 的本地时间（配额翻页口径，与 ``USE_TZ`` 取值无关）。"""
    return datetime.fromtimestamp(_now(), _local_zone())


def _local_today() -> str:
    """本地日期 ``YYYY-MM-DD``：配额按它分片，跨天自然归零。"""
    return _local_now().date().isoformat()


def _seconds_until_quota_reset() -> float:
    """距下一个本地零点（配额重置点）的秒数。"""
    now = _local_now()
    next_midnight = datetime.combine(now.date() + timedelta(days=1), dt_time.min, tzinfo=now.tzinfo)
    return max(0.0, (next_midnight - now).total_seconds())


def _daily_pages_limit() -> int:
    """每凭证每日页数上限；0/未设/非法 = 不限。

    每次调用读 env 而不缓存：读取只是字典查找，换来的是测试可 ``monkeypatch.setenv`` 直接改口径。
    """
    raw = (os.environ.get(DAILY_PAGES_ENV, "") or "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("%s=%r 不是整数，按不限处理", DAILY_PAGES_ENV, raw)
        return 0


def _is_exhausted(used_pages: int, daily_limit: int) -> bool:
    """该凭证今日额度是否已耗尽（``daily_limit`` 为 0 = 不限）。"""
    return daily_limit > 0 and used_pages >= daily_limit


# ── 失败档位判定（调用方 release 时用）──────────────────────────────────────


def _exception_status(error: BaseException | None) -> int | None:
    """沿异常链找 HTTP 状态码（SDK/包装异常常把它挂在 ``.status_code`` 或 ``.response``）。

    与 ``apps/core/llm/key_pool.py::_exception_status`` 同口径；那边是私有实现，
    跨模块引用会把 document_parsing 钉死在 llm 包的内部结构上，故各自保留一份。
    """
    seen: set[int] = set()
    current: BaseException | None = error
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


def classify_failure_reason(error: BaseException | None) -> str:
    """把调用方的真实异常映射成凭证池的失败档位。

    判定顺序（真实证据优先，不猜）：HTTP 状态码 → 429/额度文案 → 鉴权文案 → 兜底瞬时。

    Args:
        error: 正在传播的异常；``None``（正常返回）按 ``transient``。

    Returns:
        ``REASON_TRANSIENT`` / ``REASON_AUTH`` / ``REASON_QUOTA``。
    """
    status = _exception_status(error)
    if status in _AUTH_STATUS_CODES:
        return REASON_AUTH
    if status == 429:
        return REASON_QUOTA
    text = str(error or "").lower()
    if any(hint in text for hint in _QUOTA_HINTS):
        return REASON_QUOTA
    if any(hint in text for hint in _AUTH_HINTS):
        return REASON_AUTH
    return REASON_TRANSIENT


def failure_reason_of_active_exception() -> str:
    """``finally`` 里取「正在展开的异常」并判定档位；无异常（正常返回）时为 ``transient``。

    为什么需要它：``release`` 在 ``finally`` 里调用，那里拿不到 ``except ... as e`` 的绑定；
    而 ``sys.exc_info()`` 在 ``finally`` 期间返回的正是正在展开的那个异常。调用点若各自
    补 ``except`` 只为拿异常，会凭空多出一批宽捕获。
    """
    return classify_failure_reason(sys.exc_info()[1])


# ── 页数记账（调用方 release(pages=...) 时用）─────────────────────────────────


def pages_from_metadata(metadata: dict[str, Any] | None) -> int:
    """从解析结果的 ``metadata`` 取页数（供 ``release(pages=...)`` 记账）；取不到返回 0。

    页数只用于配额软记账，**任何脏值都不允许把一次成功的解析弄挂**，所以这里宁可记 0。
    """
    try:
        return max(0, int((metadata or {}).get("page_count") or 0))
    except (TypeError, ValueError):
        return 0


# ── 凭证池 ──────────────────────────────────────────────────────────────────


class CredentialPool:
    """单个解析平台的凭证槽位管理（线程安全）。

    并发槽位只在本进程内计数；冷却与日额度记账走 Django cache（见模块 docstring），
    因此重建池（平台配置变更）不会丢掉「哪把 Key 今天已经没额度了」。
    ``provider_key`` 为空时降级为纯进程内（无平台归属的一次性池）。
    """

    __slots__ = (
        "_active",
        "_cooldown_until",
        "_cursor",
        "_digests",
        "_lock",
        "_namespace",
        "_quota_date",
        "_used_pages",
        "credentials",
        "limit",
        "provider_key",
    )

    def __init__(self, credentials: list[str], concurrency_per_key: int = 0, *, provider_key: str = "") -> None:
        self.credentials = list(credentials)
        self.limit = max(0, int(concurrency_per_key or 0))
        self.provider_key = str(provider_key or "")
        count = len(self.credentials)
        # 进程内镜像兼降级账本：cache 不可用时它就是唯一状态；cache 可用时与 cache 取「较坏值」合并。
        self._active = [0] * count
        self._cooldown_until = [0.0] * count
        self._used_pages = [0] * count
        self._quota_date = [""] * count
        # 摘要与键前缀只派生一次：每次 acquire 都要用，不能每次重算（KDF 远贵于 sha256）。
        # 注意 ``credentials`` 构造后不得原地修改（改配置请让 get_credential_pool 重建池），
        # 否则摘要会与凭证错位，配额/冷却会记到别人头上。
        self._digests = [_credential_digest(credential) for credential in self.credentials]
        # 空 namespace = 纯进程内模式（见模块 docstring「跨进程共享」）
        self._namespace = f"{_CACHE_KEY_PREFIX}:{_provider_segment(self.provider_key)}" if self.provider_key else ""
        self._cursor = 0
        self._lock = threading.Lock()

    # ── 缓存键 ──

    def _cooldown_key(self, idx: int) -> str:
        return f"{self._namespace}:{self._digests[idx]}:cool"

    def _pages_key(self, idx: int, today: str) -> str:
        return f"{self._namespace}:{self._digests[idx]}:pages:{today}"

    # ── 状态读写 ──

    def _load_state(self, today: str) -> tuple[list[float], list[int]]:
        """读全部凭证的 (冷却截止时间, 今日已用页数)。

        缓存优先，且与进程内账本**取较坏值**：缓存里多出来的冷却/用量一定来自别的进程
        （或本进程写成功后的回读），漏掉任何一条都会让额度被超刷，宁可保守。
        读失败时直接用进程内账本（fail-open，不打断主流程）。
        """
        count = len(self.credentials)
        cooldowns = list(self._cooldown_until)
        used_pages = [self._used_pages[i] if self._quota_date[i] == today else 0 for i in range(count)]
        cooldown_keys = [self._cooldown_key(i) for i in range(count)]
        pages_keys = [self._pages_key(i, today) for i in range(count)]
        cached = _cache_get_many([*cooldown_keys, *pages_keys]) if self._namespace else {}
        for i in range(count):
            cached_until = cached.get(cooldown_keys[i])
            if isinstance(cached_until, (int, float)) and float(cached_until) > cooldowns[i]:
                cooldowns[i] = float(cached_until)
            cached_pages = cached.get(pages_keys[i])
            if isinstance(cached_pages, int) and cached_pages > used_pages[i]:
                used_pages[i] = int(cached_pages)
        # 回写镜像：下一次缓存不可用时至少还有这次读到的状态
        self._cooldown_until = cooldowns
        self._used_pages = used_pages
        self._quota_date = [today] * count
        return cooldowns, used_pages

    def _add_pages(self, idx: int, pages: int) -> None:
        """按实际处理页数记账：cache 原子累加 + 进程内账本累加。"""
        if pages <= 0:
            return
        today = _local_today()
        # TTL = 到本地零点 + 1 小时：键按日期分片，跨天自然归零，过期键由缓存自己清掉
        if self._namespace:
            _cache_add_pages(self._pages_key(idx, today), int(pages), int(_seconds_until_quota_reset()) + 3600)
        if self._quota_date[idx] != today:
            self._quota_date[idx] = today
            self._used_pages[idx] = 0
        self._used_pages[idx] += int(pages)

    # ── 公开 API ──

    def acquire(self) -> int | None:
        """选中一个可用凭证下标并占用。

        跳过「冷却未到点」与「今日额度已耗尽」的凭证；并发上限只在第一轮生效，
        之后按旧语义超限使用未冷却、未耗尽额度的凭证（保证请求可用）。

        Returns:
            凭证下标；无可用凭证时返回 None。
        """
        with self._lock:
            count = len(self.credentials)
            if count == 0:
                return None
            now = _now()
            cooldowns, used_pages = self._load_state(_local_today())
            daily_limit = _daily_pages_limit()
            cooling = {i for i in range(count) if cooldowns[i] > now}
            exhausted = [i for i in range(count) if _is_exhausted(used_pages[i], daily_limit)]
            blocked = cooling | set(exhausted)
            if exhausted:
                # 这条 warning 是「这批为什么慢/为什么拿不到凭证」的唯一归因线索，不能降级成 debug
                logger.warning(
                    "凭证池跳过额度耗尽凭证: provider=%s limit=%d slots=%s",
                    self.provider_key or "default",
                    daily_limit,
                    ", ".join(f"{_slot_label(i)}={used_pages[i]}页" for i in exhausted),
                )
            for _ in range(count):
                idx = self._cursor % count
                self._cursor += 1
                if idx in blocked or (self.limit and self._active[idx] >= self.limit):
                    continue
                self._active[idx] += 1
                return idx
            # 全部处于并发上限：超限使用下一个未冷却、未耗尽额度的凭证，保证请求可用
            for _ in range(count):
                idx = self._cursor % count
                self._cursor += 1
                if idx in blocked:
                    continue
                self._active[idx] += 1
                return idx
            logger.warning(
                "凭证池无可用凭证（全部冷却或额度耗尽）: provider=%s slots=%s 冷却中=%d 额度耗尽=%d",
                self.provider_key or "default",
                ", ".join(_slot_label(i) for i in range(count)),
                len(cooling),
                len(exhausted),
            )
            return None

    def release(
        self,
        idx: int,
        *,
        success: bool,
        reason: str = REASON_TRANSIENT,
        pages: int = 0,
    ) -> None:
        """释放凭证槽位；失败按 ``reason`` 分档冷却，并按实际处理页数记账。

        Args:
            idx: ``acquire`` 返回的下标；越界静默忽略（与升级前一致）。
            success: 本次占用是否成功。
            reason: 失败档位 ``transient`` / ``auth`` / ``quota``（默认 ``transient``）；
                未知取值按 ``transient`` 处理，成功时无意义。
            pages: 本次实际处理的页数，用于日额度记账（0 = 不记账）。
        """
        with self._lock:
            if not 0 <= idx < len(self._active):
                return
            self._active[idx] = max(0, self._active[idx] - 1)
            self._add_pages(idx, pages)
            if success:
                return
            normalized = reason if reason in (REASON_TRANSIENT, REASON_AUTH, REASON_QUOTA) else REASON_TRANSIENT
            if normalized != reason:
                logger.debug("未知的凭证失败档位 %r，按 transient 处理", reason)
            seconds = self._cooldown_seconds(normalized)
            now = _now()
            key = self._cooldown_key(idx)
            # 已有更长的冷却就保留：别的进程刚标的 quota 长冷却，不该被本进程一次瞬时失败
            # 缩短成 30s（缓存值也要跟着取 max，否则缓存里的长冷却会被覆盖掉）
            cached = _cache_get_many([key]).get(key) if self._namespace else None
            if isinstance(cached, (int, float)):
                self._cooldown_until[idx] = max(self._cooldown_until[idx], float(cached))
            self._cooldown_until[idx] = max(self._cooldown_until[idx], now + seconds)
            if self._namespace:
                _cache_set(key, self._cooldown_until[idx], max(1, int(self._cooldown_until[idx] - now) + 1))
            log = logger.warning if normalized in (REASON_AUTH, REASON_QUOTA) else logger.info
            log(
                "凭证进入冷却: provider=%s slot=%s reason=%s 冷却=%.0fs",
                self.provider_key or "default",
                _slot_label(idx),
                normalized,
                seconds,
            )

    def _cooldown_seconds(self, reason: str) -> float:
        """档位 → 冷却秒数（``quota`` 的时长取决于「到下一个重置点还有多久」）。"""
        if reason == REASON_QUOTA:
            return _seconds_until_quota_reset() + QUOTA_COOLDOWN_GRACE_SECONDS
        if reason == REASON_AUTH:
            return AUTH_COOLDOWN_SECONDS
        return TRANSIENT_COOLDOWN_SECONDS

    def snapshot(self) -> list[dict[str, Any]]:
        """各凭证的只读状态（下标与 ``credentials`` 对齐，**不含凭证明文**）。

        运维最常问的三件事——「第 3 把 Key 是不是还在冷却」「今天用掉多少页」
        「是不是额度没了」——都靠这个快照回答，不需要去 grep 日志。

        Returns:
            每凭证一个 dict：``cooldown_remaining``（秒）、``used_pages``（今日已用页数）、
            ``exhausted``（今日额度是否已耗尽）。
        """
        with self._lock:
            now = _now()
            cooldowns, used_pages = self._load_state(_local_today())
            daily_limit = _daily_pages_limit()
            return [
                {
                    "cooldown_remaining": round(max(0.0, cooldowns[i] - now), 3),
                    "used_pages": int(used_pages[i]),
                    "exhausted": _is_exhausted(used_pages[i], daily_limit),
                }
                for i in range(len(self.credentials))
            ]


_registry: dict[str, CredentialPool] = {}
_registry_lock = threading.Lock()


def get_credential_pool(
    provider_key: str,
    credentials: list[str],
    concurrency_per_key: int = 0,
) -> CredentialPool:
    """按平台标识获取共享的凭证池。

    当凭证列表或并发上限发生变化时重建池（旧池由仍在执行的任务继续持有，互不影响）。
    冷却与日额度记账在 Django cache 里，重建池不会丢（同一 provider + 同一凭证的键不变）。

    Args:
        provider_key: 平台唯一标识（建议用 DocumentParseProvider.name）。
        credentials: 凭证明文列表。
        concurrency_per_key: 每凭证并发上限。

    Returns:
        共享的 CredentialPool 实例。
    """
    global _registry
    with _registry_lock:
        pool = _registry.get(provider_key)
        if (
            pool is not None
            and pool.credentials == list(credentials)
            and pool.limit == max(0, int(concurrency_per_key or 0))
        ):
            return pool
        pool = CredentialPool(credentials, concurrency_per_key, provider_key=provider_key)
        _registry[provider_key] = pool
        return pool
