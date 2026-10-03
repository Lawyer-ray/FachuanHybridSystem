"""JTNAdapter.wait_open_browsers_closed 回收逻辑单测（Playwright driver 泄漏修复的锚点）。

回归语义：半自动浏览器关闭后必须逐个 stop playwright driver（node 进程），
回收只处理本实例打开的会话并同步清理全局防-GC 列表；等待/停止失败不得上抛。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.oa_filing.services.oa_scripts.jtn import adapter as jtn_adapter


def _make_session_pair(connected: bool = True, stop_raises: bool = False):
    playwright = MagicMock()
    playwright.stop = AsyncMock(side_effect=RuntimeError("boom") if stop_raises else None)
    browser = MagicMock()
    browser.is_connected.return_value = connected
    browser.wait_for_event = AsyncMock(return_value=None)
    return playwright, browser


@pytest.mark.asyncio
async def test_connected_browser_waits_then_stops(monkeypatch: pytest.MonkeyPatch):
    """连接中的浏览器：等 close 事件 → stop driver。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    pw, br = _make_session_pair(connected=True)
    adapter._opened_sessions.append((pw, br))
    jtn_adapter._active_browser_sessions.append((pw, br))

    await adapter.wait_open_browsers_closed()

    br.wait_for_event.assert_awaited_once_with("close", timeout=0)
    pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnected_browser_skips_wait(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    pw, br = _make_session_pair(connected=False)
    adapter._opened_sessions.append((pw, br))
    jtn_adapter._active_browser_sessions.append((pw, br))

    await adapter.wait_open_browsers_closed()

    br.wait_for_event.assert_not_awaited()
    pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_failure_swallowed_and_registry_cleaned(monkeypatch: pytest.MonkeyPatch):
    """driver stop 抛错不上抛（回收尽力而为），全局列表同步清理。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    pw, br = _make_session_pair(connected=False, stop_raises=True)
    adapter._opened_sessions.append((pw, br))
    jtn_adapter._active_browser_sessions.append((pw, br))

    await adapter.wait_open_browsers_closed()  # 不应抛

    assert adapter._opened_sessions == []
    assert (pw, br) not in jtn_adapter._active_browser_sessions


@pytest.mark.asyncio
async def test_other_instances_sessions_untouched(monkeypatch: pytest.MonkeyPatch):
    """回收只处理本实例会话，不动其他线程/请求打开的浏览器。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    mine_pw, mine_br = _make_session_pair(connected=False)
    other_pw, other_br = _make_session_pair(connected=False)
    adapter._opened_sessions.append((mine_pw, mine_br))
    jtn_adapter._active_browser_sessions.append((mine_pw, mine_br))
    jtn_adapter._active_browser_sessions.append((other_pw, other_br))

    await adapter.wait_open_browsers_closed()

    mine_pw.stop.assert_awaited_once()
    other_pw.stop.assert_not_awaited()
    assert (other_pw, other_br) in jtn_adapter._active_browser_sessions


@pytest.mark.asyncio
async def test_empty_sessions_noop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    await adapter.wait_open_browsers_closed()  # 空会话不应抛错
    assert adapter._opened_sessions == []
