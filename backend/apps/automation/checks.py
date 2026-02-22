"""
系统检查 - 确保爬虫依赖正确配置
"""

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register


@register()
def check_scraper_dependencies(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """检查爬虫依赖"""
    errors: list[CheckMessage] = []

    # 检查 Playwright
    try:
        import playwright  # 检查是否安装
    except ImportError:
        errors.append(
            Error(
                "Playwright 未安装",
                hint="运行: uv add playwright && playwright install chromium",
                id="automation.E001",
            )
        )

    # 检查加密密钥
    if not hasattr(settings, "SCRAPER_ENCRYPTION_KEY"):
        errors.append(
            Warning(
                "未配置 SCRAPER_ENCRYPTION_KEY",
                hint="在 settings.py 中添加: SCRAPER_ENCRYPTION_KEY = Fernet.generate_key()",
                id="automation.W001",
            )
        )

    # 检查 MEDIA_ROOT
    if not hasattr(settings, "MEDIA_ROOT"):
        errors.append(
            Error(
                "未配置 MEDIA_ROOT",
                hint="在 settings.py 中配置 MEDIA_ROOT",
                id="automation.E002",
            )
        )

    return errors
