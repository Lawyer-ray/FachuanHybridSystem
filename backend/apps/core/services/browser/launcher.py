"""原生 Playwright launch 模式。

通过 chromium.launch() 启动浏览器，适用于绝大多数场景。
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from .anti_detection import anti_detection
from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger("apps.core")


def _ensure_browsers_installed() -> None:
    """检测 Playwright 浏览器是否已安装，缺失时自动下载。

    通过检查 Playwright 浏览器缓存目录判断是否已安装，
    避免每次都执行 install 命令带来的启动延迟。
    """
    cache_dir = Path.home() / ".cache" / "ms-playwright"
    if not cache_dir.exists():
        # macOS 上 Playwright 也用 ~/Library/Caches/ms-playwright/
        cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache_dir.exists():
        cache_dir = Path.home() / ".local" / "share" / "ms-playwright"

    if not cache_dir.exists():
        _run_playwright_install()
        return

    # 检查是否有 chromium 目录（版本号随 Playwright 版本变化）
    if not any(d.name.startswith("chromium") for d in cache_dir.iterdir() if d.is_dir()):
        _run_playwright_install()


def _run_playwright_install() -> None:
    """执行 playwright install chromium。"""
    logger.info("Playwright 浏览器缺失，自动安装中...")
    subprocess.check_call(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdout=subprocess.DEVNULL,
    )
    logger.info("Playwright 浏览器安装完成")


def _launch_with_retry[T](factory: Callable[[], T], *, max_attempts: int = 2) -> T:
    """尝试启动浏览器，遇到 Executable 不存在时自动安装后重试。"""
    for attempt in range(1, max_attempts + 1):
        try:
            return factory()
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc) or attempt >= max_attempts:
                raise
            logger.warning("浏览器可执行文件缺失，自动安装后重试 (attempt %d/%d)", attempt, max_attempts)
            _run_playwright_install()
    raise RuntimeError("unreachable")


@contextmanager
def launch_browser(
    profile: BrowserProfile,
    *,
    session_id: str | None = None,
) -> Iterator[tuple[Page, BrowserContext]]:
    """启动浏览器并返回 (page, context)。

    自动管理 Playwright、Browser、Context、Page 的完整生命周期。

    Args:
        profile: 浏览器配置档案
        session_id: 非 None 时使用持久化 user_data_dir

    Yields:
        (page, context) 元组
    """
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None

    try:
        from playwright.sync_api import sync_playwright

        _ensure_browsers_installed()

        logger.info("启动 Playwright 浏览器 (profile=%s, headless=%s)", profile.name, profile.headless)
        playwright = sync_playwright().start()

        # 启动浏览器
        launch_args = profile.to_launch_args()

        # 如果有 session_id，使用持久化目录
        effective_user_data_dir = profile.user_data_dir
        if session_id and not effective_user_data_dir:
            effective_user_data_dir = str(Path(tempfile.gettempdir()) / "fachuan_browser_sessions" / session_id)

        if effective_user_data_dir:
            Path(effective_user_data_dir).mkdir(parents=True, exist_ok=True)
            context = _launch_with_retry(
                lambda: playwright.chromium.launch_persistent_context(
                    user_data_dir=effective_user_data_dir,
                    **launch_args,
                ),
            )
            # persistent context 本身就是 context，不需要单独的 browser
            browser = None
        else:
            browser = _launch_with_retry(
                lambda: playwright.chromium.launch(**launch_args),
            )

            # 创建 context
            context_args = profile.to_context_args()
            if profile.anti_detection:
                anti_opts = anti_detection.get_context_options()
                anti_opts.update(context_args)
                context_args = anti_opts

            context = browser.new_context(**context_args)

        # 设置超时
        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        # 创建 page
        page = context.new_page()

        # 注入 stealth
        if profile.anti_detection:
            anti_detection.apply_stealth(context)

        logger.info("浏览器已就绪 (profile=%s)", profile.name)
        yield page, context

    except Exception:
        logger.exception("浏览器操作失败 (profile=%s)", profile.name)
        raise
    finally:
        _cleanup(page, context, browser, playwright, profile)


def _cleanup(
    page: Page | None,
    context: BrowserContext | None,
    browser: Browser | None,
    playwright: Playwright | None,
    profile: BrowserProfile,
) -> None:
    """按顺序清理浏览器资源。"""
    errors = []

    if page is not None:
        try:
            page.close()
        except Exception as e:
            errors.append(f"关闭页面失败: {e}")

    # persistent context 时 context 和 browser 是同一个对象
    if context is not None and context is not browser:
        try:
            context.close()
        except Exception as e:
            errors.append(f"关闭上下文失败: {e}")

    if browser is not None:
        try:
            browser.close()
        except Exception as e:
            errors.append(f"关闭浏览器失败: {e}")

    if playwright is not None:
        try:
            playwright.stop()
        except Exception as e:
            errors.append(f"停止 Playwright 失败: {e}")

    if errors:
        logger.warning("清理过程中出现错误 (profile=%s): %s", profile.name, errors)
    else:
        logger.debug("浏览器资源已清理 (profile=%s)", profile.name)
