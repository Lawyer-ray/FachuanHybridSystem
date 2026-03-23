"""案件律师占位符服务

提取案件绑定的律师信息：姓名、执业证号、电话、律所地址。
"""

import logging
from typing import Any, ClassVar

from django.db.models import QuerySet

from apps.cases.models import CaseAssignment
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class CaseLawyerService(BasePlaceholderService):
    """案件律师占位符服务"""

    name: str = "case_lawyer_service"
    display_name: str = "诉讼文书-案件律师信息"
    description: str = "生成案件绑定的律师信息：姓名、执业证号、电话、律所地址"
    category: str = "litigation"
    placeholder_keys: ClassVar = [
        LitigationPlaceholderKeys.CASE_LAWYER_NAME,
        LitigationPlaceholderKeys.CASE_LAWYER_ID,
        LitigationPlaceholderKeys.CASE_LAWYER_PHONE,
        LitigationPlaceholderKeys.CASE_LAWYER_ADDRESS,
    ]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {
                LitigationPlaceholderKeys.CASE_LAWYER_NAME: "",
                LitigationPlaceholderKeys.CASE_LAWYER_ID: "",
                LitigationPlaceholderKeys.CASE_LAWYER_PHONE: "",
                LitigationPlaceholderKeys.CASE_LAWYER_ADDRESS: "",
            }

        assignments: QuerySet[CaseAssignment] = CaseAssignment.objects.filter(
            case_id=case_id
        ).select_related("lawyer__law_firm")

        if not assignments.exists():
            logger.warning("未找到案件律师: case_id=%s", case_id)
            return {
                LitigationPlaceholderKeys.CASE_LAWYER_NAME: "",
                LitigationPlaceholderKeys.CASE_LAWYER_ID: "",
                LitigationPlaceholderKeys.CASE_LAWYER_PHONE: "",
                LitigationPlaceholderKeys.CASE_LAWYER_ADDRESS: "",
            }

        names: list[str] = []
        ids: list[str] = []
        phones: list[str] = []
        seen_addresses: set[str] = set()
        addresses: list[str] = []

        for assignment in assignments:
            lawyer = assignment.lawyer
            if not lawyer:
                continue

            name = (lawyer.real_name or lawyer.username or "").strip()
            if name and name not in names:
                names.append(name)

            license_no = (lawyer.license_no or "").strip()
            if license_no and license_no not in ids:
                ids.append(license_no)

            phone = (lawyer.phone or "").strip()
            if phone and phone not in phones:
                phones.append(phone)

            address = ""
            if lawyer.law_firm:
                address = (lawyer.law_firm.address or "").strip()
            if address and address not in seen_addresses:
                seen_addresses.add(address)
                addresses.append(address)

        return {
            LitigationPlaceholderKeys.CASE_LAWYER_NAME: "、".join(names),
            LitigationPlaceholderKeys.CASE_LAWYER_ID: "、".join(ids),
            LitigationPlaceholderKeys.CASE_LAWYER_PHONE: "、".join(phones),
            LitigationPlaceholderKeys.CASE_LAWYER_ADDRESS: "、".join(addresses),
        }
