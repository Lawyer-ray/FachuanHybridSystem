#!/usr/bin/env python3
"""
飞书群聊诊断脚本

用于诊断群聊创建问题，检查配置、权限和群聊状态。
"""

import os
import sys
import json
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / 'apiSystem'))

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
import django
django.setup()

from apps.automation.services.chat.feishu_provider import FeishuChatProvider
from apps.automation.services.chat.owner_config_manager import OwnerConfigManager


def check_feishu_config():
    """检查飞书配置"""
    print("=== 飞书配置检查 ===")
    
    provider = FeishuChatProvider()
    
    print(f"提供者可用性: {provider.is_available()}")
    print(f"配置信息: {list(provider.config.keys())}")
    
    # 检查关键配置
    app_id = provider.config.get('APP_ID')
    app_secret = provider.config.get('APP_SECRET')
    
    print(f"APP_ID: {'已配置' if app_id else '未配置'}")
    print(f"APP_SECRET: {'已配置' if app_secret else '未配置'}")
    
    return provider


def check_owner_config():
    """检查群主配置"""
    print("\n=== 群主配置检查 ===")
    
    manager = OwnerConfigManager()
    
    default_owner = manager.get_default_owner_id()
    print(f"默认群主ID: {default_owner}")
    
    config_summary = manager.get_config_summary()
    print(f"配置摘要: {json.dumps(config_summary, indent=2, ensure_ascii=False)}")
    
    # 测试有效群主ID获取
    effective_owner = manager.get_effective_owner_id(None)
    print(f"有效群主ID: {effective_owner}")
    
    # 验证群主ID格式
    if effective_owner:
        is_valid = manager.validate_owner_id(effective_owner)
        print(f"群主ID格式验证: {'通过' if is_valid else '失败'}")
    
    return manager, effective_owner


def test_access_token(provider):
    """测试访问令牌获取"""
    print("\n=== 访问令牌测试 ===")
    
    try:
        token = provider._get_tenant_access_token()
        print(f"访问令牌获取: 成功")
        print(f"令牌前缀: {token[:20]}...")
        return True
    except Exception as e:
        print(f"访问令牌获取失败: {str(e)}")
        return False


def get_chat_info(provider, chat_id):
    """获取群聊详细信息"""
    print(f"\n=== 群聊信息查询: {chat_id} ===")
    
    try:
        result = provider.get_chat_info(chat_id)
        
        if result.success:
            print("群聊信息获取成功:")
            print(json.dumps(result.raw_response, indent=2, ensure_ascii=False))
            
            # 检查群主信息
            chat_data = result.raw_response.get('data', {})
            owner_id = chat_data.get('owner_id')
            members = chat_data.get('members', [])
            
            print(f"\n群主ID: {owner_id}")
            print(f"成员数量: {len(members)}")
            
            if members:
                print("群成员:")
                for i, member in enumerate(members[:5]):  # 只显示前5个成员
                    print(f"  {i+1}. {member.get('name', '未知')} ({member.get('member_id', '未知')})")
            
            return chat_data
        else:
            print(f"群聊信息获取失败: {result.message}")
            return None
            
    except Exception as e:
        print(f"获取群聊信息时发生错误: {str(e)}")
        return None


def get_owner_info(provider, chat_id):
    """获取群主详细信息"""
    print(f"\n=== 群主信息查询: {chat_id} ===")
    
    try:
        owner_info = provider.get_chat_owner_info(chat_id)
        print("群主信息:")
        print(json.dumps(owner_info, indent=2, ensure_ascii=False))
        return owner_info
    except Exception as e:
        print(f"获取群主信息时发生错误: {str(e)}")
        return None


def verify_owner_setting(provider, chat_id, expected_owner_id):
    """验证群主设置"""
    print(f"\n=== 群主设置验证 ===")
    
    if not expected_owner_id:
        print("没有期望的群主ID，跳过验证")
        return False
    
    try:
        is_correct = provider.verify_owner_setting(chat_id, expected_owner_id)
        print(f"群主设置验证结果: {'正确' if is_correct else '错误'}")
        return is_correct
    except Exception as e:
        print(f"验证群主设置时发生错误: {str(e)}")
        return False


def main():
    print("=== 飞书群聊诊断工具 ===")
    
    # 1. 检查配置
    provider = check_feishu_config()
    manager, effective_owner = check_owner_config()
    
    # 2. 测试访问令牌
    if not test_access_token(provider):
        print("访问令牌获取失败，无法继续诊断")
        return
    
    # 3. 获取要诊断的群聊ID
    chat_id = input("\n请输入要诊断的群聊ID (例如: oc_dd737f9e3d7d64f8d9f6474fb59eec49): ").strip()
    
    if not chat_id:
        print("未提供群聊ID，退出诊断")
        return
    
    # 4. 获取群聊信息
    chat_data = get_chat_info(provider, chat_id)
    
    # 5. 获取群主信息
    owner_info = get_owner_info(provider, chat_id)
    
    # 6. 验证群主设置
    verify_owner_setting(provider, chat_id, effective_owner)
    
    # 7. 总结诊断结果
    print("\n=== 诊断总结 ===")
    
    if chat_data:
        actual_owner = chat_data.get('owner_id')
        print(f"群聊存在: 是")
        print(f"实际群主: {actual_owner}")
        print(f"期望群主: {effective_owner}")
        print(f"群主匹配: {'是' if actual_owner == effective_owner else '否'}")
        
        # 分析可能的问题
        if not actual_owner:
            print("\n⚠️  问题: 群聊没有设置群主")
            print("   可能原因: 创建群聊时没有正确设置owner_id参数")
        elif actual_owner != effective_owner:
            print(f"\n⚠️  问题: 群主不匹配")
            print(f"   实际群主: {actual_owner}")
            print(f"   期望群主: {effective_owner}")
            print("   可能原因: 配置的群主ID不正确或格式有误")
        else:
            print("\n✅ 群主设置正确")
            print("   如果你看不到群聊，可能的原因:")
            print("   1. 你的飞书账号不是配置的群主账号")
            print("   2. 群聊创建在不同的飞书租户中")
            print("   3. 飞书客户端需要刷新或重新登录")
    else:
        print("群聊不存在或无法访问")


if __name__ == "__main__":
    main()