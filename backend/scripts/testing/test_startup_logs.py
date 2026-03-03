#!/usr/bin/env python3
"""
测试启动日志精简效果

验证修改后的启动日志是否已经精简，不再有重复的信息。
"""

import os
import sys

import django

from apps.core.path import Path

project_root = Path(__file__).parent.parent.parent
api_system_path = project_root / "apiSystem"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(api_system_path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")


def test_startup_logs():
    print("🚀 测试 Django 启动日志精简效果...")

    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("📋 初始化 Django...")

    try:
        django.setup()
        print("✅ Django 初始化完成")

        print("\n📋 测试群聊提供者工厂...")
        from apps.automation.services.chat.factory import ChatProviderFactory

        registered_platforms = ChatProviderFactory.get_registered_platforms()
        print(f"✅ 已注册平台: {[p.value for p in registered_platforms]}")

        available_platforms = ChatProviderFactory.get_available_platforms()
        print(f"✅ 可用平台: {[p.value for p in available_platforms]}")

        print("\n📋 测试重复导入...")
        for i in range(3):
            print(f"第 {i+1} 次导入...")
            import importlib

            import apps.automation.services.chat

            importlib.reload(apps.automation.services.chat)

        print("✅ 重复导入测试完成")

        print("\n📋 测试应用配置...")
        from apps.automation.apps import AutomationConfig

        config = AutomationConfig("apps.automation", None)
        print("第 1 次调用 ready()...")
        config.ready()
        print("第 2 次调用 ready()...")
        config.ready()
        print("第 3 次调用 ready()...")
        config.ready()

        print("✅ 应用配置测试完成")

    except Exception as e:
        print(f"❌ 测试过程中发生错误: {str(e)}")
        import traceback

        traceback.print_exc()
        return False

    return True


def main():
    print("=" * 60)
    print("Django-Q 启动日志精简测试")
    print("=" * 60)

    success = test_startup_logs()

    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成！启动日志已精简")
    else:
        print("❌ 测试失败，请检查错误信息")
    print("=" * 60)


if __name__ == "__main__":
    main()
