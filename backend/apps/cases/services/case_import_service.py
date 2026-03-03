"""案件 JSON 导入服务（级联创建 Contract、Client、Lawyer）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.cases.models import Case
    from apps.client.services.client_resolve_service import ClientResolveService
    from apps.contracts.services.contract_import_service import ContractImportService
    from apps.organization.services.lawyer_resolve_service import LawyerResolveService

logger = logging.getLogger("apps.cases")

_CASE_FIELDS: tuple[str, ...] = (
    "name",
    "status",
    "effective_date",
    "specified_date",
    "cause_of_action",
    "target_amount",
    "preservation_amount",
    "case_type",
    "current_stage",
    "is_archived",
    "filing_number",
)


class CaseImportService:
    """按 filing_number get_or_create Case，级联创建 Contract、Client、Lawyer。"""

    def __init__(
        self,
        contract_import: ContractImportService | None,
        client_resolve: ClientResolveService,
        lawyer_resolve: LawyerResolveService,
    ) -> None:
        self._contract_import = contract_import
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve

    @transaction.atomic
    def import_one(self, data: dict[str, Any], contract: Any = None) -> Case:
        from apps.cases.models import Case, CaseAssignment, CaseParty

        if not data.get("name"):
            raise ValidationException(message=_("案件名称不能为空"), code="INVALID_CASE_DATA")

        filing_number: str | None = data.get("filing_number") or None
        if filing_number:
            existing = Case.objects.filter(filing_number=filing_number).first()
            if existing:
                logger.info("复用已有案件", extra={"case_id": existing.pk, "filing_number": filing_number})
                return existing

        # 解析关联合同（可选，外部传入时优先）
        if contract is None:
            contract_data = data.get("contract")
            if contract_data and self._contract_import is not None:
                # 去掉 cases 字段，避免合同导入时再还原一遍当前 case（重复创建）
                contract_data = {k: v for k, v in contract_data.items() if k != "cases"}
                contract = self._contract_import.resolve(contract_data)

        case_data = {f: data[f] for f in _CASE_FIELDS if f in data}
        if not case_data.get("filing_number"):
            case_data["filing_number"] = None
        if contract is not None:
            case_data["contract"] = contract
        case = Case.objects.create(**case_data)
        logger.info("创建新案件", extra={"case_id": case.pk, "case_name": case.name})

        for party_data in data.get("parties") or []:
            client_data = party_data.get("client")
            if not client_data:
                continue
            client = self._client_resolve.resolve_with_attachments(client_data)
            legal_status = party_data.get("legal_status")
            CaseParty.objects.get_or_create(case=case, client=client, defaults={"legal_status": legal_status})

        for assign_data in data.get("assignments") or []:
            lawyer_data = assign_data.get("lawyer")
            if not lawyer_data:
                continue
            lawyer = self._lawyer_resolve.resolve(lawyer_data)
            if lawyer is None:
                continue
            CaseAssignment.objects.get_or_create(case=case, lawyer=lawyer)

        from apps.cases.models import CaseNumber
        from apps.cases.models.case import SupervisingAuthority

        for sa_data in data.get("supervising_authorities") or []:
            SupervisingAuthority.objects.get_or_create(
                case=case,
                name=sa_data.get("name"),
                defaults={"authority_type": sa_data.get("authority_type", "TRIAL")},
            )

        for cn_data in data.get("case_numbers") or []:
            if cn_data.get("number"):
                CaseNumber.objects.get_or_create(
                    case=case,
                    number=cn_data["number"],
                    defaults={"is_active": cn_data.get("is_active", False), "remarks": cn_data.get("remarks")},
                )

        from apps.cases.models.chat import CaseChat

        for ch_data in data.get("chats") or []:
            if ch_data.get("chat_id"):
                CaseChat.objects.get_or_create(
                    case=case,
                    platform=ch_data.get("platform", "feishu"),
                    chat_id=ch_data["chat_id"],
                    defaults={
                        "name": ch_data.get("name", ""),
                        "is_active": ch_data.get("is_active", True),
                        "owner_id": ch_data.get("owner_id"),
                    },
                )

        from apps.cases.models.log import CaseLog, CaseLogAttachment

        for log_data in data.get("logs") or []:
            if not log_data.get("content"):
                continue
            actor_data = log_data.get("actor")
            if not actor_data:
                continue
            actor = self._lawyer_resolve.resolve(actor_data)
            if actor is None:
                continue
            log = CaseLog.objects.create(
                case=case,
                content=log_data["content"],
                actor=actor,
            )
            for att_data in log_data.get("attachments") or []:
                file_path = att_data.get("file_path")
                if file_path:
                    from pathlib import Path

                    from django.conf import settings
                    from django.core.files.base import ContentFile

                    full = Path(settings.MEDIA_ROOT) / file_path
                    if full.exists():
                        with full.open("rb") as f:
                            att = CaseLogAttachment(log=log)
                            att.file.save(att_data.get("filename", full.name), ContentFile(f.read()), save=True)
            from apps.reminders.models import Reminder

            for r_data in log_data.get("reminders") or []:
                if r_data.get("due_at") and r_data.get("reminder_type"):
                    Reminder.objects.get_or_create(
                        case_log=log,
                        reminder_type=r_data["reminder_type"],
                        due_at=r_data["due_at"],
                        defaults={"content": r_data.get("content", ""), "metadata": r_data.get("metadata", {})},
                    )

        return case
