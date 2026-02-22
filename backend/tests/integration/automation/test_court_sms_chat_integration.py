"""
法院短信群聊集成测试

测试短信通知服务与案件群聊服务的集成功能。
"""

from unittest.mock import Mock

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus, CourtSMSType
from apps.automation.services.sms.sms_notification_service import SMSNotificationService
from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage
from apps.cases.models import Case
from apps.core.enums import ChatPlatform


class CourtSMSChatIntegrationTest(TestCase):
    """法院短信群聊集成测试"""

    def setUp(self):
        """设置测试数据"""
        # 创建测试案件
        self.case = Case.objects.create(name="张三诉李四合同纠纷案", current_stage="FIRST_TRIAL")

        # 创建测试短信
        self.sms = CourtSMS.objects.create(
            content="您有新的法院文书，请及时查看。案件：张三诉李四合同纠纷案",
            received_at=timezone.now(),
            status=CourtSMSStatus.NOTIFYING,
            sms_type=CourtSMSType.DOCUMENT_DELIVERY,
            case=self.case,
        )

        self.case_chat_service = Mock()
        self.fee_check_service = Mock()
        self.chat_message_sender = Mock()
        self.notification_service = SMSNotificationService(  # type: ignore[call-arg]
            case_chat_service=self.case_chat_service,
            fee_check_service=self.fee_check_service,
            chat_message_sender=self.chat_message_sender,
        )
        self.document_attachment_service = Mock()
        self.stage = SMSNotifyingStage(
            notification_service=self.notification_service,
            document_attachment_service=self.document_attachment_service,
        )

    def test_send_case_chat_notification_success(self):
        mock_chat = Mock()
        mock_chat.chat_id = "oc_test123"
        self.case_chat_service.get_or_create_chat.return_value = mock_chat

        mock_result = Mock()
        mock_result.success = True
        mock_result.message = "发送成功"
        self.case_chat_service.send_document_notification.return_value = mock_result

        ok = self.notification_service.send_case_chat_notification(self.sms, ["/path/to/document.pdf"])
        assert ok is True

        self.case_chat_service.get_or_create_chat.assert_called_once_with(
            case_id=self.case.id,
            platform=ChatPlatform.FEISHU,
        )
        self.case_chat_service.send_document_notification.assert_called_once_with(
            case_id=self.case.id,
            sms_content=self.sms.content,
            document_paths=["/path/to/document.pdf"],
            platform=ChatPlatform.FEISHU,
            title="📋 法院文书通知",
        )

    def test_send_case_chat_notification_create_chat_failure(self):
        self.case_chat_service.get_or_create_chat.side_effect = Exception("群聊创建失败")
        ok = self.notification_service.send_case_chat_notification(self.sms)
        assert ok is False
        self.case_chat_service.send_document_notification.assert_not_called()

    def test_send_case_chat_notification_send_failure(self):
        mock_chat = Mock()
        mock_chat.chat_id = "oc_test123"
        self.case_chat_service.get_or_create_chat.return_value = mock_chat

        mock_result = Mock()
        mock_result.success = False
        mock_result.message = "发送失败"
        self.case_chat_service.send_document_notification.return_value = mock_result

        ok = self.notification_service.send_case_chat_notification(self.sms)
        assert ok is False
        self.case_chat_service.get_or_create_chat.assert_called_once()
        self.case_chat_service.send_document_notification.assert_called_once()

    def test_send_case_chat_notification_no_case(self):
        """测试短信未绑定案件的处理"""
        # 创建未绑定案件的短信
        sms_no_case = CourtSMS.objects.create(
            content="测试短信", received_at=timezone.now(), status=CourtSMSStatus.NOTIFYING, case=None
        )

        ok = self.notification_service.send_case_chat_notification(sms_no_case)
        assert ok is False

    def test_process_notifying_integration(self):
        self.document_attachment_service.get_paths_for_notification.return_value = [
            "/path/to/document1.pdf",
            "/path/to/document2.pdf",
        ]
        self.notification_service.send_case_chat_notification = Mock(return_value=True) # type: ignore[method-assign]

        with self.captureOnCommitCallbacks(execute=True):
            result_sms = self.stage.process(self.sms)

        result_sms.refresh_from_db()
        self.assertEqual(result_sms.status, CourtSMSStatus.COMPLETED)
        self.assertIsNotNone(result_sms.feishu_sent_at)

        self.notification_service.send_case_chat_notification.assert_called_once()
