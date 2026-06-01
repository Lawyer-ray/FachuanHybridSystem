from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.automation.models import CourtSMSStatus
from apps.automation.services.sms.stages.sms_notifying_stage import SMSNotifyingStage
from apps.core.dto.chat import MultiPlatformNotificationResult, PlatformNotificationResult


@dataclass
class FakeSMS:
    id: int = 1
    status: str = CourtSMSStatus.NOTIFYING
    error_message: str | None = None
    notification_results: dict[str, Any] = field(default_factory=dict)
    save_count: int = 0

    def save(self) -> None:
        self.save_count += 1


def test_notification_failure_keeps_archived_sms_completed() -> None:
    sms = FakeSMS()
    result = MultiPlatformNotificationResult(
        attempts=[
            PlatformNotificationResult(
                platform="feishu",
                success=False,
                error="not configured",
            )
        ]
    )

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
