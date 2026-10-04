"""SMSNotificationService 单元测试 — 多平台群聊通知扇出（sync + async）。

mock ChatProviderFactory / case_chat_service，不发送真实消息。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.sms_notification_service import SMSNotificationService
from apps.core.models.enums import ChatPlatform


def _sms(case: Any = None) -> Any:
    return SimpleNamespace(id=1, case=case, content="【广东法院】您的文书已到达")


def _case() -> Any:
    return SimpleNamespace(id=99)


def _chat_service(ok: bool = True, chat_id: str = "oc_123") -> MagicMock:
    svc = MagicMock()
    svc.get_or_create_chat.return_value = SimpleNamespace(chat_id=chat_id)
    if ok:
        svc.send_document_notification.return_value = SimpleNamespace(success=True, message="发送成功")
    else:
        svc.send_document_notification.return_value = SimpleNamespace(success=False, message="机器人不可用")
    return svc


class TestSendCaseChatNotification:
    def test_sms_without_case_returns_failure_attempt(self) -> None:
        result = SMSNotificationService(case_chat_service=_chat_service()).send_case_chat_notification(_sms(None))

        assert result.any_success is False
        assert len(result.attempts) == 1
        assert result.attempts[0].platform == "none"
        assert "未绑定案件" in result.attempts[0].error

    def test_no_available_platforms_returns_failure(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service())
        with patch.object(svc, "_get_available_platforms", return_value=[]):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "没有可用的群聊平台" in result.attempts[0].error

    def test_single_platform_success(self) -> None:
        chat = _chat_service(ok=True)
        svc = SMSNotificationService(case_chat_service=chat)
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(_sms(_case()), document_paths=["/tmp/a.pdf", "/tmp/b.pdf"])

        assert result.any_success is True
        assert result.successful_platforms == [ChatPlatform.FEISHU.value]
        attempt = result.attempts[0]
        assert attempt.success is True
        assert attempt.chat_id == "oc_123"
        assert attempt.file_count == 2
        assert attempt.sent_file_count == 2
        assert attempt.sent_at is not None
        # 文本通知调用带了正确参数
        kwargs = chat.send_document_notification.call_args.kwargs
        assert kwargs["case_id"] == 99
        assert kwargs["platform"] is ChatPlatform.FEISHU
        assert kwargs["document_paths"] == ["/tmp/a.pdf", "/tmp/b.pdf"]
        assert kwargs["sms_content"] == "【广东法院】您的文书已到达"

    def test_send_result_failure_reports_error(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service(ok=False))
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "机器人不可用" in result.attempts[0].error

    def test_get_or_create_chat_failure(self) -> None:
        chat = _chat_service()
        chat.get_or_create_chat.side_effect = RuntimeError("群聊服务不可用")
        svc = SMSNotificationService(case_chat_service=chat)
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "获取或创建群聊失败" in result.attempts[0].error

    def test_send_raises_exception(self) -> None:
        chat = _chat_service()
        chat.send_document_notification.side_effect = RuntimeError("网络错误")
        svc = SMSNotificationService(case_chat_service=chat)
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "发送通知异常" in result.attempts[0].error

    def test_multi_platform_partial_success_is_overall_success(self) -> None:
        chat = _chat_service()
        svc = SMSNotificationService(case_chat_service=chat)
        platforms = [ChatPlatform.FEISHU, ChatPlatform.WECHAT_WORK]
        chat.send_document_notification.side_effect = [
            RuntimeError("第一个平台挂了"),
            SimpleNamespace(success=True, message="ok"),
        ]
        with patch.object(svc, "_get_available_platforms", return_value=platforms):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is True
        assert result.successful_platforms == [ChatPlatform.WECHAT_WORK.value]
        assert result.failed_platforms == [ChatPlatform.FEISHU.value]

    def test_chat_service_access_failure_catches_outer(self) -> None:
        class _ExplodingService(SMSNotificationService):
            @property
            def case_chat_service(self) -> Any:
                raise RuntimeError("定位聊天服务失败")

        svc = _ExplodingService()
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = svc.send_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "平台通知处理失败" in result.attempts[0].error
        assert "定位聊天服务失败" in result.attempts[0].error


class TestGetAvailablePlatforms:
    def test_returns_factory_platforms(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service())
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as factory:
            factory.get_available_platforms.return_value = [ChatPlatform.FEISHU]
            assert svc._get_available_platforms() == [ChatPlatform.FEISHU]

    def test_factory_failure_falls_back_to_feishu(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service())
        with patch("apps.automation.services.chat.factory.ChatProviderFactory") as factory:
            factory.get_available_platforms.side_effect = Exception("无法发现平台")
            assert svc._get_available_platforms() == [ChatPlatform.FEISHU]


class TestAsyncSendCaseChatNotification:
    @pytest.mark.asyncio
    async def test_no_case_returns_failure(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service())
        result = await svc.asend_case_chat_notification(_sms(None))
        assert result.any_success is False
        assert "未绑定案件" in result.attempts[0].error

    @pytest.mark.asyncio
    async def test_no_platforms_returns_failure(self) -> None:
        svc = SMSNotificationService(case_chat_service=_chat_service())
        with patch.object(svc, "_get_available_platforms", return_value=[]):
            result = await svc.asend_case_chat_notification(_sms(_case()))
        assert result.any_success is False
        assert "没有可用的群聊平台" in result.attempts[0].error

    @pytest.mark.asyncio
    async def test_platform_success(self) -> None:
        chat = _chat_service(ok=True)
        svc = SMSNotificationService(case_chat_service=chat)
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            result = await svc.asend_case_chat_notification(_sms(_case()), document_paths=["/tmp/x.pdf"])

        assert result.any_success is True
        assert result.attempts[0].file_count == 1

    @pytest.mark.asyncio
    async def test_platform_task_exception_recorded_as_failure(self) -> None:
        """gather(return_exceptions=True) 中抛出的异常被折叠为失败 attempt。"""
        svc = SMSNotificationService(case_chat_service=_chat_service())
        with patch.object(svc, "_get_available_platforms", return_value=[ChatPlatform.FEISHU]):
            with patch.object(svc, "_notify_single_platform", side_effect=RuntimeError("线程炸了")):
                result = await svc.asend_case_chat_notification(_sms(_case()))

        assert result.any_success is False
        assert "线程炸了" in result.attempts[0].error
        assert result.attempts[0].platform == ChatPlatform.FEISHU.value
