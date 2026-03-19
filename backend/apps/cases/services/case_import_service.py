"""案件 JSON 导入服务（级联创建 Contract、Client、Lawyer）。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.cases.models import Case
    from apps.client.models import Client
    from apps.contracts.models import Contract
    from apps.organization.models import Lawyer

ImportData = dict[str, object]


class CasePartyImportPayload(TypedDict):
    legal_status: NotRequired[str | None]
    client: NotRequired[ImportData]


class CaseAssignmentImportPayload(TypedDict):
    lawyer: NotRequired[ImportData]


class SupervisingAuthorityImportPayload(TypedDict):
    name: NotRequired[str]
    authority_type: NotRequired[str]


class CaseNumberImportPayload(TypedDict):
    number: NotRequired[str]
    is_active: NotRequired[bool]
    remarks: NotRequired[str | None]


class CaseChatImportPayload(TypedDict):
    platform: NotRequired[str]
    chat_id: NotRequired[str]
    name: NotRequired[str]
    is_active: NotRequired[bool]
    owner_id: NotRequired[int | None]


class CaseLogAttachmentImportPayload(TypedDict):
    file_path: NotRequired[str]
    filename: NotRequired[str]


class CaseLogReminderImportPayload(TypedDict):
    reminder_type: NotRequired[str]
    content: NotRequired[str]
    due_at: NotRequired[str | datetime | None]
    metadata: NotRequired[dict[str, object]]


class CaseLogImportPayload(TypedDict):
    content: NotRequired[str]
    actor: NotRequired[ImportData]
    attachments: NotRequired[list[CaseLogAttachmentImportPayload]]
    reminders: NotRequired[list[CaseLogReminderImportPayload]]


class CaseImportPayload(TypedDict):
    name: NotRequired[str]
    status: NotRequired[str]
    effective_date: NotRequired[object]
    specified_date: NotRequired[object]
    cause_of_action: NotRequired[str | None]
    target_amount: NotRequired[object]
    preservation_amount: NotRequired[object]
    case_type: NotRequired[str | None]
    current_stage: NotRequired[str | None]
    is_archived: NotRequired[bool]
    filing_number: NotRequired[str | None]
    contract: NotRequired[ImportData]
    parties: NotRequired[list[CasePartyImportPayload]]
    assignments: NotRequired[list[CaseAssignmentImportPayload]]
    supervising_authorities: NotRequired[list[SupervisingAuthorityImportPayload]]
    case_numbers: NotRequired[list[CaseNumberImportPayload]]
    chats: NotRequired[list[CaseChatImportPayload]]
    logs: NotRequired[list[CaseLogImportPayload]]


class ClientResolverProtocol(Protocol):
    def resolve_with_attachments(self, data: ImportData) -> Client: ...


class ContractImportProtocol(Protocol):
    def resolve(self, data: ImportData) -> Contract: ...


class LawyerResolverProtocol(Protocol):
    def resolve(self, data: ImportData) -> Lawyer | None: ...


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


def _parse_log_reminders_for_create(
    reminder_data_list: list[CaseLogReminderImportPayload],
) -> list[dict[str, object]]:
    reminders: list[dict[str, object]] = []
    for reminder_data in reminder_data_list:
        reminder_type = reminder_data.get("reminder_type")
        due_at = reminder_data.get("due_at")
        if not reminder_type or due_at is None:
            continue
        parsed_due_at = parse_datetime(due_at) if isinstance(due_at, str) else due_at
        if not isinstance(parsed_due_at, datetime):
            continue
        metadata = reminder_data.get("metadata")
        reminders.append(
            {
                "reminder_type": reminder_type,
                "content": reminder_data.get("content", ""),
                "due_at": parsed_due_at,
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return reminders


class CaseImportService:
    """按 filing_number get_or_create Case，级联创建 Contract、Client、Lawyer。"""

    def __init__(
        self,
        contract_import: ContractImportProtocol | None,
        client_resolve: ClientResolverProtocol,
        lawyer_resolve: LawyerResolverProtocol,
    ) -> None:
        self._contract_import = contract_import
        self._client_resolve = client_resolve
        self._lawyer_resolve = lawyer_resolve

    def bind_contract_import(self, contract_import: ContractImportProtocol | None) -> None:
        """绑定合同导入服务（用于导入链路中的循环依赖组装）。"""
        self._contract_import = contract_import

    @transaction.atomic
    def import_one(self, data: CaseImportPayload, contract: Contract | None = None) -> Case:
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
            if isinstance(contract_data, dict) and self._contract_import is not None:
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
            if not isinstance(client_data, dict):
                continue
            client = self._client_resolve.resolve_with_attachments(client_data)
            legal_status = party_data.get("legal_status")
            CaseParty.objects.get_or_create(case=case, client=client, defaults={"legal_status": legal_status})

        for assign_data in data.get("assignments") or []:
            lawyer_data = assign_data.get("lawyer")
            if not isinstance(lawyer_data, dict):
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
            chat_id = ch_data.get("chat_id")
            if isinstance(chat_id, str) and chat_id:
                CaseChat.objects.get_or_create(
                    case=case,
                    platform=ch_data.get("platform", "feishu"),
                    chat_id=chat_id,
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
            if not isinstance(actor_data, dict):
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
                if isinstance(file_path, str) and file_path:
                    from django.conf import settings
                    from django.core.files.base import ContentFile

                    full = Path(settings.MEDIA_ROOT) / file_path
                    if full.exists():
                        filename = att_data.get("filename")
                        save_name = filename if isinstance(filename, str) and filename else full.name
                        with full.open("rb") as f:
                            att = CaseLogAttachment(log=log)
                            att.file.save(save_name, ContentFile(f.read()), save=True)
            # 批量创建案件日志提醒
            reminders_list = _parse_log_reminders_for_create(log_data.get("reminders") or [])
            if reminders_list:
                from apps.cases.services.case.wiring import get_reminder_service

                reminder_service = get_reminder_service()
                reminder_service.create_case_log_reminders_internal(
                    case_log_id=log.id,
                    reminders=reminders_list,
                )

        return case


def build_case_import_service_for_admin() -> CaseImportService:
    """构建 admin 导入使用的 CaseImportService（包含循环依赖绑定）。"""
    from apps.core.dependencies.business_import import build_case_and_contract_import_services_for_admin

    case_svc, _ = build_case_and_contract_import_services_for_admin()
    return case_svc
