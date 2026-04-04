"""跨模块适配器 — 其他模块通过此类访问 cases 功能。"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError
from apps.core.interfaces import CaseDTO, IClientService, IContractService

from .case_access_policy import CaseAccessPolicy
from .case_command_service import CaseCommandService
from .case_details_query_service import CaseDetailsQueryService
from .case_internal_query_service import CaseInternalQueryService
from .case_log_internal_service import CaseLogInternalService
from .case_number_internal_service import CaseNumberInternalService
from .case_party_internal_query_service import CasePartyInternalQueryService
from .case_template_binding_query_service import CaseTemplateBindingQueryService


class CaseServiceAdapter:
    def __init__(
        self,
        *,
        contract_service: IContractService | None = None,
        client_service: IClientService | None = None,
    ) -> None:
        if contract_service is None:
            raise RuntimeError("CaseServiceAdapter.contract_service 未注入")
        if client_service is None:
            raise RuntimeError("CaseServiceAdapter.client_service 未注入")

        self._contract_service = contract_service
        self._client_service = client_service

        access_policy = CaseAccessPolicy()
        self._command = CaseCommandService(
            contract_service=contract_service,
            access_policy=access_policy,
        )
        self._internal_query = CaseInternalQueryService()
        self._log_internal = CaseLogInternalService()
        self._number_internal = CaseNumberInternalService()
        self._details_query = CaseDetailsQueryService()
        self._party_query = CasePartyInternalQueryService()
        self._template_binding_query = CaseTemplateBindingQueryService()

    # ------------------------------------------------------------------
    # Query — internal
    # ------------------------------------------------------------------

    def get_case(self, case_id: int) -> CaseDTO | None:
        return self._internal_query.get_case_internal(case_id=case_id)

    def get_cases_by_contract(self, contract_id: int) -> Any:
        return self._internal_query.get_cases_by_contract_internal(contract_id=contract_id)

    def count_cases_by_contract(self, contract_id: int) -> int:
        return self._command.count_cases_by_contract(contract_id=contract_id)

    def get_primary_lawyer_names_by_case_ids_internal(self, case_ids: list[int]) -> Any:
        return self._internal_query.get_primary_lawyer_names_by_case_ids_internal(case_ids=case_ids)

    def search_cases_for_binding_internal(self, search_term: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self._internal_query.search_cases_for_binding_internal(search_term=search_term, limit=limit)

    def get_primary_case_numbers_by_case_ids_internal(self, case_ids: list[int]) -> Any:
        return self._internal_query.get_primary_case_numbers_by_case_ids_internal(case_ids=case_ids)

    def check_case_access(self, case_id: int, user_id: int) -> Any:
        return self._internal_query.check_case_access_internal(case_id=case_id, user_id=user_id)

    def get_cases_by_ids(self, case_ids: list[int]) -> Any:
        return self._internal_query.get_cases_by_ids_internal(case_ids=case_ids)

    def validate_case_active(self, case_id: int) -> Any:
        return self._internal_query.validate_case_active_internal(case_id=case_id)

    def get_case_current_stage(self, case_id: int) -> Any:
        return self._internal_query.get_case_current_stage_internal(case_id=case_id)

    def get_user_extra_case_access(self, user_id: int) -> Any:
        return self._internal_query.get_user_extra_case_access_internal(user_id=user_id)

    def get_case_by_id_internal(self, case_id: int) -> CaseDTO | None:
        return self._internal_query.get_case_internal(case_id=case_id)

    def search_cases_by_party_internal(self, party_names: list[str], status: str | None = None) -> Any:
        return self._internal_query.search_cases_by_party_internal(party_names=party_names, status=status)

    def get_case_numbers_by_case_internal(self, case_id: int) -> Any:
        return self._internal_query.get_case_numbers_by_case_internal(case_id=case_id)

    def get_case_party_names_internal(self, case_id: int) -> Any:
        return self._internal_query.get_case_party_names_internal(case_id=case_id)

    def search_cases_by_case_number_internal(self, case_number: str) -> Any:
        return self._internal_query.search_cases_by_case_number_internal(case_number=case_number)

    def list_cases_internal(
        self, status: str | None = None, limit: int | None = None, order_by: str = "-start_date"
    ) -> Any:
        return self._internal_query.list_cases_internal(status=status, limit=limit, order_by=order_by)

    def search_cases_internal(self, query: str, status: str | None = None, limit: int = 30) -> Any:
        return self._internal_query.search_cases_internal(query=query, status=status, limit=limit)

    def get_case_internal(self, case_id: int) -> CaseDTO | None:
        return self._internal_query.get_case_internal(case_id=case_id)

    # ------------------------------------------------------------------
    # Query — details / log / party / template
    # ------------------------------------------------------------------

    def get_case_model_internal(self, case_id: int) -> Any | None:
        return self._details_query.get_case_model_internal(case_id=case_id)

    def get_case_with_details_internal(self, case_id: int) -> Any:
        return self._details_query.get_case_with_details_internal(case_id=case_id)

    def get_case_log_model_internal(self, case_log_id: int) -> Any | None:
        return self._log_internal.get_case_log_model_internal(case_log_id=case_log_id)

    def get_case_parties_by_legal_status_internal(self, case_id: int, legal_status: str) -> Any:
        return self._party_query.get_case_parties_by_legal_status_internal(case_id=case_id, legal_status=legal_status)

    def get_case_parties_internal(self, case_id: int, legal_status: str | None = None) -> Any:
        return self._party_query.get_case_parties_internal(case_id=case_id, legal_status=legal_status)

    def get_case_template_binding_internal(self, case_id: int) -> Any:
        return self._template_binding_query.get_case_template_binding_internal(case_id=case_id)

    def get_case_template_bindings_by_name_internal(self, case_id: int, template_name: str) -> Any:
        return self._template_binding_query.get_case_template_bindings_by_name_internal(
            case_id=case_id, template_name=template_name
        )

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def create_case(
        self,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        if user is None and not perm_open_access:
            perm_open_access = True
        case = self._command.create_case(data=data, user=user, org_access=org_access, perm_open_access=perm_open_access)
        dto = self._internal_query.get_case_internal(case_id=case.id)
        if not dto:
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case.id})
        return dto

    def unbind_cases_from_contract_internal(self, contract_id: int) -> Any:
        return self._command.unbind_cases_from_contract_internal(contract_id)

    def create_case_assignment(self, case_id: int, lawyer_id: int) -> Any:
        from apps.cases.services.party.case_assignment_service import CaseAssignmentService

        return CaseAssignmentService().create_assignment_internal(case_id=case_id, lawyer_id=lawyer_id)

    def create_case_party(self, case_id: int, client_id: int, legal_status: str | None = None) -> Any:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        return CasePartyMutationService(
            client_service=self._client_service,
            contract_service=self._contract_service,
        ).create_party_internal(case_id=case_id, client_id=client_id, legal_status=legal_status)

    # ------------------------------------------------------------------
    # Log / Number mutations
    # ------------------------------------------------------------------

    def create_case_log_internal(self, case_id: int, content: str, user_id: int | None = None) -> Any:
        return self._log_internal.create_case_log_internal(case_id=case_id, content=content, user_id=user_id)

    def add_case_log_attachment_internal(self, case_log_id: int, file_path: str, file_name: str) -> Any:
        return self._log_internal.add_case_log_attachment_internal(
            case_log_id=case_log_id, file_path=file_path, file_name=file_name
        )

    def add_case_number_internal(self, case_id: int, case_number: str, user_id: int | None = None) -> Any:
        return self._number_internal.add_case_number_internal(case_id=case_id, case_number=case_number, user_id=user_id)

    def update_case_log_reminder_internal(self, case_log_id: int, reminder_time: Any, reminder_type: str) -> Any:
        return self._log_internal.update_case_log_reminder_internal(
            case_log_id=case_log_id, reminder_time=reminder_time, reminder_type=reminder_type
        )
