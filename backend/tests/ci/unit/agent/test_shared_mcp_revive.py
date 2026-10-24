"""共享 MCP 自愈测试 —— acquire 路径上的 ensure 与降级。

## 背景（2026-10-25 审计发现）

``ensure_shared_server`` 原本只在进程池**首次创建**时调用一次（chat_service
``get_pool`` 的 ``if _pool is None`` 分支）。共享 MCP 是单点常驻进程
（~225MB），运行中崩溃后没有任何拉起路径：所有新会话连不上 :8011，
工具面全废，直到 Django 重启——「坏得太安静」家族的又一成员。

修复后每次 ``pool.acquire`` 拿到执行位都会 ensure 一把（幂等：端口在就
秒回），且新拉实例时 ``wait_ready=True``（冷启动实测 ~6s，不等的话 pi
立刻连接、落在冷启动窗口里，这个会话照样没有工具）。

注意 patch 目标：``acquire`` 里是函数内 ``from .shared_mcp import ...``，
每次执行都从源模块解析，所以必须 patch ``shared_mcp`` 模块的属性，
patch ``pool`` 模块同名属性无效。

本文件守护：
1. acquire 确实触发 ensure（带 wait_ready=True 与池配置的 endpoint）；
2. stdio 回退（mcp_endpoint=None）不触发；
3. ensure 抛 OSError 只降级（会话照常建立），不弄死对话；
4. ``wait_ready`` 只在新拉实例时生效、复用现有实例不等待。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from apps.agent.pi import pool as pool_module
from apps.agent.pi import shared_mcp as shared_mcp_module
from apps.agent.pi.pool import PiProcessPool, PoolConfig
from apps.agent.pi.shared_mcp import McpEndpoint, ensure_shared_server


class _StubSession:
    def __init__(self, **kwargs: Any) -> None:
        self.closed = False

    async def start(self) -> None:
        await asyncio.sleep(0)

    async def close(self, *, abort_running: bool = False) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _stub_pool_internals(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(pool_module, "write_pi_config", lambda *a, **k: None)
    monkeypatch.setattr(pool_module, "PiRpcSession", _StubSession)
    monkeypatch.setattr(
        pool_module, "layout", lambda: (Path("/tmp/stub-work"), Path("/tmp/stub-config"), Path("/tmp/stub-sessions"))
    )
    yield


class TestAcquireRevivesSharedMcp:
    def test_acquire_ensures_shared_server_with_wait(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """每次 acquire 都要 ensure（wait_ready=True），不能只在池创建时拉一次。"""
        calls: list[dict[str, Any]] = []
        endpoint = McpEndpoint(host="127.0.0.1", port=8011)
        monkeypatch.setattr(
            shared_mcp_module,
            "ensure_shared_server",
            lambda ep, **kw: calls.append({"endpoint": ep, **kw}),
        )

        async def run() -> None:
            pool = PiProcessPool(PoolConfig(size=1, mcp_endpoint=endpoint))
            async with pool.acquire():
                pass
            async with pool.acquire():  # 第二次 acquire 也要 ensure
                pass

        asyncio.run(run())
        assert len(calls) == 2, f"acquire×2 应 ensure×2，实际 {len(calls)}"
        assert all(c["wait_ready"] is True for c in calls), calls
        assert all(c["endpoint"] is endpoint for c in calls), "endpoint 必须来自池配置"

    def test_stdio_mode_does_not_ensure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stdio 回退（mcp_endpoint=None）每个 pi 各起一份，不走共享 ensure。"""
        calls: list[Any] = []
        monkeypatch.setattr(shared_mcp_module, "ensure_shared_server", lambda *a, **k: calls.append(a))

        async def run() -> None:
            pool = PiProcessPool(PoolConfig(size=1, mcp_endpoint=None))
            async with pool.acquire():
                pass

        asyncio.run(run())
        assert calls == [], "stdio 模式不应触发共享 MCP ensure"

    def test_ensure_failure_degrades_not_crashes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ensure 抛 OSError 只降级（无工具但能对话），不弄死整个会话。"""

        def boom(*args: Any, **kwargs: Any) -> None:
            raise OSError("spawn failed")

        monkeypatch.setattr(shared_mcp_module, "ensure_shared_server", boom)

        async def run() -> bool:
            pool = PiProcessPool(PoolConfig(size=1, mcp_endpoint=McpEndpoint()))
            async with pool.acquire() as session:
                return session is not None

        assert asyncio.run(run()) is True


class TestWaitReadySemantics:
    def test_reuse_returns_without_waiting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """复用现有实例（spawn 返回 None）时不得进入就绪轮询。"""
        port_probes: list[Any] = []
        monkeypatch.setattr(shared_mcp_module, "spawn_shared_server", lambda ep: None)
        monkeypatch.setattr(
            shared_mcp_module, "port_open", lambda *a, **k: port_probes.append(a) or True
        )
        ensure_shared_server(McpEndpoint(), wait_ready=True)
        assert port_probes == [], "复用实例不应进入就绪轮询"

    def test_fresh_spawn_waits_until_port_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """新拉实例必须轮询端口就绪后才返回（防 pi 连进冷启动窗口）。"""
        port_probes: list[Any] = []

        class _FakeProc:
            pass

        monkeypatch.setattr(shared_mcp_module, "spawn_shared_server", lambda ep: _FakeProc())
        monkeypatch.setattr(
            shared_mcp_module, "port_open", lambda *a, **k: port_probes.append(a) or True
        )
        ensure_shared_server(McpEndpoint(), wait_ready=True)
        assert port_probes, "新拉实例应轮询端口就绪"

    def test_shared_disabled_skips_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FACHUAN_MCP_SHARED=0 时既不 spawn 也不等待。"""
        spawned: list[Any] = []
        monkeypatch.setenv("FACHUAN_MCP_SHARED", "0")
        monkeypatch.setattr(shared_mcp_module, "spawn_shared_server", lambda ep: spawned.append(ep))
        ensure_shared_server(McpEndpoint(), wait_ready=True)
        assert spawned == []
