"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.core.exceptions import NotFoundError
from apps.core.interfaces import CaseDTO, IClientService, IContractService

from .case_service import CaseService
from .composition import build_case_service

if TYPE_CHECKING:
    pass


class CaseServiceAdapter:
    def __init__(
        self,
        *,
        service: CaseService | None = None,
        contract_service: IContractService | None = None,
        client_service: IClientService | None = None,
    ) -> None:
        if service is not None:
            resolved_service = service
            resolved_client_service = client_service
            resolved_contract_service = contract_service
        else:
            if contract_service is None:
                raise RuntimeError("CaseServiceAdapter.contract_service 未注入")
            if client_service is None:
                raise RuntimeError("CaseServiceAdapter.client_service 未注入")
            resolved_service = build_case_service(contract_service=contract_service)
            resolved_client_service = client_service
            resolved_contract_service = contract_service

        self.service: CaseService = resolved_service
        self._client_service = resolved_client_service
        self._contract_service = resolved_contract_service

    def get_case(self, case_id: int) -> CaseDTO | None:
        return self.service.internal_query_service.get_case_internal(case_id=case_id)

    def get_cases_by_contract(self, contract_id: int) -> Any:
        return self.service.internal_query_service.get_cases_by_contract_internal(contract_id=contract_id)

    def unbind_cases_from_contract_internal(self, contract_id: int) -> Any:
        return self.service.mutation_service.unbind_cases_from_contract_internal(contract_id)

    def get_primary_lawyer_names_by_case_ids_internal(self, case_ids: list[int]) -> Any:
        return self.service.internal_query_service.get_primary_lawyer_names_by_case_ids_internal(case_ids=case_ids)

    def search_cases_for_binding_internal(self, search_term: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self.service.internal_query_service.search_cases_for_binding_internal(
            search_term=search_term, limit=limit
        )

    def get_primary_case_numbers_by_case_ids_internal(self, case_ids: list[int]) -> Any:
        return self.service.internal_query_service.get_primary_case_numbers_by_case_ids_internal(case_ids=case_ids)

    def check_case_access(self, case_id: int, user_id: int) -> Any:
        return self.service.internal_query_service.check_case_access_internal(case_id=case_id, user_id=user_id)

    def get_cases_by_ids(self, case_ids: list[int]) -> Any:
        return self.service.internal_query_service.get_cases_by_ids_internal(case_ids=case_ids)

    def validate_case_active(self, case_id: int) -> Any:
        return self.service.internal_query_service.validate_case_active_internal(case_id=case_id)

    def get_case_current_stage(self, case_id: int) -> Any:
        return self.service.internal_query_service.get_case_current_stage_internal(case_id=case_id)

    def create_case(
        self,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        if user is None and not perm_open_access:
            perm_open_access = True
        case = self.service.create_case(data, user=user, org_access=org_access, perm_open_access=perm_open_access)
        dto = self.service.internal_query_service.get_case_internal(case_id=case.id)
        if not dto:
            raise NotFoundError(f"案件 {case.id} 不存在")
        return dto

    def create_case_assignment(self, case_id: int, lawyer_id: int) -> Any:
        from apps.cases.services.party.case_assignment_service import CaseAssignmentService

        return CaseAssignmentService().create_assignment_internal(case_id=case_id, lawyer_id=lawyer_id)

    def create_case_party(self, case_id: int, client_id: int, legal_status: str | None = None) -> Any:
        from apps.cases.services.party.case_party_mutation_service import CasePartyMutationService

        return CasePartyMutationService(
            client_service=self._client_service,  # type: ignore
            contract_service=self._contract_service,  # type: ignore
        ).create_party_internal(case_id=case_id, client_id=client_id, legal_status=legal_status)

    def get_user_extra_case_access(self, user_id: int) -> Any:
        return self.service.internal_query_service.get_user_extra_case_access_internal(user_id=user_id)

    def get_case_by_id_internal(self, case_id: int) -> CaseDTO | None:
        return self.service.internal_query_service.get_case_internal(case_id=case_id)

    def search_cases_by_party_internal(self, party_names: list[str], status: str | None = None) -> Any:
        return self.service.internal_query_service.search_cases_by_party_internal(
            party_names=party_names, status=status
        )

    def get_case_numbers_by_case_internal(self, case_id: int) -> Any:
        return self.service.internal_query_service.get_case_numbers_by_case_internal(case_id=case_id)

    def get_case_party_names_internal(self, case_id: int) -> Any:
        return self.service.internal_query_service.get_case_party_names_internal(case_id=case_id)

    def search_cases_by_case_number_internal(self, case_number: str) -> Any:
        return self.service.internal_query_service.search_cases_by_case_number_internal(case_number=case_number)

    def list_cases_internal(
        self, status: str | None = None, limit: int | None = None, order_by: str = "-start_date"
    ) -> Any:
        return self.service.internal_query_service.list_cases_internal(status=status, limit=limit, order_by=order_by)

    def search_cases_internal(self, query: str, status: str | None = None, limit: int = 30) -> Any:
        return self.service.internal_query_service.search_cases_internal(query=query, status=status, limit=limit)

    def create_case_log_internal(self, case_id: int, content: str, user_id: int | None = None) -> Any:
        return self.service.log_internal_service.create_case_log_internal(
            case_id=case_id, content=content, user_id=user_id
        )

    def add_case_log_attachment_internal(self, case_log_id: int, file_path: str, file_name: str) -> Any:
        return self.service.log_internal_service.add_case_log_attachment_internal(
            case_log_id=case_log_id, file_path=file_path, file_name=file_name
        )

    def add_case_number_internal(self, case_id: int, case_number: str, user_id: int | None = None) -> Any:
        return self.service.number_internal_service.add_case_number_internal(
            case_id=case_id, case_number=case_number, user_id=user_id
        )

    def update_case_log_reminder_internal(self, case_log_id: int, reminder_time: Any, reminder_type: str) -> Any:
        return self.service.log_internal_service.update_case_log_reminder_internal(
            case_log_id=case_log_id, reminder_time=reminder_time, reminder_type=reminder_type
        )

    def get_case_model_internal(self, case_id: int) -> Any | None:
        return self.service.details_query_service.get_case_model_internal(case_id=case_id)

    def get_case_log_model_internal(self, case_log_id: int) -> Any | None:
        return self.service.log_internal_service.get_case_log_model_internal(case_log_id=case_log_id)

    def get_case_with_details_internal(self, case_id: int) -> Any:
        return self.service.details_query_service.get_case_with_details_internal(case_id=case_id)

    def get_case_parties_by_legal_status_internal(self, case_id: int, legal_status: str) -> Any:
        return self.service.party_query_service.get_case_parties_by_legal_status_internal(
            case_id=case_id, legal_status=legal_status
        )

    def get_case_template_binding_internal(self, case_id: int) -> Any:
        return self.service.template_binding_query_service.get_case_template_binding_internal(case_id=case_id)

    def get_case_parties_internal(self, case_id: int, legal_status: str | None = None) -> Any:
        return self.service.party_query_service.get_case_parties_internal(case_id=case_id, legal_status=legal_status)

    def get_case_template_bindings_by_name_internal(self, case_id: int, template_name: str) -> Any:
        return self.service.template_binding_query_service.get_case_template_bindings_by_name_internal(
            case_id=case_id, template_name=template_name
        )

    def get_case_internal(self, case_id: int) -> CaseDTO | None:
        return self.service.internal_query_service.get_case_internal(case_id=case_id)
