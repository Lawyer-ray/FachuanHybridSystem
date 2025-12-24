#!/usr/bin/env python3
"""
测试飞书消息发送功能

用于验证修复后的飞书消息发送是否正常工作。

使用方法：
cd backend
source venv311/bin/activate  # 激活虚拟环境
python scripts/test_feishu_message.py
"""

import os
import sys
import django

# 设置 Django 环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.apiSystem.settings')
django.setup()

from apps.automation.services.chat.feishu_provider import FeishuChatProvider
from apps.automation.services.chat.base import MessageContent


def test_feishu_message():
    """测试飞书消息发送"""
    
    # 创建飞书提供者
    provider = FeishuChatProvider()
    
    # 检查配置
    if not provider.is_available():
        print("❌ 飞书配置不完整，无法测试")
        return False
    
    print("✅ 飞书配置检查通过")
    
    # 测试群聊ID（请替换为实际的群聊ID）
    test_chat_id = "oc_eb6f465cf3fc9e3bdfc29160df54b6a5"  # 从错误日志中获取的群聊ID
    
    # 创建测试消息
    content = MessageContent(
        title="📋 测试消息",
        text="这是一条测试消息，用于验证飞书消息发送功能是否正常工作。"
    )
    
    try:
        print(f"🚀 开始发送测试消息到群聊: {test_chat_id}")
        
        # 发送消息
        result = provider.send_message(test_chat_id, content)
        
        if result.success:
            print("✅ 消息发送成功！")
            print(f"   消息ID: {result.raw_response.get('data', {}).get('message_id', 'N/A')}")
            return True
        else:
            print(f"❌ 消息发送失败: {result.message}")
            return False
            
    except Exception as e:
        print(f"❌ 发送消息时出现异常: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("飞书消息发送测试")
    print("=" * 50)
    
    success = test_feishu_message()
    
    print("=" * 50)
    if success:
        print("🎉 测试通过！飞书消息发送功能正常")
    else:
        print("💥 测试失败！请检查配置和网络连接")
    print("=" * 50)