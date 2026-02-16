"""Business workflow orchestration."""

from typing import Any, Protocol

from apps.automation.models import CourtSMS, CourtSMSStatus

from .court_sms_repository import CourtSMSRepository


class CourtSMSStageProcessor(Protocol):
    def _process_parsing(self, sms: CourtSMS) -> CourtSMS: ...
    def _process_downloading_or_matching(self, sms: CourtSMS) -> CourtSMS: ...
    def _process_matching(self, sms: CourtSMS) -> CourtSMS: ...
    def _process_renaming(self, sms: CourtSMS) -> CourtSMS: ...
    def _process_notifying(self, sms: CourtSMS) -> CourtSMS: ...


class CourtSMSProcessingWorkflow:
    def __init__(self, *, repo: CourtSMSRepository, processor: CourtSMSStageProcessor) -> None:
        self.repo = repo
        self.processor = processor

    def process_sms(self, *, sms_id: int) -> Any:
        sms = self.repo.get_by_id(sms_id=sms_id)

        if sms.status == CourtSMSStatus.PENDING:
            sms = self.processor._process_parsing(sms)

        if sms.status == CourtSMSStatus.PARSING:
            sms = self.processor._process_downloading_or_matching(sms)

        if sms.status == CourtSMSStatus.DOWNLOADING:
            return sms

        if sms.status == CourtSMSStatus.MATCHING:
            sms = self.processor._process_matching(sms)

        if sms.status == CourtSMSStatus.RENAMING:
            sms = self.processor._process_renaming(sms)

        if sms.status == CourtSMSStatus.NOTIFYING:
            sms = self.processor._process_notifying(sms)

        return sms

    def process_from_matching(self, *, sms_id: int) -> Any:
        sms = self.repo.get_by_id(sms_id=sms_id)

        if sms.status == CourtSMSStatus.MATCHING:
            sms = self.processor._process_matching(sms)

        if sms.status == CourtSMSStatus.RENAMING:
            sms = self.processor._process_renaming(sms)

        if sms.status == CourtSMSStatus.NOTIFYING:
            sms = self.processor._process_notifying(sms)

        return sms

    def process_from_renaming(self, *, sms_id: int) -> Any:
        sms = self.repo.get_by_id(sms_id=sms_id)

        if sms.status == CourtSMSStatus.RENAMING:
            sms = self.processor._process_renaming(sms)

        if sms.status == CourtSMSStatus.NOTIFYING:
            sms = self.processor._process_notifying(sms)

        return sms
