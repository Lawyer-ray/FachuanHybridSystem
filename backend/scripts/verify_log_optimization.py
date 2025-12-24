#!/usr/bin/env python3
"""
验证日志优化修改

检查代码修改是否正确实现了日志精简功能。
"""

import re
from pathlib import Path


def check_factory_log_level():
    """检查群聊提供者工厂的日志级别"""
    
    file_path = Path(__file__).parent.parent / 'apps/automation/services/chat/factory.py'
    
    if not file_path.exists():
        print("❌ ChatProviderFactory 文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    # 检查注册日志是否改为 DEBUG 级别
    if 'logger.debug(f"已注册群聊提供者:' in content:
        print("✅ 群聊提供者注册日志已改为 DEBUG 级别")
        return True
    elif 'logger.info(f"已注册群聊提供者:' in content:
        print("❌ 群聊提供者注册日志仍为 INFO 级别")
        return False
    else:
        print("⚠️  未找到群聊提供者注册日志")
        return False


def check_apps_config():
    """检查应用配置的日志优化"""
    
    file_path = Path(__file__).parent.parent / 'apps/automation/apps.py'
    
    if not file_path.exists():
        print("❌ AutomationConfig 文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    checks = [
        # 检查是否添加了重复执行防护
        (r'if hasattr\(self, \'_recovery_scheduled\'\)', "添加重复执行防护"),
        
        # 检查是否将详细日志改为 DEBUG
        (r'logger\.debug\("安排延迟恢复', "启动日志改为 DEBUG 级别"),
        
        # 检查是否将恢复任务日志改为 DEBUG
        (r'logger\.debug\("开始执行延迟的', "恢复任务日志改为 DEBUG 级别"),
        
        # 检查是否设置了静默输出
        (r'verbosity=0', "设置静默输出模式"),
    ]
    
    print("\n=== 检查应用配置优化 ===")
    all_passed = True
    
    for pattern, description in checks:
        if re.search(pattern, content):
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            all_passed = False
    
    return all_passed


def check_management_command():
    """检查管理命令的日志优化"""
    
    file_path = Path(__file__).parent.parent / 'apps/automation/management/commands/recover_court_sms_tasks.py'
    
    if not file_path.exists():
        print("❌ 管理命令文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    checks = [
        # 检查是否添加了 verbose 参数控制
        (r'verbose = options\.get\(\'verbosity\', 1\) > 0', "添加详细输出控制"),
        
        # 检查是否在静默模式下减少输出
        (r'if verbose:', "添加条件输出控制"),
        
        # 检查方法签名是否添加了 verbose 参数
        (r'def _reset_stuck_tasks\(self, max_age, verbose=True\)', "重置任务方法添加 verbose 参数"),
        
        # 检查恢复方法签名
        (r'def _recover_incomplete_tasks\(self, max_age, verbose=True\)', "恢复任务方法添加 verbose 参数"),
    ]
    
    print("\n=== 检查管理命令优化 ===")
    all_passed = True
    
    for pattern, description in checks:
        if re.search(pattern, content):
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            all_passed = False
    
    return all_passed


def check_chat_init():
    """检查群聊服务初始化的重复注册防护"""
    
    file_path = Path(__file__).parent.parent / 'apps/automation/services/chat/__init__.py'
    
    if not file_path.exists():
        print("❌ 群聊服务初始化文件不存在")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    
    # 检查是否添加了重复注册防护
    if 'if ChatProviderFactory.is_platform_registered(ChatPlatform.FEISHU):' in content:
        print("✅ 群聊服务添加重复注册防护")
        return True
    else:
        print("❌ 群聊服务未添加重复注册防护")
        return False


def main():
    """主验证函数"""
    
    print("🔍 验证 Django-Q 启动日志精简优化...")
    
    factory_ok = check_factory_log_level()
    apps_ok = check_apps_config()
    command_ok = check_management_command()
    init_ok = check_chat_init()
    
    print(f"\n📊 验证结果:")
    print(f"群聊提供者工厂: {'✅ 通过' if factory_ok else '❌ 失败'}")
    print(f"应用配置优化: {'✅ 通过' if apps_ok else '❌ 失败'}")
    print(f"管理命令优化: {'✅ 通过' if command_ok else '❌ 失败'}")
    print(f"重复注册防护: {'✅ 通过' if init_ok else '❌ 失败'}")
    
    if factory_ok and apps_ok and command_ok and init_ok:
        print("\n🎉 所有优化验证通过！Django-Q 启动日志已成功精简。")
        print("\n📝 优化效果:")
        print("   ✅ 群聊提供者注册日志改为 DEBUG 级别，减少重复信息")
        print("   ✅ 应用启动添加重复执行防护，避免多次输出")
        print("   ✅ 任务恢复在静默模式下不显示详细信息")
        print("   ✅ 管理命令支持详细输出控制")
        return True
    else:
        print("\n⚠️  部分优化验证失败，请检查代码修改。")
        return False


if __name__ == "__main__":
    main()