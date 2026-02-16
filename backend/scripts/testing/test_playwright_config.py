#!/usr/bin/env python3
"""
测试 Playwright 截图配置
验证截图保存路径是否正确配置
"""

import os
import sys

from apps.core.path import Path

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "apiSystem"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()

from apps.automation.utils.playwright_config import get_playwright_downloads_dir, get_screenshot_path


def test_playwright_config():
    print("🔧 测试 Playwright 截图配置...")

    downloads_dir = get_playwright_downloads_dir()
    print(f"📁 下载目录: {downloads_dir}")

    if Path(downloads_dir).exists():
        print("✅ 下载目录已创建")
    else:
        print("❌ 下载目录不存在")
        return False

    screenshot_path = get_screenshot_path("test")
    print(f"📸 截图路径: {screenshot_path}")

    if "backend/media/automation/screenshots" in screenshot_path:
        print("✅ 截图路径格式正确")
    else:
        print("❌ 截图路径格式错误")
        return False

    env_dir = os.environ.get("PLAYWRIGHT_DOWNLOADS_DIR")
    if env_dir:
        print(f"🌍 环境变量 PLAYWRIGHT_DOWNLOADS_DIR: {env_dir}")
        print("✅ 环境变量已设置")
    else:
        print("⚠️  环境变量 PLAYWRIGHT_DOWNLOADS_DIR 未设置")

    print("🎉 Playwright 配置测试完成！")
    return True


if __name__ == "__main__":
    test_playwright_config()
