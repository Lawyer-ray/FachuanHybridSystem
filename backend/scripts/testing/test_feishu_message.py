#!/usr/bin/env python3
"""
测试飞书消息发送功能
"""

import os
import sys

import django

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_dir)
sys.path.append(os.path.join(backend_dir, "apiSystem"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.automation.services.chat.base import MessageContent
from apps.automation.services.chat.feishu_provider import FeishuChatProvider


def test_feishu_message():
    provider = FeishuChatProvider()

    if not provider.is_available():
        print("❌ 飞书配置不完整，无法测试")
        return False

    print("✅ 飞书配置检查通过")

    test_chat_id = "oc_eb6f465cf3fc9e3bdfc29160df54b6a5"

    content = MessageContent(title="📋 测试消息", text="这是一条测试消息，用于验证飞书消息发送功能是否正常工作。")

    try:
        print(f"🚀 开始发送测试消息到群聊: {test_chat_id}")

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
