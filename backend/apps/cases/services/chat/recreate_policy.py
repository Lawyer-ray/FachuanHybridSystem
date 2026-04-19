"""Business logic services."""

from __future__ import annotations

from typing import Any


class ChatRecreatePolicy:
    def should_recreate(self, *, result: Any) -> bool:
        if not result.error_code:
            return False

        # 飞书群聊不存在的错误码
        feishu_chat_not_found_codes = [
            "230002",
            "230003",
            "230004",
            "99991663",
            "99991664",
        ]

        # 钉钉群聊不存在的错误码
        dingtalk_chat_not_found_codes = [
            "invalidParameter.chatId",  # 群聊ID无效
            "groupNotFound",  # 群聊不存在
            "invalidChatId",  # 群聊ID不合法
        ]

        # Telegram 话题/群组不存在的错误码
        telegram_chat_not_found_codes = [
            "400",  # Bad Request: chat not found / topic not found
            "403",  # Forbidden: bot is not a member of the group chat
        ]

        error_code = str(result.error_code)
        if error_code in feishu_chat_not_found_codes:
            return True
        if error_code in dingtalk_chat_not_found_codes:
            return True
        if error_code in telegram_chat_not_found_codes:
            return True

        error_message = result.message or ""
        chat_not_found_keywords = [
            "群聊不存在",
            "群聊已解散",
            "chat not found",
            "chat dissolved",
            "bot not in chat",
            "机器人不在群聊中",
            "topic not found",
            "话题不存在",
            "TOPIC_NOT_FOUND",
            "group not found",
            "群组不存在",
        ]

        for keyword in chat_not_found_keywords:
            if keyword.lower() in error_message.lower():
                return True

        return False
