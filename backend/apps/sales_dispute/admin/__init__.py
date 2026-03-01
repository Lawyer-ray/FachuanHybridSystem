from __future__ import annotations

from apps.sales_dispute.admin.case_assessment_admin import CaseAssessmentAdmin
from apps.sales_dispute.admin.collection_record_admin import CollectionRecordAdmin
from apps.sales_dispute.admin.lpr_rate_admin import LPRRateAdmin
from apps.sales_dispute.admin.payment_record_admin import PaymentRecordAdmin

__all__: list[str] = [
    "CaseAssessmentAdmin",
    "CollectionRecordAdmin",
    "LPRRateAdmin",
    "PaymentRecordAdmin",
]
