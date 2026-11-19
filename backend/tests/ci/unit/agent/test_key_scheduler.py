"""``key_scheduler`` —— 轮次级 API key 分配。

## 为什么这个模块值得单独测

网关对每把 key 限 ``max_parallel_requests = 3``（实测 429 + ``retry-after: 60``）。
分配器的两个性质直接决定「三 agent 同答会不会卡 60 秒」：

1. **同一轮内互不相同** —— 三栏撞一把 key 就是 3 并发，再加一个人提问就 429；
2. **跨轮分散** —— 全局轮转若只在负载相同时挑前几个，后面几把 key 永远闲置，
   并发能力白白浪费（实测踩过：修之前连跑两轮都拿到 sk-A/B/C）。

所以下面每条断言都对应一个真实故障模式，不是形式化覆盖率。
"""

from __future__ import annotations

import logging

import pytest

from apps.agent.backends.key_scheduler import (
    CAPACITY_ENV,
    DEFAULT_CAPACITY,
    KeyScheduler,
    capacity,
    fingerprint,
    get_key_scheduler,
)

KEYS = ["sk-A", "sk-B", "sk-C", "sk-D", "sk-E"]


@pytest.fixture
def sched() -> KeyScheduler:
    """每个用例一个干净调度器（单例是进程级的，跨用例会互相干扰）。"""
    s = KeyScheduler()
    s.reset()
    return s


class TestDistinctWithinRound:
    """同一轮内必须互不相同——这是「三 agent 用三把 key」的字面要求。"""

    def test_three_columns_get_three_distinct_keys(self, sched: KeyScheduler) -> None:
        leases = sched.allocate(KEYS, 3)
        assert len(leases) == 3
        assert len({lease.key for lease in leases}) == 3, "三栏拿到了重复的 key"

    def test_more_columns_than_keys_wraps_instead_of_failing(self, sched: KeyScheduler) -> None:
        """key 不够时要**循环复用**而不是报错或返回空。

        少几把 key 是运维配置问题，不该让律师的提问失败——这是产品取舍，
        与「宁可慢也别挂」一致。
        """
        leases = sched.allocate(["sk-A", "sk-B"], 4)
        assert len(leases) == 4
        assert {lease.key for lease in leases} == {"sk-A", "sk-B"}

    def test_empty_keys_still_returns_leases(self, sched: KeyScheduler) -> None:
        """没有任何 key 时返回空串租约，让后端按原口径报「未配置平台」。"""
        leases = sched.allocate([], 2)
        assert [lease.key for lease in leases] == ["", ""]
        # 空 key 不该被记账（否则 snapshot 里会多一个 "(empty)": n）
        assert sched.snapshot() == {}


class TestSpreadAcrossRounds:
    """跨轮要分散——只按在飞数排且不轮转的话，后几把 key 会永远闲置。"""

    def test_successive_rounds_use_different_keys(self, sched: KeyScheduler) -> None:
        first = {lease.key for lease in sched.allocate(KEYS, 3)}
        second = {lease.key for lease in sched.allocate(KEYS, 3)}
        # 5 把 key、每轮 3 栏：两轮必有 1 把重叠（抽屉原理），但**不能完全相同**
        assert first != second, "第二轮又用了同一批 key，后面的 key 被闲置了"
        assert len(first & second) <= 1, "两轮重叠过多：分配没有真正分散"

    def test_all_keys_get_used_over_time(self, sched: KeyScheduler) -> None:
        used: set[str] = set()
        for _ in range(3):
            used |= {lease.key for lease in sched.allocate(KEYS, 3)}
        assert used == set(KEYS), f"有 key 从未被使用：{set(KEYS) - used}"


