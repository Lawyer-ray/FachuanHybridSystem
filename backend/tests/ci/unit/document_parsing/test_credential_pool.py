"""CredentialPool 测试：轮询分配、并发上限、分档冷却、日配额、跨进程共享与脱敏。

全程用假 cache（``FakeCache`` / ``BrokenCache``）隔离：不依赖 Redis / PG 实例，
也才能断言「同一份缓存被两个池实例看到」=「两个 worker 进程共享状态」。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings

from apps.document_parsing.services import credential_pool
from apps.document_parsing.services.credential_pool import (
    REASON_AUTH,
    REASON_QUOTA,
    REASON_TRANSIENT,
    CredentialPool,
    classify_failure_reason,
    get_credential_pool,
    pages_from_metadata,
)


class FakeCache:
    """Django cache 的最小替身（只实现凭证池用到的四个方法）。"""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        return {key: self.store[key] for key in keys if key in self.store}

    def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        self.store[key] = value

    def add(self, key: str, value: Any, timeout: int | None = None) -> bool:
        if key in self.store:
            return False
        self.store[key] = value
        return True

    def incr(self, key: str, delta: int = 1) -> int:
        if key not in self.store:
            raise ValueError(f"Key '{key}' not found")
        self.store[key] = int(self.store[key]) + int(delta)
        return int(self.store[key])


class BrokenCache:
    """所有操作都抛 ``ValueError``：与 Django cache「键不存在/反序列化失败」同族，属于 CACHE_ERRORS。"""

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        raise ValueError("cache down")

    def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        raise ValueError("cache down")

    def add(self, key: str, value: Any, timeout: int | None = None) -> bool:
        raise ValueError("cache down")

    def incr(self, key: str, delta: int = 1) -> int:
        raise ValueError("cache down")


class LogCollector(logging.Handler):
    """直接挂在凭证池 logger 上收集记录。

    不能用 caplog：``apps`` logger 配了 ``propagate=False``（见 ``apps/core/infrastructure/logging.py``），
    记录不会传播到 root，caplog 的 handler 收不到。
    """

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> FakeCache:
    """每个用例一份干净假缓存：状态不跨用例串味，也不碰真实 Redis/LocMem。

    同时清掉 ``OCR_CREDENTIAL_DAILY_PAGES``：不让跑测试的机器上的环境变量改掉配额口径。
    """
    monkeypatch.delenv(credential_pool.DAILY_PAGES_ENV, raising=False)
    fake = FakeCache()
    monkeypatch.setattr(credential_pool, "_cache", lambda: fake)
    return fake


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """可控墙钟（秒）。凭证池的时间判断统一走 ``_now()``，替换它即可「拨表」。"""
    moment = [datetime(2026, 11, 25, 10, 0, tzinfo=ZoneInfo(settings.TIME_ZONE)).timestamp()]
    monkeypatch.setattr(credential_pool, "_now", lambda: moment[0])
    return moment


@pytest.fixture
def pool_logs() -> Any:
    collector = LogCollector()
    previous_level = credential_pool.logger.level
    credential_pool.logger.setLevel(logging.DEBUG)
    credential_pool.logger.addHandler(collector)
    try:
        yield collector
    finally:
        credential_pool.logger.removeHandler(collector)
        credential_pool.logger.setLevel(previous_level)


class TestCredentialPool:
    def test_empty_pool_acquires_none(self) -> None:
        pool = CredentialPool([])
        assert pool.acquire() is None

    def test_rotates_across_keys(self) -> None:
        pool = CredentialPool(["a", "b", "c"])
        idxs = [pool.acquire() for _ in range(3)]
        assert idxs == [0, 1, 2]
        # 全部 used→释放后可再次轮转
        for i in idxs:
            pool.release(i, success=True)
        assert pool.acquire() == 0

    def test_concurrency_limit(self) -> None:
        pool = CredentialPool(["a", "b"], concurrency_per_key=1)
        i0 = pool.acquire()
        i1 = pool.acquire()
        # a、b 各自被占用（每 key 上限 1）
        assert {i0, i1} == {0, 1}
        # 已满：超限使用下一个未冷却凭证（仍可用）
        assert pool.acquire() in (0, 1)
        pool.release(i0, success=True)
        pool.release(i1, success=True)

    def test_limit_zero_unlimited(self) -> None:
        pool = CredentialPool(["a"], concurrency_per_key=0)
        for _ in range(5):
            assert pool.acquire() == 0
        pool.release(0, success=True)

    def test_failed_credential_goes_cooldown(self) -> None:
        pool = CredentialPool(["a", "b"])
        # 占用 a，失败后冷却
        idx = pool.acquire()
        assert idx == 0
        pool.release(idx, success=False)
        # 冷却未到点：a 必须被跳过（旧行为：30s 内不可用）
        assert pool.snapshot()[0]["cooldown_remaining"] > 0
        # b 立即可用
        assert pool.acquire() == 1
        pool.release(1, success=True)

    def test_release_out_of_range_is_noop(self) -> None:
        pool = CredentialPool(["a"])
        assert pool.release(0, success=True) is None
        assert pool.release(99, success=True) is None  # 越界静默忽略

    def test_thread_safety(self) -> None:
        pool = CredentialPool(["k"] * 4, concurrency_per_key=1)
        results: list[int] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                idx = pool.acquire()
                pool.release(idx, success=True)
                results.append(1)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert sum(results) == 20


class TestGetCredentialPool:
    def test_shares_same_pool_for_same_key(self) -> None:
        p1 = get_credential_pool("平台A", ["a"], 3)
        p2 = get_credential_pool("平台A", ["a"], 3)
        assert p1 is p2
        # provider 名要带进池里：缓存键的命名空间靠它隔离
        assert p2.provider_key == "平台A"

    def test_rebuilds_when_credentials_change(self) -> None:
        p1 = get_credential_pool("平台B", ["a"], 3)
        p2 = get_credential_pool("平台B", ["a", "b"], 3)
        assert p1 is not p2
        assert p2.credentials == ["a", "b"]

    def test_rebuilds_when_limit_changes(self) -> None:
        p1 = get_credential_pool("平台C", ["a"], 3)
        p2 = get_credential_pool("平台C", ["a"], 5)
        assert p1 is not p2
        assert p2.limit == 5


class TestDailyQuota:
    """B3：日额度记账 + 按 settings.TIME_ZONE 本地日期翻页复位。"""

    def test_exhausted_credential_is_skipped(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "10")
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], provider_key="mineru")

        assert pool.acquire() == 0
        pool.release(0, success=True, pages=10)
        assert pool.snapshot()[0]["exhausted"] is True
        assert pool.snapshot()[0]["used_pages"] == 10

        # 0 号已达日额度：轮询到它也必须跳过，只能拿 1 号
        assert pool.acquire() == 1
        pool.release(1, success=True)
        assert pool.acquire() == 1
        pool.release(1, success=True)

    def test_quota_resets_on_local_date_rollover(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "10")
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], provider_key="mineru")
        pool.release(0, success=True, pages=10)
        assert pool.snapshot()[0]["exhausted"] is True

        # 拨到第二天（本地日期 +1 天）：额度复位，0 号重新可用
        clock[0] += 24 * 3600
        assert pool.snapshot()[0]["used_pages"] == 0
        assert pool.snapshot()[0]["exhausted"] is False
        assert pool.acquire() == 0

    def test_all_credentials_exhausted_returns_none(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "5")
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], provider_key="mineru")
        pool.release(0, success=True, pages=5)
        pool.release(1, success=True, pages=5)
        assert pool.acquire() is None

    def test_zero_or_unset_quota_means_unlimited(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=True, pages=10_000)
        assert pool.snapshot()[0]["exhausted"] is False
        assert pool.acquire() == 0

        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "0")
        assert pool.acquire() == 0

    def test_invalid_quota_env_is_unlimited(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "每天一千页")
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=True, pages=10_000)
        assert pool.snapshot()[0]["exhausted"] is False


class TestTieredCooldown:
    """B2：三档冷却时长不同，quota 冷却到下一个重置点而不是 30s。"""

    def test_three_reasons_have_distinct_durations(self, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002", "key-cccc-0003"], provider_key="mineru")
        pool.release(0, success=False, reason=REASON_TRANSIENT)
        pool.release(1, success=False, reason=REASON_AUTH)
        pool.release(2, success=False, reason=REASON_QUOTA)

        transient, auth, quota = (row["cooldown_remaining"] for row in pool.snapshot())
        assert transient == pytest.approx(credential_pool.TRANSIENT_COOLDOWN_SECONDS)
        assert auth == pytest.approx(credential_pool.AUTH_COOLDOWN_SECONDS)
        # 假时钟定格在本地 10:00 → 距下一个零点 14 小时，再加冷却余量
        assert quota == pytest.approx(14 * 3600 + credential_pool.QUOTA_COOLDOWN_GRACE_SECONDS)
        # 三档必须真的不同（quota 绝不能再是 30s）
        assert len({transient, auth, quota}) == 3
        assert quota > credential_pool.TRANSIENT_COOLDOWN_SECONDS

    def test_credential_recovers_after_transient_cooldown(self, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=False, reason=REASON_TRANSIENT)
        assert pool.acquire() is None

        clock[0] += credential_pool.TRANSIENT_COOLDOWN_SECONDS + 1
        assert pool.snapshot()[0]["cooldown_remaining"] == 0
        assert pool.acquire() == 0

    def test_quota_cooldown_outlives_transient(self, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=False, reason=REASON_QUOTA)
        # 30 秒后仍在冷却：额度不会因为时间流逝 30 秒而回来
        clock[0] += credential_pool.TRANSIENT_COOLDOWN_SECONDS + 1
        assert pool.acquire() is None
        assert pool.snapshot()[0]["cooldown_remaining"] > 0

    def test_unknown_reason_falls_back_to_transient(self, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=False, reason="something-new")
        assert pool.snapshot()[0]["cooldown_remaining"] == pytest.approx(credential_pool.TRANSIENT_COOLDOWN_SECONDS)

    def test_over_limit_fallback_skips_cooling_credential(self, clock: list[float]) -> None:
        """B1 旧语义「全满时超限使用」仍不得挑冷却中的凭证。"""
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], concurrency_per_key=1, provider_key="mineru")
        pool.release(0, success=False, reason=REASON_TRANSIENT)
        assert {pool.acquire(), pool.acquire(), pool.acquire()} == {1}


class TestCacheDegraded:
    """B4：cache 不可用时降级为进程内，且不得打断主流程。"""

    def test_cache_outage_degrades_to_process_local(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setattr(credential_pool, "_cache", BrokenCache)
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], provider_key="mineru")

        idx = pool.acquire()
        assert idx == 0
        pool.release(idx, success=True, pages=7)

        # 配额记账在进程内仍然生效
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "7")
        assert pool.snapshot()[0]["used_pages"] == 7
        assert pool.snapshot()[0]["exhausted"] is True
        assert pool.acquire() == 1

        # 冷却也在进程内生效；cache 全程抛异常但没有中断任何调用
        pool.release(1, success=False, reason=REASON_QUOTA)
        assert pool.acquire() is None
        assert pool.snapshot()[1]["cooldown_remaining"] > 0

    def test_broken_cache_does_not_raise(self, clock: list[float]) -> None:
        pool = CredentialPool(["key-aaaa-0001"], provider_key="mineru")
        pool.release(0, success=False, reason=REASON_QUOTA)
        assert pool.acquire() is None
        assert pool.snapshot()[0]["cooldown_remaining"] > 0


class TestCrossProcessSharedState:
    """B4：状态在 Django cache 里 → 两个池实例（= 两个 worker 进程）互相可见。

    真 Redis 部署时这就是「worker A 判死的 Key，worker B 也不会再挑」；
    没配 Redis（LocMem）时退化为进程内，两实例互不可见（由下一个用例钉住）。
    """

    def test_cooldown_is_visible_across_instances(self, clock: list[float]) -> None:
        worker_a = CredentialPool(["shared-key-0001"], provider_key="mineru")
        worker_b = CredentialPool(["shared-key-0001"], provider_key="mineru")
        worker_a.release(0, success=False, reason=REASON_QUOTA)
        assert worker_b.acquire() is None
        assert worker_b.snapshot()[0]["cooldown_remaining"] > 0

    def test_daily_pages_are_visible_across_instances(
        self, monkeypatch: pytest.MonkeyPatch, clock: list[float]
    ) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "5")
        worker_a = CredentialPool(["shared-key-0002"], provider_key="mineru")
        worker_b = CredentialPool(["shared-key-0002"], provider_key="mineru")
        worker_a.release(0, success=True, pages=5)
        assert worker_b.snapshot()[0]["used_pages"] == 5
        assert worker_b.acquire() is None

    def test_pool_without_provider_stays_process_local(self, fake_cache: FakeCache, clock: list[float]) -> None:
        """没有平台归属的一次性池（显式 api_key / 单凭证直用）不读写共享账本。"""
        pool = CredentialPool(["shared-key-0004"])
        pool.release(0, success=False, reason=REASON_QUOTA)
        assert fake_cache.store == {}
        assert pool.acquire() is None

    def test_state_is_namespaced_by_provider(self, clock: list[float]) -> None:
        mineru = CredentialPool(["shared-key-0003"], provider_key="mineru")
        paddle = CredentialPool(["shared-key-0003"], provider_key="paddleocr")
        mineru.release(0, success=False, reason=REASON_QUOTA)
        # 同一条凭证串在不同平台上是不同账号，冷却不能互相传染
        assert paddle.acquire() == 0


class TestNoCredentialLeak:
    """B4 红线：缓存键与日志都不得出现凭证的任何片段（日志只给槽位序号）。"""

    def test_cache_keys_and_logs_never_contain_plaintext(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_cache: FakeCache,
        clock: list[float],
        pool_logs: Any,
    ) -> None:
        cred = "demo-credential-alpha"
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "1")
        pool = CredentialPool([cred], provider_key="MinerU 生产")
        pool.release(0, success=True, pages=1)
        assert pool.acquire() is None  # 触发「额度跳过」与「无可用凭证」两条 warning

        keys = list(fake_cache.store)
        assert keys, "应当写过缓存（冷却/页数都走缓存）"
        assert all(cred not in key for key in keys)
        assert all(key.isascii() for key in keys), keys  # 中文 provider 名不得裸拼进键

        # 键里用的是 KDF 派生的稳定摘要（不是 sha256：见 ``_credential_digest`` 的注释）
        expected_digest = credential_pool._credential_digest(cred)
        assert len(expected_digest) == 16
        assert any(expected_digest in key for key in keys)

        logs = "\n".join(pool_logs.messages)
        # B5 要求的归因线索：跳过额度耗尽的凭证、以及全部凭证不可用时各一条 warning
        assert "跳过额度耗尽凭证" in logs
        assert "无可用凭证" in logs
        assert cred not in logs
        # 收紧口径：连尾 4 位都不许出现（它仍是凭证的一部分，且 CodeQL 把脱敏写法判为泄漏）
        assert cred[-4:] not in logs
        assert "槽#1" in logs  # 归因改由槽位序号承担

    def test_slot_label_carries_no_credential(self) -> None:
        assert [credential_pool._slot_label(i) for i in (0, 2)] == ["槽#1", "槽#3"]


class TestSnapshot:
    """B5：snapshot() 给出可诊断指标。"""

    def test_reports_cooldown_pages_and_exhausted(self, monkeypatch: pytest.MonkeyPatch, clock: list[float]) -> None:
        monkeypatch.setenv(credential_pool.DAILY_PAGES_ENV, "100")
        pool = CredentialPool(["key-aaaa-0001", "key-bbbb-0002"], provider_key="mineru")
        pool.release(0, success=True, pages=30)
        pool.release(1, success=False, reason=REASON_AUTH)

        rows = pool.snapshot()
        assert len(rows) == 2
        assert set(rows[0]) == {"cooldown_remaining", "used_pages", "exhausted"}
        assert rows[0]["used_pages"] == 30
        assert rows[0]["cooldown_remaining"] == 0
        assert rows[0]["exhausted"] is False
        assert rows[1]["used_pages"] == 0
        assert rows[1]["cooldown_remaining"] == pytest.approx(credential_pool.AUTH_COOLDOWN_SECONDS)
        assert rows[1]["exhausted"] is False

    def test_snapshot_contains_no_credential_text(self, clock: list[float]) -> None:
        cred = "demo-credential-bravo"
        rows = CredentialPool([cred], provider_key="mineru").snapshot()
        assert cred not in repr(rows)


class TestClassifyFailureReason:
    """B6：调用方按真实异常判定档位（401/403→auth，429/额度→quota，其余→transient）。"""

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("PaddleOCR API 返回错误: HTTP 401", REASON_AUTH),
            ("PaddleOCR API 返回错误: HTTP 403 Forbidden", REASON_AUTH),
            ("PaddleOCR API 返回错误: HTTP 429", REASON_QUOTA),
            ("MinerU 任务失败: 今日免费额度已用完", REASON_QUOTA),
            ("TextinParse 解析失败: quota exceeded", REASON_QUOTA),
            ("MinerU 解析失败: HTTP 500 Internal Server Error", REASON_TRANSIENT),
            ("连接超时", REASON_TRANSIENT),
        ],
    )
    def test_maps_message_to_reason(self, message: str, expected: str) -> None:
        assert classify_failure_reason(RuntimeError(message)) == expected

    def test_status_code_on_exception_chain_wins(self) -> None:
        class _HttpStatusError(Exception):
            response = SimpleNamespace(status_code=403)

        error = RuntimeError("包装后的错误")
        error.__cause__ = _HttpStatusError("底层错误")
        assert classify_failure_reason(error) == REASON_AUTH

    def test_status_code_attribute_wins(self) -> None:
        class _SdkError(Exception):
            status_code = 429

        assert classify_failure_reason(_SdkError("队列已满")) == REASON_QUOTA

    def test_none_means_transient(self) -> None:
        assert classify_failure_reason(None) == REASON_TRANSIENT


class TestPagesFromMetadata:
    def test_reads_page_count(self) -> None:
        assert pages_from_metadata({"page_count": 12}) == 12

    @pytest.mark.parametrize("metadata", [None, {}, {"page_count": None}, {"page_count": "很多"}, {"page_count": -3}])
    def test_dirty_values_fall_back_to_zero(self, metadata: dict[str, Any] | None) -> None:
        assert pages_from_metadata(metadata) == 0
