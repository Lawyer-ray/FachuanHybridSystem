"""Tests for apps.core.tasking.qcluster_shutdown: django-q Cluster.stop() 幂等 / 可重入补丁。

覆盖三类真实缺陷场景：
1. 已拆机（stop_event 置 None）后再次收到信号 → 不再 NoneType.set()。
2. stop() 进行中（卡在 sentinel.join()）被同一线程重入 → 短路、不重复 join。
3. 从未启动 / sentinel 已退出 → 安全短路。
"""

from __future__ import annotations

import types

import pytest
from django_q import cluster as django_q_cluster

from apps.core.tasking.qcluster_shutdown import patch_django_q_cluster_stop_for_macos


class _FakeSentinel:
    """最小 sentinel 替身，仅需 is_alive() / join()。"""

    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.joined = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self) -> None:
        self.joined = True


class _StopEvent:
    """最小 Event 替身；set() 在补丁测试里只作占位，无需真实信号量。"""

    def set(self) -> None:  # pragma: no cover - 仅占位
        pass


def _make_cluster(*, sentinel, stop_event, start_event=None) -> types.SimpleNamespace:
    """造一个只带 stop() 依赖字段的 Cluster 替身（不触达真实 django_q 构造）。"""
    c = types.SimpleNamespace()
    c.sentinel = sentinel
    c.stop_event = stop_event
    c.start_event = start_event if start_event is not None else object()
    return c


def _original_stop_behavior(self) -> bool:
    """复刻 django_q Cluster.stop() 的原始（有 bug 的）行为。"""
    if not self.sentinel.is_alive():
        return False
    self.stop_event.set()  # ← stop_event 为 None 时此处 AttributeError
    self.sentinel.join()
    self.start_event = None
    self.stop_event = None
    return True


class TestDjangoQStopPatch:
    def _patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(django_q_cluster.Cluster, "stop", _original_stop_behavior, raising=True)
        monkeypatch.delattr(_original_stop_behavior, "_fachuan_stop_patched", raising=False)
        # 清掉其它测试可能留下的补丁标记，确保本次 patch 真的重新生成。
        patch_django_q_cluster_stop_for_macos()

    def test_patch_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch(monkeypatch)
        patched_once = django_q_cluster.Cluster.stop
        patch_django_q_cluster_stop_for_macos()
        assert django_q_cluster.Cluster.stop is patched_once
        assert getattr(patched_once, "_fachuan_stop_patched", False) is True

    def test_stopped_cluster_none_events_short_circuit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """第一次 stop() 已把事件置 None；第二次信号进来不再报错（对应真实 bug）。"""
        self._patch(monkeypatch)
        fake = _make_cluster(sentinel=_FakeSentinel(True), stop_event=_StopEvent())

        # 第一次：正常拆机，事件被清空。
        assert django_q_cluster.Cluster.stop(fake) is True
        assert fake.stop_event is None
        assert fake.start_event is None

        # 第二次：event os.waitpid 阻塞中再次收到信号、字段仍是 None 状态。
        # 直接调（未修补版：`None.set()`）会 AttributeError；补丁应安全短路。
        assert django_q_cluster.Cluster.stop(fake) is False

    def test_stop_progress_reentrant_short_circuit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stop() 卡在 join 时被同一线程重入 → 第二次立即 False，join 只跑一次。"""
        join_calls = {"n": 0}
        state = {"second_result": "unset"}
        cluster_holder: dict[str, object] = {}

        class _ReentrantSentinel:
            def is_alive(self) -> bool:
                return True

            def join(self) -> None:
                join_calls["n"] += 1
                # join 中途模拟第二个信号：同一线程重入被 patch 的 stop。
                state["second_result"] = django_q_cluster.Cluster.stop(  # type: ignore[arg-type]
                    cluster_holder["c"]
                )

        self._patch(monkeypatch)
        cluster = _make_cluster(sentinel=_ReentrantSentinel(), stop_event=_StopEvent())
        cluster_holder["c"] = cluster

        assert django_q_cluster.Cluster.stop(cluster) is True  # type: ignore[arg-type]
        assert join_calls["n"] == 1  # 重入未触发第二次 join
        assert state["second_result"] is False  # 重入被短路
        assert cluster.stop_event is None

    def test_never_started_cluster_short_circuit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """__init__ 后未 start：sentinel/stop_event 为 None，安全短路。"""
        self._patch(monkeypatch)
        fake = _make_cluster(sentinel=None, stop_event=None)
        assert django_q_cluster.Cluster.stop(fake) is False

    def test_sentinel_already_dead_short_circuit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sentinel 已退出：补丁补清尾一次并短路，不重复 join。"""
        self._patch(monkeypatch)
        fake = _make_cluster(sentinel=_FakeSentinel(alive=False), stop_event=_StopEvent())
        assert django_q_cluster.Cluster.stop(fake) is False
        assert fake.stop_event is None
        assert fake.start_event is None
