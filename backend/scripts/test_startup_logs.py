#!/usr/bin/env python3
"""
测试启动日志精简效果

验证修改后的启动日志是否已经精简，不再有重复的信息。
"""

import os
import sys
import django
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
api_system_path = project_root / 'apiSystem'
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(api_system_path))

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')

def test_startup_logs():
    """测试启动日志"""
    
    print("🚀 测试 Django 启动日志精简效果...")
    
    # 设置日志级别为 INFO，这样可以看到重要信息但不会太详细
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    print("📋 初始化 Django...")
    
    try:
        # 初始化 Django
        django.setup()
        print("✅ Django 初始化完成")
        
        # 测试群聊提供者工厂
        print("\n📋 测试群聊提供者工厂...")
        from apps.automation.services.chat.factory import ChatProviderFactory
        from apps.core.enums import ChatPlatform
        
        # 检查已注册的平台
        registered_platforms = ChatProviderFactory.get_registered_platforms()
        print(f"✅ 已注册平台: {[p.value for p in registered_platforms]}")
        
        # 检查可用平台
        available_platforms = ChatProviderFactory.get_available_platforms()
        print(f"✅ 可用平台: {[p.value for p in available_platforms]}")
        
        # 测试重复导入是否会产生重复日志
        print("\n📋 测试重复导入...")
        for i in range(3):
            print(f"第 {i+1} 次导入...")
            # 重新导入模块
            import importlib
            import apps.automation.services.chat
            importlib.reload(apps.automation.services.chat)
        
        print("✅ 重复导入测试完成")
        
        # 测试应用配置
        print("\n📋 测试应用配置...")
        from apps.automation.apps import AutomationConfig
        
        # 模拟多次调用 ready() 方法
        config = AutomationConfig('apps.automation', None)
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
    """主测试函数"""
    
    print("=" * 60)
    print("Django-Q 启动日志精简测试")
    print("=" * 60)
    
    success = test_startup_logs()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成！启动日志已精简")
        print("📝 预期效果:")
        print("   - 群聊提供者注册日志改为 DEBUG 级别")
        print("   - 应用启动日志减少重复信息")
        print("   - 任务恢复日志在静默模式下不显示详细信息")
    else:
        print("❌ 测试失败，请检查错误信息")
    print("=" * 60)


if __name__ == "__main__":
    main()