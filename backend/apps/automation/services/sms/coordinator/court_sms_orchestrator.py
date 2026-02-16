"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from apps.automation.models import CourtSMSStatus
from apps.automation.services.sms.court_sms_repository import CourtSMSRepository
from apps.automation.services.sms.sms_processing_workflow import CourtSMSProcessingWorkflow
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.automation")


class CourtSMSOrchestrator:
    def __init__(self, *, workflow: CourtSMSProcessingWorkflow, repo: CourtSMSRepository) -> None:
        self.workflow = workflow
        self.repo = repo

    def process_sms(self, sms_id: int) -> Any:
        try:
            return self.workflow.process_sms(sms_id=sms_id)
        except Exception as e:
            logger.error(f"处理短信失败: ID={sms_id}, 错误: {e!s}")
            sms = self.repo.get_by_id(sms_id=sms_id)
            self.repo.set_status(sms=sms, status=CourtSMSStatus.FAILED, error_message=str(e))
            raise ValidationException(message=f"处理短信失败: {e!s}", code="SMS_PROCESSING_FAILED", errors={}) from e

    def process_from_matching(self, sms_id: int) -> Any:
        return self.workflow.process_from_matching(sms_id=sms_id)

    def process_from_renaming(self, sms_id: int) -> Any:
        return self.workflow.process_from_renaming(sms_id=sms_id)
