"""微信公众号登录状态检测测试。"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from apps.wechat_mp.services.auth_handler import check_login_status


@pytest.mark.asyncio
async def test_check_login_status_on_login_page() -> None:
    """在登录页面返回 False。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage"
    result = await check_login_status(page)
    assert result is False


@pytest.mark.asyncio
async def test_check_login_status_logged_in() -> None:
    """已登录状态。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/home"
    mock_el = AsyncMock()
    mock_el.is_visible = AsyncMock(return_value=True)
    page.query_selector = AsyncMock(return_value=mock_el)
    result = await check_login_status(page)
    assert result is True


@pytest.mark.asyncio
async def test_check_login_status_not_logged_in() -> None:
    """未登录状态（无登录标识元素）。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/home"
    page.query_selector = AsyncMock(return_value=None)
    result = await check_login_status(page)
    assert result is False


@pytest.mark.asyncio
async def test_check_login_status_element_not_visible() -> None:
    """元素存在但不可见。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/home"
    mock_el = AsyncMock()
    mock_el.is_visible = AsyncMock(return_value=False)
    page.query_selector = AsyncMock(return_value=mock_el)
    # 第一个 selector 不可见，继续检查下一个
    # 所有都不可见时返回 False
    result = await check_login_status(page)
    assert result is False


@pytest.mark.asyncio
async def test_check_login_status_execution_context_destroyed() -> None:
    """执行上下文被销毁返回 False。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/home"
    page.query_selector = AsyncMock(side_effect=Exception("Execution context was destroyed"))
    result = await check_login_status(page)
    assert result is False


@pytest.mark.asyncio
async def test_check_login_status_generic_exception() -> None:
    """通用异常返回 False。"""
    page = MagicMock()
    page.url = "https://mp.weixin.qq.com/cgi-bin/home"
    page.query_selector = AsyncMock(side_effect=Exception("some error"))
    result = await check_login_status(page)
    assert result is False
