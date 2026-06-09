"""CloakBrowser 异步启动模式。

通过 CloakBrowser launch_async() 启动浏览器，替代手动 Chrome 进程管理 + CDP 连接。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .anti_detection import anti_detection
from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.core")


@asynccontextmanager
async def connect_cdp_browser(
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Browser, BrowserContext]]:
    """通过 CloakBrowser 启动浏览器（替代手动 Chrome 进程 + CDP 连接）。

    Args:
        profile: 浏览器配置档案
        auto_launch: 保留参数（兼容接口），CloakBrowser 始终自动管理进程

    Yields:
        (browser, context) 元组
    """
    from cloakbrowser import ensure_binary, launch_async, launch_persistent_context_async

    browser: Browser | None = None
    context: BrowserContext | None = None

    try:
        ensure_binary()

        launch_kwargs: dict[str, Any] = {
            "headless": profile.headless,
            "humanize": profile.anti_detection,
        }
        if profile.proxy:
            launch_kwargs["proxy"] = profile.proxy

        if profile.user_data_dir:
            # 持久化上下文（需要保持登录状态的场景）
            Path(profile.user_data_dir).mkdir(parents=True, exist_ok=True)
            context = await launch_persistent_context_async(
                user_data_dir=profile.user_data_dir,
                **launch_kwargs,
            )
            logger.info("CloakBrowser 持久化上下文已启动 (profile=%s)", profile.name)
        else:
            browser = await launch_async(**launch_kwargs)
            context_args = profile.to_context_args()
            if profile.anti_detection:
                anti_opts = anti_detection.get_context_options()
                anti_opts.update(context_args)
                context_args = anti_opts
            context = await browser.new_context(**context_args)
            logger.info("CloakBrowser 已启动 (profile=%s)", profile.name)

        # 设置超时
        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        try:
            result_browser: Any = browser if browser is not None else context
            yield result_browser, context
        finally:
            try:
                await context.close()
            except Exception:
                pass
            logger.debug("CloakBrowser context 已关闭")

    except Exception:
        logger.exception("CloakBrowser 启动失败 (profile=%s)", profile.name)
        raise


@asynccontextmanager
async def connect_cdp_page(
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Page, BrowserContext]]:
    """通过 CloakBrowser 启动并返回 (page, context)。"""
    async with connect_cdp_browser(profile, auto_launch=auto_launch) as (browser, context):
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        # dialog 处理
        page.on("dialog", lambda d: d.accept())

        # macOS 补充指纹补丁
        from .anti_detection import anti_detection
        await anti_detection.apply_macos_patches_async(page)

        yield page, context
