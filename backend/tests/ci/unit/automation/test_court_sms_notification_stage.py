from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.automation.models import CourtSMSStatus
from apps.automation.services.sms.court_sms_service import CourtSMSService
from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage
from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult


@dataclass
class FakeSMS:
    id: int = 1
    status: str = CourtSMSStatus.NOTIFYING
    case: object | None = object()
    error_message: str | None = None
    notification_results: dict[str, Any] = field(default_factory=dict)
    save_count: int = 0

    def save(self) -> None:
        self.save_count += 1


class FakeDocumentAttachment:
    def get_paths_for_notification(self, sms: FakeSMS) -> list[str]:
        return ["/tmp/court-document.pdf"]


@dataclass
class FakeNotification:
    result: MultiPlatformNotificationResult | None = None
    error: Exception | None = None

    def send_case_chat_notification(
        self, sms: FakeSMS, document_paths: list[str]
    ) -> MultiPlatformNotificationResult:
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("FakeNotification.result is required")
        return self.result


def failed_notification_result() -> MultiPlatformNotificationResult:
    return MultiPlatformNotificationResult(
        attempts=[
            PlatformNotificationResult(
                platform="feishu",
                success=False,
                error="not configured",
            )
        ]
    )


def test_notification_failure_keeps_archived_sms_completed() -> None:
    sms = FakeSMS()
    result = failed_notification_result()

    SMSNotifyingStage()._update_notification_status(sms, result)

    assert sms.status == CourtSMSStatus.COMPLETED
    assert sms.notification_results["feishu"]["success"] is False
    assert sms.error_message is not None
    assert "不影响文书归档" in sms.error_message


def test_notification_exception_keeps_archived_sms_completed() -> None:
    sms = FakeSMS()

    SMSNotifyingStage()._handle_notification_error(sms, RuntimeError("boom"))

    assert sms.status == CourtSMSStatus.COMPLETED
    assert sms.notification_results["_exception"] == {"success": False, "error": "boom"}
    assert sms.error_message is not None
    assert "不影响文书归档" in sms.error_message
    assert sms.save_count == 1


def test_process_notifying_with_case_and_failed_notification_completes() -> None:
    sms = FakeSMS(case=object())
    service = CourtSMSService(
        document_attachment=FakeDocumentAttachment(),
        notification=FakeNotification(result=failed_notification_result()),
    )

    result = service._process_notifying(sms)

    assert result is sms
    assert sms.status == CourtSMSStatus.COMPLETED
    assert sms.notification_results["feishu"]["success"] is False
    assert sms.error_message is not None
    assert "不影响文书归档" in sms.error_message


def test_process_notifying_without_case_and_failed_notification_fails() -> None:
    sms = FakeSMS(case=None)
    service = CourtSMSService(
        document_attachment=FakeDocumentAttachment(),
        notification=FakeNotification(result=failed_notification_result()),
    )

    result = service._process_notifying(sms)

    assert result is sms
    assert sms.status == CourtSMSStatus.FAILED
    assert sms.notification_results["none"]["success"] is False
    assert sms.error_message == "案件群聊通知发送失败"


def test_process_notifying_with_case_and_notification_exception_completes() -> None:
    sms = FakeSMS(case=object())
    service = CourtSMSService(
        document_attachment=FakeDocumentAttachment(),
        notification=FakeNotification(error=RuntimeError("boom")),
    )

    result = service._process_notifying(sms)

    assert result is sms
    assert sms.status == CourtSMSStatus.COMPLETED
    assert sms.notification_results["_exception"] == {"success": False, "error": "boom"}
    assert sms.error_message is not None
    assert "不影响文书归档" in sms.error_message


def test_process_notifying_without_case_and_notification_exception_fails() -> None:
    sms = FakeSMS(case=None)

    class RaisingDocumentAttachment:
        def get_paths_for_notification(self, sms: FakeSMS) -> list[str]:
            raise RuntimeError("boom")

    service = CourtSMSService(
        document_attachment=RaisingDocumentAttachment(),
        notification=FakeNotification(result=failed_notification_result()),
    )

    result = service._process_notifying(sms)

    assert result is sms
    assert sms.status == CourtSMSStatus.FAILED
    assert sms.notification_results["_exception"] == {"success": False, "error": "boom"}
    assert sms.error_message == "案件群聊通知发送失败: boom"
