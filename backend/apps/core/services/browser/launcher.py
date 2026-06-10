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

from .anti_detection import anti_detection
from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.core")


@contextmanager
def launch_browser(  # pragma: no cover
    profile: BrowserProfile,
    *,
    session_id: str | None = None,
) -> Iterator[tuple[Page, BrowserContext]]:
    """通过 CloakBrowser 启动浏览器并返回 (page, context)。

    Args:
        profile: 浏览器配置档案
        session_id: 非 None 时使用持久化 user_data_dir

    Yields:
        (page, context) 元组
    """
    from cloakbrowser import ensure_binary, launch, launch_persistent_context

    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None

    try:
        ensure_binary()

        logger.info("启动 CloakBrowser (profile=%s, headless=%s)", profile.name, profile.headless)

        # 解析 user_data_dir
        effective_user_data_dir = profile.user_data_dir
        if session_id and not effective_user_data_dir:
            effective_user_data_dir = str(Path(tempfile.gettempdir()) / "fachuan_browser_sessions" / session_id)

        # CloakBrowser 启动参数
        launch_kwargs: dict[str, Any] = {
            "headless": profile.headless,
            "humanize": profile.anti_detection,
        }
        if profile.proxy:
            launch_kwargs["proxy"] = profile.proxy

        if effective_user_data_dir:
            # 持久化上下文（使用 launch_persistent_context）
            Path(effective_user_data_dir).mkdir(parents=True, exist_ok=True)
            context = launch_persistent_context(
                user_data_dir=effective_user_data_dir,
                **launch_kwargs,
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            # 普通启动
            browser = launch(**launch_kwargs)
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

        # dialog 处理（CloakBrowser 继承 Playwright 的 dialog 拦截行为）
        assert page is not None
        page.on("dialog", lambda d: d.accept())  # type: ignore[attr-defined]

        # macOS 补充指纹补丁（26→58 差异）
        anti_detection.apply_macos_patches(page)

        logger.info("CloakBrowser 已就绪 (profile=%s)", profile.name)
        yield page, context

    except Exception:
        logger.exception("CloakBrowser 启动失败 (profile=%s)", profile.name)
        raise
    finally:
        _cleanup(page, context, browser)


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
