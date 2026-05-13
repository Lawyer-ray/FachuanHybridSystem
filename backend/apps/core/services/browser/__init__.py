"""浏览器公共服务。

统一管理 Playwright 浏览器生命周期，支持原生 launch 和 CDP 连接两种模式。

快速开始::

    from apps.core.services.browser import create_browser

    # 默认无头模式
    with create_browser() as (page, context):
        page.goto("https://example.com")

    # 使用预定义 Profile
    with create_browser("court_zxfw") as (page, context):
        page.goto("https://zxfw.court.gov.cn")

    # CDP 连接（gsxt、express 等 Profile 自动走 CDP）
    with create_browser("gsxt") as (page, context):
        ...

    # 复用登录态
    with create_browser(session_id="lawyer_zhang") as (page, context):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any

from .anti_detection import AntiDetection, anti_detection
from .chrome_process import is_cdp_ready, kill_chrome, launch_chrome
from .profiles import BrowserProfile, get_profile, register_profile
from .service import BrowserService, get_browser_service

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext as AsyncBrowserContext
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import BrowserContext, Page


@contextmanager
def create_browser(
    profile: str | BrowserProfile = "default",
    *,
    session_id: str | None = None,
    **kwargs: Any,
) -> Iterator[tuple[Page, BrowserContext]]:
    """创建浏览器任务。

    自动根据 Profile 配置决定使用原生 launch 还是 CDP 连接。
    任务结束后自动清理所有浏览器资源。

    Args:
        profile: 配置档案名称或实例
        session_id: 非 None 时复用已有的登录态（持久化 user_data_dir）
        **kwargs: 传递给 BrowserProfile 的额外参数覆盖

    Yields:
        (page, context) 元组

    Example::

        with create_browser() as (page, context):
            page.goto("https://example.com")

        with create_browser("court_zxfw") as (page, context):
            page.goto("https://zxfw.court.gov.cn")

        with create_browser(session_id="lawyer_zhang") as (page, context):
            page.goto("https://zxfw.court.gov.cn")  # 已登录
    """
    if isinstance(profile, str):
        profile = get_profile(profile)

    # 应用 kwargs 覆盖
    if kwargs:
        import dataclasses

        profile = dataclasses.replace(profile, **kwargs)

    if profile.is_cdp:
        # CDP 模式：同步包装异步调用
        import asyncio

        from .cdp_connector import connect_cdp_page

        async def _run() -> tuple[Page, BrowserContext]:
            async with connect_cdp_page(profile, auto_launch=True) as (page, ctx):
                # 将 page 和 context 传递给调用方
                result = (page, ctx)
                yield result  # type: ignore[misc]

        # CDP 模式需要异步上下文，这里用同步包装
        # 实际使用时，CDP 场景建议直接用 create_browser_async
        raise NotImplementedError(
            "CDP 模式请使用 create_browser_async()，"
            "或在异步函数中使用: async with create_browser_async('gsxt') as (page, ctx): ..."
        )
    else:
        from .launcher import launch_browser

        yield from launch_browser(profile, session_id=session_id)


@asynccontextmanager
async def create_browser_async(
    profile: str | BrowserProfile = "default",
    *,
    session_id: str | None = None,
    **kwargs: Any,
) -> AsyncIterator[tuple[AsyncPage, AsyncBrowserContext]]:
    """异步版本：创建浏览器任务。

    支持所有连接模式（原生 launch、CDP、远程连接）。

    Args:
        profile: 配置档案名称或实例
        session_id: 非 None 时复用已有的登录态
        **kwargs: 传递给 BrowserProfile 的额外参数覆盖

    Yields:
        (page, context) 元组

    Example::

        async with create_browser_async("gsxt") as (page, context):
            await page.goto("https://gsxt.gov.cn")
    """
    if isinstance(profile, str):
        profile = get_profile(profile)

    if kwargs:
        import dataclasses

        profile = dataclasses.replace(profile, **kwargs)

    if profile.is_cdp:
        from .cdp_connector import connect_cdp_page

        async with connect_cdp_page(profile, auto_launch=True) as (page, context):
            yield page, context
    else:
        # 原生 launch 的异步版本
        from playwright.async_api import async_playwright

        from .anti_detection import anti_detection

        async with async_playwright() as pw:
            launch_args = profile.to_launch_args()
            browser = await pw.chromium.launch(**launch_args)

            context_args = profile.to_context_args()
            if profile.anti_detection:
                anti_opts = anti_detection.get_context_options()
                anti_opts.update(context_args)
                context_args = anti_opts

            context = await browser.new_context(**context_args)
            context.set_default_timeout(profile.timeout)
            context.set_default_navigation_timeout(profile.navigation_timeout)

            page = await context.new_page()

            if profile.anti_detection:
                await anti_detection.apply_stealth_async(context)

            try:
                yield page, context
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass


__all__ = [
    # 核心 API
    "create_browser",
    "create_browser_async",
    # 配置
    "BrowserProfile",
    "get_profile",
    "register_profile",
    # 服务
    "BrowserService",
    "get_browser_service",
    # Chrome 进程管理
    "launch_chrome",
    "kill_chrome",
    "is_cdp_ready",
    # 反检测
    "AntiDetection",
    "anti_detection",
]
