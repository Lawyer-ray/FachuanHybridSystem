from typing import cast

"""Data repository layer."""


class CourtSmsRepo:
    def find_completed_sms_id_by_case_number(self, case_number: str) -> int | None:
        from apps.automation.models import CourtSMS, CourtSMSStatus

        sms = CourtSMS.objects.filter(case_numbers__contains=[case_number], status=CourtSMSStatus.COMPLETED).first()
        return cast(int, sms.id) if sms else None
