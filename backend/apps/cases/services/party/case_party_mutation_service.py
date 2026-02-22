"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.cases.models import CaseParty
from apps.core.business_config import business_config
from apps.core.exceptions import ConflictError, NotFoundError, ValidationException
from apps.core.interfaces import IClientService, IContractService

from .repo import CasePartyCommandRepo

logger = logging.getLogger("apps.cases")


class CasePartyMutationService:
    def __init__(
        self,
        *,
        client_service: IClientService,
        contract_service: IContractService,
        repo: CasePartyCommandRepo | None = None,
    ) -> None:
        self.client_service = client_service
        self.contract_service = contract_service
        self.repo = repo or CasePartyCommandRepo()

    def validate_party_in_contract_scope(self, case_id: int, client_id: int) -> bool:
        case = self.repo.get_case(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )
        if case.contract_id is None:
            return True
        try:
            all_parties = self.contract_service.get_all_parties(case.contract_id)
        except NotFoundError:
            raise ValidationException(
                message=_("关联合同不存在"),
                code="CONTRACT_NOT_FOUND",
                errors={"contract_id": f"案件关联的合同 {case.contract_id} 不存在"},
            ) from None
        valid_client_ids = {party["id"] for party in all_parties}
        if client_id not in valid_client_ids:
            raise ValidationException(
                message=_("当事人必须属于绑定合同的当事人范围"),
                code="PARTY_NOT_IN_CONTRACT_SCOPE",
                errors={"client_id": str(_("当事人必须属于绑定合同的当事人范围"))},
            )
        return True

    def validate_legal_status_compatibility(
        self, *, case_id: int, legal_status: str, exclude_party_id: int | None = None, client_id: int | None = None
    ) -> bool:
        from apps.cases.models import Case

        case = Case.objects.filter(id=case_id).only("id").first()
        if not case:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )
        parties_qs = CaseParty.objects.filter(case_id=case_id).select_related("client")
        if exclude_party_id:
            parties_qs = parties_qs.exclude(id=exclude_party_id)
        is_compatible = business_config.is_legal_status_valid_for_case_type(legal_status, None)
        # 检查与现有诉讼地位的兼容性（简单检查：同一案件不能有完全相同的诉讼地位组合冲突）
        if not is_compatible:
            raise ValidationException(
                message=_("诉讼地位 %(status)s 不适用于当前案件") % {"status": legal_status},
                code="INCOMPATIBLE_LEGAL_STATUS",
                errors={
                    "legal_status": str(_("诉讼地位与现有当事人不兼容")),
                    "attempted_status": legal_status,
                },
            )
        if client_id:
            self._validate_our_party_legal_status(
                case_id=case_id, legal_status=legal_status, client_id=client_id, parties_qs=parties_qs
            )
        return True

    def _validate_our_party_legal_status(
        self, *, case_id: int, legal_status: str, client_id: int, parties_qs: QuerySet[Any, Any]
    ) -> None:
        client_dto = self.client_service.get_client_internal(client_id)
        if not client_dto or not client_dto.is_our_client:
            return
        new_status_config = business_config.is_legal_status_valid_for_case_type(legal_status, None)
        if not new_status_config:
            return
        # 获取新诉讼地位的标签用于日志
        new_group = legal_status
        opposing_groups = {
            "plaintiff_side": "defendant_side",
            "defendant_side": "plaintiff_side",
            "appellant_side": "appellee_side",
            "appellee_side": "appellant_side",
            "applicant_side": "respondent_side",
            "respondent_side": "applicant_side",
            "criminal_defendant_side": "criminal_victim_side",
            "criminal_victim_side": "criminal_defendant_side",
        }
        opposing_group = opposing_groups.get(new_group)
        if not opposing_group:
            return
        our_party_statuses = list(
            parties_qs.filter(client__is_our_client=True)
            .exclude(legal_status__isnull=True)
            .exclude(legal_status="")
            .values_list("legal_status", "client__name")
        )
        for existing_status, client_name in our_party_statuses:
            existing_in_opposing = (
                existing_status in opposing_groups
                and opposing_groups.get(existing_status) == new_group
            )
            if existing_in_opposing:
                new_status_label = business_config.get_legal_status_label(legal_status)
                existing_status_label = business_config.get_legal_status_label(existing_status)
                conflict_msg = _(
                    "我方当事人诉讼地位冲突:案件中已有我方当事人「%(name)s」"
                    "为%(existing)s,不能再添加我方当事人为%(new)s"
                ) % {"name": client_name, "existing": existing_status_label, "new": new_status_label}
                raise ValidationException(
                    message=conflict_msg,
                    code="OUR_PARTY_LEGAL_STATUS_CONFLICT",
                    errors={
                        "legal_status": str(_("我方当事人不能同时处于对立诉讼地位")),
                        "conflicting_party": client_name,
                        "conflicting_status": existing_status,
                    },
                )

    @transaction.atomic
    def create_party(
        self, *, case_id: int, client_id: int, legal_status: str | None = None, user: Any | None = None
    ) -> CaseParty:
        case = self.repo.get_case(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )
        if not self.client_service.validate_client_exists(client_id):
            raise NotFoundError(
                message=_("客户不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的客户不存在"},
            )
        if self.repo.party_exists(case_id=case_id, client_id=client_id):
            raise ConflictError(
                message=_("当事人已存在"),
                code="PARTY_ALREADY_EXISTS",
                errors={"party": f"案件 {case_id} 中已存在客户 {client_id} 的当事人记录"},
            )
        self.validate_party_in_contract_scope(case_id, client_id)
        if legal_status:
            self.validate_legal_status_compatibility(case_id=case_id, legal_status=legal_status, client_id=client_id)
        party = self.repo.create_party(case=case, client_id=client_id, legal_status=legal_status)
        logger.info(
            "创建当事人成功",
            extra={
                "action": "create_party",
                "party_id": party.id,
                "case_id": case_id,
                "client_id": client_id,
                "legal_status": legal_status,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        return party

    @transaction.atomic
    def update_party(self, *, party_id: int, data: dict[str, Any], user: Any | None = None) -> CaseParty:
        party = self.repo.get_party_for_update(party_id)
        if not party:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="PARTY_NOT_FOUND",
                errors={"party_id": f"ID 为 {party_id} 的当事人不存在"},
            )
        self._validate_update_references(data, party)
        new_case_id = data.get("case_id", party.case_id)
        new_client_id = data.get("client_id", party.client_id)
        self._validate_update_uniqueness(party_id, party, new_case_id, new_client_id)
        new_legal_status = data.get("legal_status")
        if new_legal_status and new_legal_status != party.legal_status:
            self.validate_legal_status_compatibility(
                case_id=new_case_id, legal_status=new_legal_status, exclude_party_id=party_id, client_id=new_client_id
            )
        if new_case_id != party.case_id or new_client_id != party.client_id:
            self.validate_party_in_contract_scope(new_case_id, new_client_id)
        for key, value in data.items():
            if hasattr(party, key):
                setattr(party, key, value)
        party.save()
        logger.info(
            "更新当事人成功",
            extra={
                "action": "update_party",
                "party_id": party_id,
                "case_id": party.case_id,
                "client_id": party.client_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        return party

    def _validate_update_references(self, data: dict[str, Any], party: CaseParty) -> None:
        """验证更新数据中引用的案件和客户是否存在"""
        case_id = data.get("case_id")
        if case_id and case_id != party.case_id and (not self.repo.get_case(case_id)):
            raise NotFoundError(
                message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )
        client_id = data.get("client_id")
        if client_id and client_id != party.client_id and (not self.client_service.validate_client_exists(client_id)):
            raise NotFoundError(
                message=_("客户不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的客户不存在"},
            )

    def _validate_update_uniqueness(
        self, party_id: int, party: CaseParty, new_case_id: Any, new_client_id: Any
    ) -> None:
        """验证更新后不会产生重复当事人"""
        if new_case_id == party.case_id and new_client_id == party.client_id:
            return
        if CaseParty.objects.filter(case_id=new_case_id, client_id=new_client_id).exclude(id=party_id).exists():
            raise ConflictError(
                message=_("当事人已存在"),
                code="PARTY_ALREADY_EXISTS",
                errors={"party": f"案件 {new_case_id} 中已存在客户 {new_client_id} 的当事人记录"},
            )

    @transaction.atomic
    def delete_party(self, *, party_id: int, user: Any | None = None) -> dict[str, bool]:
        party = CaseParty.objects.filter(id=party_id).only("id", "case_id", "client_id").first()
        if not party:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="PARTY_NOT_FOUND",
                errors={"party_id": f"ID 为 {party_id} 的当事人不存在"},
            )
        case_id = party.case_id
        client_id = party.client_id
        party.delete()
        logger.info(
            "删除当事人成功",
            extra={
                "action": "delete_party",
                "party_id": party_id,
                "case_id": case_id,
                "client_id": client_id,
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
        return {"success": True}

    @transaction.atomic
    def create_party_internal(self, *, case_id: int, client_id: int, legal_status: str | None = None) -> bool:
        case = self.repo.get_case(case_id)
        if not case:
            return False
        if self.repo.party_exists(case_id=case_id, client_id=client_id):
            return True
        self.repo.create_party(case=case, client_id=client_id, legal_status=legal_status)
        return True
