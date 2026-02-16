"""
Playwright 配置工具
统一管理 Playwright 截图和下载路径
"""

import os

from django.conf import settings

from apps.core.path import Path


def get_playwright_downloads_dir() -> str:
    """
    获取 Playwright 下载目录
    统一设置为项目的 media/automation/screenshots 目录
    """
    # 使用项目根目录下的 backend/media 目录
    project_root = Path(settings.BASE_DIR).parent  # 从 apiSystem 到 backend
    downloads_dir = project_root / "media" / "automation" / "screenshots"
    downloads_dir.makedirs_p()
    return str(downloads_dir.abspath())


def get_screenshot_path(name: str = "screenshot") -> str:
    """
    生成截图文件路径
    """
    from datetime import datetime

    downloads_dir = Path(get_playwright_downloads_dir())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    return str(downloads_dir / filename)


# 设置环境变量,确保 MCP Playwright 使用正确的下载目录
os.environ["PLAYWRIGHT_DOWNLOADS_DIR"] = get_playwright_downloads_dir()
