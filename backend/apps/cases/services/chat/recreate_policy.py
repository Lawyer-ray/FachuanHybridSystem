"""Business logic services."""

from __future__ import annotations

from typing import Any


class ChatRecreatePolicy:
    def should_recreate(self, *, result: Any) -> bool:
        if not result.error_code:
            return False

        feishu_chat_not_found_codes = [
            "230002",
            "230003",
            "230004",
            "99991663",
            "99991664",
        ]

        error_code = str(result.error_code)
        if error_code in feishu_chat_not_found_codes:
            return True

        error_message = result.message or ""
        chat_not_found_keywords = [
            "群聊不存在",
            "群聊已解散",
            "chat not found",
            "chat dissolved",
            "bot not in chat",
            "机器人不在群聊中",
        ]

        for keyword in chat_not_found_keywords:
            if keyword.lower() in error_message.lower():
                return True

        return False
