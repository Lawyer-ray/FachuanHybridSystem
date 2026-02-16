"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .assembler import CaseDtoAssembler
from .case_assignment_aggregation_service import CaseAssignmentAggregationService
from .case_number_aggregation_service import CaseNumberAggregationService
from .case_party_aggregation_service import CasePartyAggregationService

if TYPE_CHECKING:
    from apps.core.interfaces import CaseDTO

from .repo import CaseAccessRepo, CaseAssignmentRepo, CaseNumberRepo, CasePartyRepo, CaseRepo, CaseSearchRepo


class CaseNumberQueryOrchestrator:
    def __init__(
        self,
        case_number_repo: CaseNumberRepo | None = None,
        case_search_repo: CaseSearchRepo | None = None,
        case_number_aggregation_service: CaseNumberAggregationService | None = None,
    ) -> None:
        self.case_number_repo = case_number_repo or CaseNumberRepo()
        self.case_search_repo = case_search_repo or CaseSearchRepo()
        self.case_number_aggregation_service = case_number_aggregation_service or CaseNumberAggregationService(
            case_number_repo=self.case_number_repo
        )

    def get_primary_case_number(self, case_id: int) -> str | None:
        return self.case_number_repo.get_primary_case_number(case_id)

    def get_primary_case_numbers_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.case_number_aggregation_service.get_primary_case_numbers_by_case_ids(case_ids)

    def get_case_numbers_by_case(self, case_id: int) -> list[str]:
        return self.case_number_repo.get_case_numbers_by_case(case_id)

    def search_cases_by_case_number(self, case_number: str) -> Any:
        return self.case_search_repo.search_cases_by_case_number(case_number)


class CasePartyQueryOrchestrator:
    def __init__(
        self,
        case_party_repo: CasePartyRepo | None = None,
        case_party_aggregation_service: CasePartyAggregationService | None = None,
    ) -> None:
        self.case_party_repo = case_party_repo or CasePartyRepo()
        self.case_party_aggregation_service = case_party_aggregation_service or CasePartyAggregationService(
            case_party_repo=self.case_party_repo
        )

    def search_cases_by_party(self, party_names: list[str], status: str | None = None) -> Any:
        return self.case_party_repo.search_cases_by_party(party_names, status=status)

    def get_case_party_names(self, case_id: int) -> list[str]:
        return self.case_party_aggregation_service.get_case_party_names(case_id)


class CaseAccessQueryOrchestrator:
    def __init__(
        self,
        case_access_repo: CaseAccessRepo | None = None,
        case_assignment_repo: CaseAssignmentRepo | None = None,
        case_assignment_aggregation_service: CaseAssignmentAggregationService | None = None,
    ) -> None:
        self.case_access_repo = case_access_repo or CaseAccessRepo()
        self.case_assignment_repo = case_assignment_repo or CaseAssignmentRepo()
        self.case_assignment_aggregation_service = (
            case_assignment_aggregation_service
            or CaseAssignmentAggregationService(case_assignment_repo=self.case_assignment_repo)
        )

    def check_case_access(self, case_id: int, user_id: int) -> bool:
        return self.case_assignment_repo.check_case_access(case_id, user_id)

    def get_user_extra_case_access(self, user_id: int) -> list[int]:
        return self.case_access_repo.get_user_extra_case_access(user_id)

    def get_primary_lawyer_names_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.case_assignment_aggregation_service.get_primary_lawyer_names_by_case_ids(case_ids)


class CaseQueryOrchestrator:
    def __init__(
        self,
        case_repo: CaseRepo | None = None,
        case_search_repo: CaseSearchRepo | None = None,
        case_number_orchestrator: CaseNumberQueryOrchestrator | None = None,
        case_party_orchestrator: CasePartyQueryOrchestrator | None = None,
        case_access_orchestrator: CaseAccessQueryOrchestrator | None = None,
        assembler: CaseDtoAssembler | None = None,
    ) -> None:
        self.case_repo = case_repo or CaseRepo()
        self.case_search_repo = case_search_repo or CaseSearchRepo()
        self.case_number_orchestrator = case_number_orchestrator or CaseNumberQueryOrchestrator(
            case_search_repo=self.case_search_repo
        )
        self.case_party_orchestrator = case_party_orchestrator or CasePartyQueryOrchestrator()
        self.case_access_orchestrator = case_access_orchestrator or CaseAccessQueryOrchestrator()
        self.assembler = assembler or CaseDtoAssembler()

    def _build_case_number_map(self, cases: list[Any]) -> dict[int, str | None]:
        if not cases:
            return {}
        case_ids = [case.id for case in cases]
        return self.case_number_orchestrator.get_primary_case_numbers_by_case_ids(case_ids)

    def get_case(self, case_id: int) -> CaseDTO | None | None:
        case = self.case_repo.get_case_by_id(case_id)
        if not case:
            return None
        case_number = self.case_number_orchestrator.get_primary_case_number(case_id)
        return self.assembler.to_dto(case, case_number)

    def get_cases_by_contract(self, contract_id: int) -> list[CaseDTO]:
        cases = self.case_repo.get_cases_by_contract(contract_id)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))

    def get_cases_by_ids(self, case_ids: list[int]) -> list[CaseDTO]:
        cases = self.case_repo.get_cases_by_ids(case_ids)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))

    def validate_case_active(self, case_id: int) -> bool:
        return self.case_repo.validate_case_active(case_id)

    def get_case_current_stage(self, case_id: int) -> str | None:
        return self.case_repo.get_case_current_stage(case_id)

    def check_case_access(self, case_id: int, user_id: int) -> bool:
        return self.case_access_orchestrator.check_case_access(case_id, user_id)

    def get_primary_lawyer_names_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.case_access_orchestrator.get_primary_lawyer_names_by_case_ids(case_ids)

    def get_primary_case_numbers_by_case_ids(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.case_number_orchestrator.get_primary_case_numbers_by_case_ids(case_ids)

    def get_user_extra_case_access(self, user_id: int) -> list[int]:
        return self.case_access_orchestrator.get_user_extra_case_access(user_id)

    def search_cases_by_party(self, party_names: list[str], status: str | None = None) -> list[CaseDTO]:
        cases = self.case_party_orchestrator.search_cases_by_party(party_names, status=status)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))

    def get_case_numbers_by_case(self, case_id: int) -> list[str]:
        return self.case_number_orchestrator.get_case_numbers_by_case(case_id)

    def get_case_party_names(self, case_id: int) -> list[str]:
        return self.case_party_orchestrator.get_case_party_names(case_id)

    def search_cases_by_case_number(self, case_number: str) -> list[CaseDTO]:
        cases = self.case_number_orchestrator.search_cases_by_case_number(case_number)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))

    def list_cases(
        self, status: str | None = None, limit: int | None = None, order_by: str = "-start_date"
    ) -> list[CaseDTO]:
        cases = self.case_repo.list_cases(status=status, limit=limit, order_by=order_by)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))

    def search_cases(self, query: str, status: str | None = None, limit: int = 30) -> list[CaseDTO]:
        cases = self.case_search_repo.search_cases(query=query, status=status, limit=limit)
        return self.assembler.to_dtos(cases, self._build_case_number_map(cases))
