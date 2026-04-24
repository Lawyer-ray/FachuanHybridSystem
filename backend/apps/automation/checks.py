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

    # 检查 Playwright（降级为 Warning：一张网等平台可通过纯 API 工作）
    try:
        import playwright  # 检查是否安装
    except ImportError:
        errors.append(
            Warning(
                "Playwright 未安装，部分平台（广东电子送达、简易送达、司法送达网）的文书下载功能不可用",
                hint="运行: uv add playwright && playwright install chromium；一张网(法院执行网)可通过纯 API 正常下载",
                id="automation.W002",
            )
        )

    # 检查加密密钥
    encryption_key = getattr(settings, "SCRAPER_ENCRYPTION_KEY", None)
    if not encryption_key:
        errors.append(
            Warning(
                "未配置 SCRAPER_ENCRYPTION_KEY",
                hint="设置环境变量 SCRAPER_ENCRYPTION_KEY 或在系统配置中设置固定密钥",
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
