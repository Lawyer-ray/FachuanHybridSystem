"""CloakBrowser 启动模式。

通过 CloakBrowser launch() 启动浏览器，内置 C++ 级反检测。
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .anti_detection import anti_detection
from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.core")


class BrowserInstallError(RuntimeError):
    """Playwright Chromium 不可用，携带可操作的修复指引。"""


def _assert_installed(executable: str | None) -> str:
    """校验 Playwright 报出的 Chromium 路径确实存在，否则给出修复指引。"""
    if not executable or not Path(executable).exists():
        raise BrowserInstallError(
            f"Playwright Chromium 未安装。\n期望位置: {executable}\n修复：.venv/bin/playwright install chromium"
        )
    return str(executable)


def ensure_browser_binary() -> str:
    """确保 Playwright Chromium 可用，返回可执行文件路径（**同步版**）。

    严格不能在事件循环线程里调：``sync_playwright()`` 会在 asyncio 循环内
    直接抛 ``It looks like you are using Playwright Sync API inside the asyncio
    loop``。异步路径请用 ``ensure_browser_binary_async()``。

    为什么不再做「自动下载」：之前用 CloakBrowser 的 ``ensure_binary()`` 会在
    首次使用时联网拉 Pro 二进制并要求 license key，在无终端的 worker/CI 里
    直接抛错，把「浏览器没装」这个简单事实包装成了授权问题。Playwright 的
    安装是一次性显式动作，不该在任务执行路径上隐式触发。
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            executable = pw.chromium.executable_path
    except Exception as exc:  # playwright 自身不可用（缺依赖/驱动损坏）
        raise BrowserInstallError(
            "Playwright 初始化失败，无法获取 Chromium 路径。\n"
            "修复：uv add playwright && .venv/bin/playwright install chromium\n"
            f"原始错误: {exc}"
        ) from exc
    return _assert_installed(executable)


async def ensure_browser_binary_async() -> str:
    """确保 Playwright Chromium 可用，返回可执行文件路径（**异步版**）。"""
    from playwright.async_api import async_playwright

    try:
        pw = await async_playwright().start()
    except Exception as exc:
        raise BrowserInstallError(
            "Playwright 初始化失败，无法获取 Chromium 路径。\n"
            "修复：uv add playwright && .venv/bin/playwright install chromium\n"
            f"原始错误: {exc}"
        ) from exc
    try:
        return _assert_installed(pw.chromium.executable_path)
    finally:
        await pw.stop()


def launch_browser_instance(profile: BrowserProfile) -> Browser:
    """按 profile 启动一个 Playwright Chromium 实例（非持久化）。

    ``service.py`` 的进程级复用路径用它；持久化/异步路径分别走
    ``launch_persistent_context`` 与 ``launch_async``。
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        return pw.chromium.launch(
            headless=profile.headless,
            proxy={"server": profile.proxy} if profile.proxy else None,
            args=profile.launch_args or None,
        )
    except Exception:
        pw.stop()
        raise


@contextmanager
def launch_browser(  # pragma: no cover
    profile: BrowserProfile,
    *,
    session_id: str | None = None,
) -> Iterator[tuple[Page, BrowserContext]]:
    """通过 Playwright 启动浏览器并返回 (page, context)。

    Args:
        profile: 浏览器配置档案
        session_id: 非 None 时使用持久化 user_data_dir

    Yields:
        (page, context) 元组
    """
    from playwright.sync_api import sync_playwright

    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    pw: Any = None

    try:
        ensure_browser_binary()

        logger.info("启动 Playwright Chromium (profile=%s, headless=%s)", profile.name, profile.headless)

        # 解析 user_data_dir
        effective_user_data_dir = profile.user_data_dir
        if session_id and not effective_user_data_dir:
            effective_user_data_dir = str(Path(tempfile.gettempdir()) / "fachuan_browser_sessions" / session_id)

        pw = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": profile.headless,
            "proxy": {"server": profile.proxy} if profile.proxy else None,
            "args": profile.launch_args or None,
        }

        if effective_user_data_dir:
            # 持久化上下文（使用 launch_persistent_context）
            Path(effective_user_data_dir).mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                user_data_dir=effective_user_data_dir,
                **launch_kwargs,
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            # 普通启动
            browser = pw.chromium.launch(**launch_kwargs)
            context_args = profile.to_context_args()
            if profile.anti_detection:
                anti_opts = anti_detection.get_context_options()
                anti_opts.update(context_args)
                context_args = anti_opts
            context = browser.new_context(**context_args)
            page = context.new_page()

        # 超时设置
        assert context is not None
        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        # dialog 处理（Playwright 默认不自动消化 dialog，会阻塞后续操作）
        assert page is not None
        page.on("dialog", lambda d: d.accept())

        # macOS 补充指纹补丁（26→58 差异）
        anti_detection.apply_macos_patches(page)

        logger.info("Playwright Chromium 已就绪 (profile=%s)", profile.name)
        yield page, context

    except Exception:
        logger.exception("Playwright Chromium 启动失败 (profile=%s)", profile.name)
        raise
    finally:
        _cleanup(page, context, browser)
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                logger.debug("停止 Playwright 失败（已忽略）", exc_info=True)


def _cleanup(  # pragma: no cover
    page: Page | None,
    context: BrowserContext | None,
    browser: Browser | None,
) -> None:
    """按顺序清理浏览器资源。"""
    errors: list[str] = []

    for name, closeable in [("page", page), ("context", context), ("browser", browser)]:
        if closeable is not None:
            try:
                closeable.close()
            except Exception as e:
                errors.append(f"关闭 {name} 失败: {e}")

    if errors:
        logger.warning("清理警告: %s", "; ".join(errors))
    else:
        logger.debug("浏览器资源已清理")
