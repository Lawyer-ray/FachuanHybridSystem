"""手动生命周期的浏览器会话（非上下文管理器形态）。

适用于「打开浏览器交给用户操作」的半自动场景：会话存活期跨越函数返回，
不能用 async with 提前关闭。调用方持有 :class:`BrowserSessionHandle`，
使命结束（通常是等用户关掉浏览器窗口）后调用 :func:`close_browser_session`
回收，禁止业务代码手写 browser.close() / playwright.stop() 清理逻辑。

浏览器启动行为与 ``create_browser_async()`` 的原生 launch 分支一致
（CloakBrowser + 反检测上下文 + macOS 指纹补丁），仅生命周期管理方式不同，
保证同一 Profile 在全自动 / 半自动两条链路下表现一致。

快速开始::

    from apps.core.services.browser import close_browser_session, create_browser_async_manual

    session = await create_browser_async_manual("jtn")
    try:
        await session.page.goto("https://example.com")
        # ... 把浏览器留给用户操作 ...
        return session  # 长生命周期：不要在这里关闭
    except Exception:
        await close_browser_session(session)
        raise

    # 稍后，等用户关闭浏览器窗口后回收：
    await session.wait_user_closed()
    await close_browser_session(session)
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from .anti_detection import anti_detection
from .profiles import BrowserProfile, get_profile

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger("apps.core")


@dataclasses.dataclass
class BrowserSessionHandle:
    """手动生命周期浏览器会话句柄。

    Attributes:
        profile: 创建会话所用的配置档案。
        browser: Playwright 异步 Browser（CloakBrowser 反检测启动）。
        context: 会话的 BrowserContext。
        page: 会话的首个 Page。
        playwright: 原生 Playwright driver 句柄。CloakBrowser 启动模式下为
            None（driver 的停止已内嵌在 browser.close() 里）；仅当工厂以裸
            Playwright 启动会话时才需要显式持有并 stop。
    """

    profile: BrowserProfile
    browser: Browser
    context: BrowserContext
    page: Page
    playwright: Playwright | None = None

    def is_connected(self) -> bool:
        """浏览器是否仍连接（未被用户关闭）。"""
        return self.browser.is_connected()

    async def wait_user_closed(self) -> None:
        """等待用户关闭浏览器窗口（无超时）。

        Playwright Python 的 Browser 没有 wait_for_event()（那是 Node API），
        且仅对外发射 ``disconnected`` 事件（浏览器被关闭/崩溃/断连时触发），
        用 asyncio.Event 桥接 ``on("disconnected")``。先注册再查
        is_connected，避免「注册前已断开」的竞态挂死。
        """
        closed = asyncio.Event()
        self.browser.on("disconnected", lambda _b: closed.set())
        if self.browser.is_connected():
            await closed.wait()


async def create_browser_async_manual(  # pragma: no cover
    profile: str | BrowserProfile = "default",
    **kwargs: Any,
) -> BrowserSessionHandle:
    """创建手动生命周期的异步浏览器会话。

    与 ``create_browser_async()`` 的原生 launch 分支等价，但不接管关闭：
    调用方持有返回的句柄防 GC，在浏览器使命结束（通常由用户关闭窗口）后
    调用 ``close_browser_session()`` 回收。

    Args:
        profile: 配置档案名称或实例（仅支持原生 launch；CDP/远程模式不支持）
        **kwargs: 传递给 BrowserProfile 的额外参数覆盖

    Returns:
        BrowserSessionHandle（含 browser / context / page）

    Example::

        session = await create_browser_async_manual("jtn")
        await session.page.goto("https://ims.jtn.com/")
        # ... 交给用户操作，稍后 close_browser_session(session)
    """
    if isinstance(profile, str):
        profile = get_profile(profile)

    if kwargs:
        profile = dataclasses.replace(profile, **kwargs)

    if profile.is_cdp or profile.is_remote:
        raise NotImplementedError(
            "手动生命周期会话目前仅支持原生 launch 模式；CDP/远程连接请使用 create_browser_async()。"
        )

    from cloakbrowser import launch_async

    from .launcher import ensure_browser_binary

    ensure_browser_binary()
    logger.info("启动手动生命周期浏览器 (profile=%s, headless=%s)", profile.name, profile.headless)
    browser = await launch_async(
        headless=profile.headless,
        humanize=profile.anti_detection,
    )

    context_args = profile.to_context_args()
    if profile.anti_detection:
        anti_opts = anti_detection.get_context_options()
        anti_opts.update(context_args)
        context_args = anti_opts

    context = await browser.new_context(**context_args)
    context.set_default_timeout(profile.timeout)
    context.set_default_navigation_timeout(profile.navigation_timeout)

    page = await context.new_page()
    page.on("dialog", lambda d: d.accept())

    # macOS 补充指纹补丁
    await anti_detection.apply_macos_patches_async(page)

    logger.info("手动生命周期浏览器已就绪 (profile=%s)", profile.name)
    return BrowserSessionHandle(profile=profile, browser=browser, context=context, page=page)


async def close_browser_session(session: BrowserSessionHandle) -> None:
    """回收手动生命周期浏览器会话（尽力而为，不上抛）。

    按 page → context → browser 顺序关闭。CloakBrowser 的 ``browser.close()``
    已内嵌 Playwright driver 的停止（pw.stop()）；仅当句柄携带原生
    playwright driver（playwright 非 None）时才显式补一次 stop。
    浏览器已被用户关闭时个别 close 抛错属预期，逐项吞掉并记录。
    """
    errors: list[str] = []
    for name, closeable in (
        ("page", session.page),
        ("context", session.context),
        ("browser", session.browser),
    ):
        try:
            await closeable.close()
        except Exception as e:
            errors.append(f"关闭 {name} 失败: {e}")

    if session.playwright is not None:
        try:
            await session.playwright.stop()
        except Exception as e:
            errors.append(f"停止 Playwright driver 失败: {e}")

    if errors:
        logger.warning("浏览器会话回收警告 (profile=%s): %s", session.profile.name, "; ".join(errors))
    else:
        logger.debug("浏览器会话已回收 (profile=%s)", session.profile.name)
