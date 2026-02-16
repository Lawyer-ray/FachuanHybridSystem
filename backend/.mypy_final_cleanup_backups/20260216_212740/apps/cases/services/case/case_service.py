"""Business logic services."""
from __future__ import annotations

"""
案件服务层
处理案件相关的业务逻辑
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast, Set

from apps.cases.models import Case
from apps.core.business_config import business_config
from apps.core.exceptions import ValidationException
from apps.core.interfaces import IContractService
from django.db import transaction
from django.db.models import QuerySet

from .case_access_policy import CaseAccessPolicy
from .case_details_query_service import CaseDetailsQueryService
from .case_full_create_service import CaseFullCreateService
from .case_internal_query_service import CaseInternalQueryService
from .case_log_internal_service import CaseLogInternalService
from .case_mutation_service import CaseMutationService
from .case_number_internal_service import CaseNumberInternalService
from .case_party_query_service import CasePartyQueryService
from .case_query_facade import CaseQueryFacade
from .case_template_binding_query_service import CaseTemplateBindingQueryService

logger = logging.getLogger("apps.cases")

if TYPE_CHECKING:
    from .case_mutation_facade import CaseMutationFacade


@dataclass
class CaseCreateData:
    name: str
    contract_id: int | None = None
    is_archived: bool = False
    hearing_institution: str | None = None
    target_amount: float | None = None
    cause_of_action: str | None = None
    current_stage: str | None = None
    effective_date: str | None = None


@dataclass
class CaseFullCreateData:
    case: CaseCreateData
    parties: list[dict[str, Any]] | None = None
    assignments: list[dict[str, Any]] | None = None
    logs: list[dict[str, Any]] | None = None


class CaseService:
    def __init__(self, contract_service: IContractService) -> None:
        self.contract_service = contract_service
        self._full_create_service: CaseFullCreateService | None = None
        self._log_internal_service: CaseLogInternalService | None = None
        self._details_query_service: CaseDetailsQueryService | None = None
        self._mutation_service: CaseMutationService | None = None
        self._mutation_facade: CaseMutationFacade | None = None
        self._number_internal_service: CaseNumberInternalService | None = None
        self._party_query_service: CasePartyQueryService | None = None
        self._template_binding_query_service: CaseTemplateBindingQueryService | None = None
        self._internal_query_service: CaseInternalQueryService | None = None
        self._access_policy: CaseAccessPolicy | None = None
        self._query_facade: CaseQueryFacade | None = None

    @property
    def full_create_service(self) -> CaseFullCreateService:
        if self._full_create_service is None:
            self._full_create_service = CaseFullCreateService(self)
        return self._full_create_service

    @property
    def log_internal_service(self) -> CaseLogInternalService:
        if self._log_internal_service is None:
            self._log_internal_service = CaseLogInternalService()
        return self._log_internal_service

    @property
    def details_query_service(self) -> CaseDetailsQueryService:
        if self._details_query_service is None:
            self._details_query_service = CaseDetailsQueryService()
        return self._details_query_service

    @property
    def number_internal_service(self) -> CaseNumberInternalService:
        if self._number_internal_service is None:
            self._number_internal_service = CaseNumberInternalService()
        return self._number_internal_service

    @property
    def party_query_service(self) -> CasePartyQueryService:
        if self._party_query_service is None:
            self._party_query_service = CasePartyQueryService()
        return self._party_query_service

    @property
    def template_binding_query_service(self) -> CaseTemplateBindingQueryService:
        if self._template_binding_query_service is None:
            self._template_binding_query_service = CaseTemplateBindingQueryService()
        return self._template_binding_query_service

    @property
    def internal_query_service(self) -> CaseInternalQueryService:
        if self._internal_query_service is None:
            self._internal_query_service = CaseInternalQueryService()
        return self._internal_query_service

    def check_case_access(self, case: Case, user: Any, org_access: dict[str, Any] | None) -> bool:
        return bool(self.access_policy.has_access(case_id=case.id, user=user, org_access=org_access, case=case))

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    @property
    def mutation_service(self) -> CaseMutationService:
        if self._mutation_service is None:
            self._mutation_service = CaseMutationService(self)
        return self._mutation_service

    @property
    def query_facade(self) -> CaseQueryFacade:
        if self._query_facade is None:
            self._query_facade = CaseQueryFacade(access_policy=self.access_policy)
        return self._query_facade

    @property
    def mutation_facade(self) -> "CaseMutationFacade":
        if self._mutation_facade is None:
            from .case_mutation_facade import CaseMutationFacade

            self._mutation_facade = CaseMutationFacade(
                mutation_service=self.mutation_service,
                full_create_service=self.full_create_service,
            )
        return self._mutation_facade

    def get_case_queryset(self) -> QuerySet[Case, Case]:
        return cast(QuerySet[Case, Case], self.query_facade.get_case_queryset())

    def get_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> Case:
        return self.query_facade.get_case(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def list_cases(
        self,
        case_type: str | None = None,
        status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        queryset: QuerySet[Case, Case]= self.query_facade.list_cases(
            case_type=case_type,
            status=status,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return queryset

    def search_by_case_number(
        self,
        case_number: str,
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
        exact_match: bool = False,
    ) -> QuerySet[Case, Case]:
        queryset: QuerySet[Case, Case]= self.query_facade.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            exact_match=exact_match,
        )
        return queryset

    def create_case(
        self,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> Case:
        return self.mutation_service.create_case(
            data=data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def update_case(
        self,
        case_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> Case:
        return self.mutation_service.update_case(
            case_id=case_id,
            data=data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    @transaction.atomic
    def delete_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any]| None = None,
        perm_open_access: bool = False,
    ) -> bool:
        return bool(
            self.mutation_service.delete_case(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )
        )

    def _validate_stage(
        self,
        stage: str,
        case_type: str | None,
        representation_stages: list[str] | None = None,
    ) -> str:
        if case_type and not business_config.is_stage_valid_for_case_type(stage, case_type):
            raise ValidationException("该案件类型不支持此阶段", errors={"current_stage": "阶段不适用于此案件类型"})
        if representation_stages and stage not in representation_stages:
            raise ValidationException("当前阶段必须属于代理阶段集合", errors={"current_stage": "阶段不在代理范围内"})
        return stage

    @transaction.atomic
    def create_case_full(
        self,
        data: dict[str, Any],
        actor_id: int | None = None,
        user: Any | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = self.full_create_service.create_case_full(data=data, actor_id=actor_id, user=user)
        return result