class TestCapacity:
    """跑满的 key 要跳过——这是避免 429 的关键。"""

    def test_saturated_key_is_skipped(self, sched: KeyScheduler, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "1")
        sched.allocate(["sk-A"], 1)  # 把 A 打满（cap=1）
        second = sched.allocate(["sk-A", "sk-B"], 1)
        assert second[0].key == "sk-B", "打满的 key 仍被派出去 → 会 429"

    def test_all_saturated_warns_but_still_allocates(
        self, sched: KeyScheduler, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """全满了也要给 key（best-effort），但必须留 warning。

        直接拒绝会让整轮多答失败；给出去最多是排队 60 秒——后者可接受。
        """
        monkeypatch.setenv(CAPACITY_ENV, "1")
        sched.allocate(["sk-A"], 1)
        with caplog.at_level(logging.WARNING):
            leases = sched.allocate(["sk-A"], 1)
        assert [lease.key for lease in leases] == ["sk-A"]
        assert any("并发上限" in rec.message for rec in caplog.records), "全满时没有告警"


class TestRelease:
    """归还必须准确——漏归还等于把并发槽永久占掉，越跑越容易 429。"""

    def test_release_frees_the_slot(self, sched: KeyScheduler, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "1")
        lease = sched.allocate(["sk-A"], 1)[0]
        assert sched.snapshot()
        lease.release()
        assert sched.snapshot() == {}, "归还后计数没清零"

    def test_double_release_is_safe(self, sched: KeyScheduler) -> None:
        """重复归还不该把别的栏的计数扣掉。

        ``release`` 会被 ``finally`` 与上下文管理器两条路径各调一次的可能，
        不幂等的话计数会掉到负数或误伤同 key 的兄弟栏。
        """
        lease = sched.allocate(["sk-A"], 1)[0]
        lease.release()
        lease.release()
        assert sched.snapshot() == {}

    def test_context_manager_releases(self, sched: KeyScheduler, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "1")
        with sched.allocate(["sk-A"], 1)[0] as lease:
            assert lease.key == "sk-A"
            assert sched.snapshot()
        assert sched.snapshot() == {}

    def test_release_does_not_affect_sibling_lease(self, sched: KeyScheduler) -> None:
        """同 key 上有两个租约时，释放一个不能把另一个的计数也清掉。"""
        a, b = sched.allocate(["sk-A"], 2)  # 只有一把 key → 循环复用
        assert a.key == b.key == "sk-A"
        a.release()
        snap = sched.snapshot()
        assert snap.get(fingerprint("sk-A")) == 1, "兄弟栏的占用被误清"


class TestNoKeyLeak:
    """key 不得进日志——与 ``user_token`` 同级机密。"""

    def test_log_messages_use_fingerprint_not_raw_key(self, caplog: pytest.LogCaptureFixture) -> None:
        sched = KeyScheduler()
        sched.reset()
        with caplog.at_level(logging.DEBUG):
            # 触发两条 warning 路径（key 不够 / 全满）
            sched.allocate(["sk-SECRET-1"], 3)
        text = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "sk-SECRET-1" not in text, "明文 key 进了日志"

    def test_fingerprint_is_stable_and_short(self) -> None:
        assert fingerprint("sk-A") == fingerprint("sk-A")
        assert fingerprint("sk-A") != fingerprint("sk-B")
        assert len(fingerprint("sk-A")) == 8
        assert fingerprint("") == "(empty)"


class TestConfig:
    def test_default_capacity_matches_gateway(self) -> None:
        """默认值必须与网关实测的 ``max_parallel_requests`` 一致。

        设大了会频繁 429（等 60 秒），设小了白白浪费并发槽——两边都难排查，
        所以把「默认 3」写成断言，改它就得先改这里。
        """
        assert DEFAULT_CAPACITY == 3

    def test_capacity_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "5")
        assert capacity() == 5

    def test_bad_capacity_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "not-a-number")
        assert capacity() == DEFAULT_CAPACITY

    def test_capacity_is_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(CAPACITY_ENV, "999")
        assert capacity() == 64
        monkeypatch.setenv(CAPACITY_ENV, "0")
        assert capacity() == 1


def test_singleton_is_process_wide() -> None:
    assert get_key_scheduler() is get_key_scheduler()
