"""
Playwright 配置工具
统一管理 Playwright 截图和下载路径
"""

import os
from pathlib import Path

from django.conf import settings


def get_playwright_downloads_dir() -> str:
    """
    获取 Playwright 下载目录
    统一设置为项目的 media/automation/screenshots 目录
    """
    project_root = Path(settings.BASE_DIR).parent  # 从 apiSystem 到 backend
    downloads_dir = project_root / "media" / "automation" / "screenshots"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return str(downloads_dir.resolve())


def get_screenshot_path(name: str = "screenshot") -> str:
    """
    生成截图文件路径
    """
    from datetime import datetime

    downloads_dir = Path(get_playwright_downloads_dir())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    return str(downloads_dir / filename)


def setup_playwright_env() -> None:
    """设置 Playwright 环境变量，应在应用启动时显式调用"""
    os.environ.setdefault("PLAYWRIGHT_DOWNLOADS_DIR", get_playwright_downloads_dir())
