"""群聊相关 DTO"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatResult:
    """群聊操作结果"""

    success: bool
    chat_id: str | None = None
    chat_name: str | None = None
    message: str | None = None
    error_code: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class MessageContent:
    """消息内容"""

    title: str
    text: str
    file_path: str | None = None


@dataclass
class PlatformNotificationResult:
    """单个平台的通知结果"""

    platform: str
    success: bool
    chat_id: str | None = None
    sent_at: str | None = None
    file_count: int = 0
    sent_file_count: int = 0
    error: str | None = None
    provider_summary: str | None = None


@dataclass
class MultiPlatformNotificationResult:
    """多平台通知汇总结果"""

    attempts: list[PlatformNotificationResult] = field(default_factory=list)

    @property
    def any_success(self) -> bool:
        """任一平台成功即为成功"""
        return any(r.success for r in self.attempts)

    @property
    def all_success(self) -> bool:
        """所有平台都成功"""
        return len(self.attempts) > 0 and all(r.success for r in self.attempts)

    @property
    def failed_platforms(self) -> list[str]:
        """失败的平台列表"""
        return [r.platform for r in self.attempts if not r.success]

    @property
    def successful_platforms(self) -> list[str]:
        """成功的平台列表"""
        return [r.platform for r in self.attempts if r.success]

    def to_notification_results(self) -> dict[str, Any]:
        """转换为持久化到 CourtSMS.notification_results 的 JSON 结构"""
        results: dict[str, Any] = {}
        for r in self.attempts:
            results[r.platform] = {
                "success": r.success,
                "chat_id": r.chat_id,
                "sent_at": r.sent_at,
                "file_count": r.file_count,
                "sent_file_count": r.sent_file_count,
                "error": r.error,
                "provider_summary": r.provider_summary,
            }
        return results
