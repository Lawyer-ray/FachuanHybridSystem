"""Tests for apps.core.tasking.qcluster_shutdown: 收尾期信号补丁（qcluster 僵死修复）。

背景（详见模块 docstring）：解释器已进 atexit 时收到 SIGTERM/SIGINT，django-q 的
sig_handler 会调 ``Cluster.stop() -> sentinel.join()``，在已被 atexit 持有的
``_waitpid_lock`` 上二次 acquire 而永久死锁 → qcluster 变僵尸、Redis 队列只进不出。
"""

from __future__ import annotations

import os
import signal
import sys

import pytest
from django_q import cluster as django_q_cluster

from apps.core.tasking import qcluster_shutdown


class TestSigHandlerForFinalizing:
    def test_finalizing_signal_exits_without_calling_stop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """收尾期收到信号：不进原处理器（即不进 Cluster.stop），直接退出。"""
        delegated: list[int] = []

        def _original(self: object, signum: int, frame: object) -> None:
            delegated.append(signum)

        monkeypatch.setattr(django_q_cluster.Cluster, "sig_handler", _original)
        qcluster_shutdown.patch_django_q_sig_handler_for_finalizing()

        exited: list[int] = []
        monkeypatch.setattr(qcluster_shutdown, "_exit_on_signal", exited.append)
        monkeypatch.setattr(sys, "is_finalizing", lambda: True)

        django_q_cluster.Cluster.sig_handler(object(), signal.SIGTERM, None)

        assert exited == [signal.SIGTERM]
        assert delegated == []

    def test_running_signal_delegates_to_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """解释器正常运行时：行为与 django-q 原生一致（交给原处理器）。"""
        delegated: list[int] = []

        def _original(self: object, signum: int, frame: object) -> None:
            delegated.append(signum)

        monkeypatch.setattr(django_q_cluster.Cluster, "sig_handler", _original)
        qcluster_shutdown.patch_django_q_sig_handler_for_finalizing()

        exited: list[int] = []
        monkeypatch.setattr(qcluster_shutdown, "_exit_on_signal", exited.append)
        monkeypatch.setattr(sys, "is_finalizing", lambda: False)

        django_q_cluster.Cluster.sig_handler(object(), signal.SIGINT, None)

        assert delegated == [signal.SIGINT]
        assert exited == []

    def test_patch_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """重复调用不叠加包装（start() 绑定的引用也只指向一层包装）。"""
        qcluster_shutdown.patch_django_q_sig_handler_for_finalizing()
        patched_once = django_q_cluster.Cluster.sig_handler

        qcluster_shutdown.patch_django_q_sig_handler_for_finalizing()

        assert django_q_cluster.Cluster.sig_handler is patched_once


class TestExitOnSignal:
    def test_restores_default_disposition_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """先恢复 SIG_DFL 再对自己重发，进程才会带着真实退出信号结束。"""
        seen: dict[str, tuple[object, ...]] = {}

        def _signal(signum: int, handler: object) -> None:
            seen["signal"] = (signum, handler)

        def _kill(pid: int, signum: int) -> None:
            seen["kill"] = (pid, signum)

        monkeypatch.setattr(signal, "signal", _signal)
        monkeypatch.setattr(os, "kill", _kill)
        try:
            qcluster_shutdown._exit_on_signal(signal.SIGTERM)
        finally:
            # 立刻还原：pytest-timeout 自己要用 signal.signal(SIGALRM)，
            # patch 活到 teardown 会把框架捅成 INTERNALERROR
            monkeypatch.undo()

        assert seen["signal"] == (signal.SIGTERM, signal.SIG_DFL)
        assert seen["kill"] == (os.getpid(), signal.SIGTERM)

    def test_falls_back_to_hard_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """连重发信号都失败时也不能活着（否则又是永久僵尸）。"""
        hard_exit: list[int] = []

        def _signal(signum: int, handler: object) -> None:
            raise OSError("signal 已被锁死")

        monkeypatch.setattr(signal, "signal", _signal)
        monkeypatch.setattr(os, "_exit", hard_exit.append)
        try:
            qcluster_shutdown._exit_on_signal(signal.SIGINT)
        finally:
            monkeypatch.undo()  # 同上看：不要脏着 pytest-timeout 的 SIGALRM

        assert hard_exit == [1]
