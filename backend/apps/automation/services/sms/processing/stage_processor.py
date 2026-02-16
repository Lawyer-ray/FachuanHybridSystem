"""Data processing logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.automation.models import CourtSMS

if TYPE_CHECKING:
    from apps.automation.services.sms.stages import (
        SMSDownloadingStage,
        SMSMatchingStage,
        SMSNotifyingStage,
        SMSParsingStage,
        SMSRenamingStage,
    )


@dataclass(frozen=True)
class CourtSMSStageProcessor:
    parsing_stage: SMSParsingStage
    downloading_stage: SMSDownloadingStage
    matching_stage: SMSMatchingStage
    renaming_stage: SMSRenamingStage
    notifying_stage: SMSNotifyingStage

    def _process_parsing(self, sms: CourtSMS) -> CourtSMS:
        return self.parsing_stage.process(sms)

    def _process_downloading_or_matching(self, sms: CourtSMS) -> CourtSMS:
        return self.downloading_stage.process(sms)

    def _process_matching(self, sms: CourtSMS) -> CourtSMS:
        return self.matching_stage.process(sms)

    def _process_renaming(self, sms: CourtSMS) -> CourtSMS:
        return self.renaming_stage.process(sms)

    def _process_notifying(self, sms: CourtSMS) -> CourtSMS:
        return self.notifying_stage.process(sms)
