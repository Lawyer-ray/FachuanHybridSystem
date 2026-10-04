"""JTNAdapter.wait_open_browsers_closed 回收逻辑单测（Playwright driver 泄漏修复的锚点）。

回归语义：半自动浏览器关闭后必须逐个回收浏览器会话（page → context →
browser，CloakBrowser 的 browser.close() 内嵌停止 Playwright driver / node 进程），
回收只处理本实例打开的会话并同步清理全局防-GC 列表；等待/关闭失败不得上抛。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.core.services.browser import BrowserProfile, BrowserSessionHandle
from apps.oa_filing.services.oa_scripts.jtn import adapter as jtn_adapter


def _make_session(connected: bool = True, close_raises: bool = False) -> BrowserSessionHandle:
    browser = MagicMock()
    browser.is_connected.return_value = connected
    # wait_user_closed 通过 on("close")/on("disconnected") 注册回调后等待事件；
    # 注册即触发，模拟"用户随后关闭浏览器"让等待立即返回。
    browser.on = MagicMock(side_effect=lambda _evt, handler: handler(browser))
    browser.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    context = MagicMock()
    context.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    page = MagicMock()
    page.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    return BrowserSessionHandle(
        profile=BrowserProfile(name="jtn", headless=False),
        browser=browser,
        context=context,
        page=page,
    )


@pytest.mark.asyncio
async def test_connected_browser_waits_then_reclaims(monkeypatch: pytest.MonkeyPatch):
    """连接中的浏览器：注册 disconnected 监听并等待 → 回收会话（page/context/browser 逐个关闭）。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    session = _make_session(connected=True)
    adapter._opened_sessions.append(session)
    jtn_adapter._active_browser_sessions.append(session)

    await adapter.wait_open_browsers_closed()

    registered = {call.args[0] for call in session.browser.on.call_args_list}
    assert "disconnected" in registered
    session.page.close.assert_awaited_once()
    session.context.close.assert_awaited_once()
    session.browser.close.assert_awaited_once()  # CloakBrowser: 内嵌 pw.stop()


@pytest.mark.asyncio
async def test_disconnected_browser_skips_wait(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    session = _make_session(connected=False)
    adapter._opened_sessions.append(session)
    jtn_adapter._active_browser_sessions.append(session)

    await adapter.wait_open_browsers_closed()

    # 已断开的浏览器：仍注册 disconnected 监听（防竞态），但不等待，直接回收
    session.browser.on.assert_called_once()
    assert session.browser.on.call_args.args[0] == "disconnected"
    session.browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_failure_swallowed_and_registry_cleaned(monkeypatch: pytest.MonkeyPatch):
    """会话回收抛错不上抛（回收尽力而为），全局列表同步清理。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    session = _make_session(connected=False, close_raises=True)
    adapter._opened_sessions.append(session)
    jtn_adapter._active_browser_sessions.append(session)

    await adapter.wait_open_browsers_closed()  # 不应抛

    assert adapter._opened_sessions == []
    assert session not in jtn_adapter._active_browser_sessions


@pytest.mark.asyncio
async def test_other_instances_sessions_untouched(monkeypatch: pytest.MonkeyPatch):
    """回收只处理本实例会话，不动其他线程/请求打开的浏览器。"""
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    mine = _make_session(connected=False)
    other = _make_session(connected=False)
    adapter._opened_sessions.append(mine)
    jtn_adapter._active_browser_sessions.append(mine)
    jtn_adapter._active_browser_sessions.append(other)

    await adapter.wait_open_browsers_closed()

    mine.browser.close.assert_awaited_once()
    other.browser.close.assert_not_awaited()
    assert other in jtn_adapter._active_browser_sessions


@pytest.mark.asyncio
async def test_empty_sessions_noop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jtn_adapter, "_active_browser_sessions", [])
    adapter = jtn_adapter.JTNAdapter("acc", "pwd")
    await adapter.wait_open_browsers_closed()  # 空会话不应抛错
    assert adapter._opened_sessions == []
