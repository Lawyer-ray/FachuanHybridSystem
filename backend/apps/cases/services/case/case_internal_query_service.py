"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.core.exceptions import NotFoundError

from .assembler import CaseDtoAssembler
from .case_query_orchestrator import (
    CaseAccessQueryOrchestrator,
    CaseNumberQueryOrchestrator,
    CasePartyQueryOrchestrator,
    CaseQueryOrchestrator,
)
from .repo import CaseRepo, CaseSearchRepo

if TYPE_CHECKING:
    from apps.core.interfaces import CaseDTO

logger = logging.getLogger("apps.cases")


class CaseInternalQueryService:
    _MISSING_SENTINEL = "__case_access_grants_missing__"

    def __init__(
        self,
        orchestrator: CaseQueryOrchestrator | None = None,
        case_repo: CaseRepo | None = None,
        case_search_repo: CaseSearchRepo | None = None,
        case_number_orchestrator: CaseNumberQueryOrchestrator | None = None,
        case_party_orchestrator: CasePartyQueryOrchestrator | None = None,
        case_access_orchestrator: CaseAccessQueryOrchestrator | None = None,
        assembler: CaseDtoAssembler | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._orchestrator_kwargs = {
            "case_repo": case_repo,
            "case_search_repo": case_search_repo,
            "case_number_orchestrator": case_number_orchestrator,
            "case_party_orchestrator": case_party_orchestrator,
            "case_access_orchestrator": case_access_orchestrator,
            "assembler": assembler,
        }

    @property
    def orchestrator(self) -> CaseQueryOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = CaseQueryOrchestrator(**self._orchestrator_kwargs) # type: ignore
        return self._orchestrator

    def get_case_internal(self, case_id: int) -> CaseDTO | None:
        try:
            return self.orchestrator.get_case(case_id)
        except NotFoundError:
            return None
        except Exception:
            logger.exception("get_case_internal_failed", extra={"case_id": case_id})
            raise

    def get_cases_by_contract_internal(self, contract_id: int) -> list[CaseDTO]:
        return self.orchestrator.get_cases_by_contract(contract_id)

    def get_cases_by_ids_internal(self, case_ids: list[int]) -> list[CaseDTO]:
        return self.orchestrator.get_cases_by_ids(case_ids)

    def validate_case_active_internal(self, case_id: int) -> bool:
        return self.orchestrator.validate_case_active(case_id)

    def get_case_current_stage_internal(self, case_id: int) -> str | None:
        return self.orchestrator.get_case_current_stage(case_id)

    def check_case_access_internal(self, case_id: int, user_id: int) -> bool:
        return self.orchestrator.check_case_access(case_id, user_id)

    def get_primary_lawyer_names_by_case_ids_internal(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.orchestrator.get_primary_lawyer_names_by_case_ids(case_ids)

    def get_primary_case_numbers_by_case_ids_internal(self, case_ids: list[int]) -> dict[int, str | None]:
        return self.orchestrator.get_primary_case_numbers_by_case_ids(case_ids)

    def get_user_extra_case_access_internal(self, user_id: int) -> list[int]:
        from django.core.cache import cache

        from apps.core.infrastructure import CacheKeys, CacheTimeout

        cache_key = CacheKeys.case_access_grants(user_id)
        cached = cache.get(cache_key)
        if cached is not None:
            if cached == self._MISSING_SENTINEL:
                return []
            return list(cached or [])

        try:
            result = list(self.orchestrator.get_user_extra_case_access(user_id) or [])
            cache.set(cache_key, result, timeout=CacheTimeout.get_medium())
            return result
        except Exception:
            logger.exception("get_user_extra_case_access_internal_failed", extra={"user_id": user_id})
            raise

    def search_cases_by_party_internal(self, party_names: list[str], status: str | None = None) -> list[CaseDTO]:
        return self.orchestrator.search_cases_by_party(party_names, status=status)

    def search_cases_for_binding_internal(self, search_term: str = "", limit: int = 20) -> list[dict[str, object]]:
        """搜索可绑定的案件(含案号和当事人信息)

        支持按案件名称、案号、当事人搜索.

            search_term: 搜索关键词
            limit: 返回数量限制

            案件信息字典列表
        """
        from django.db.models import Q

        from apps.cases.models import Case, CaseNumber, CaseParty

        limit = min(limit, 20)

        if not search_term or not search_term.strip():
            cases = (
                Case.objects.select_related()
                .prefetch_related("case_numbers", "parties__client")
                .order_by("-id")[:limit]
            )
        else:
            term = search_term.strip()
            name_query = Q(name__icontains=term)
            case_ids_by_number = CaseNumber.objects.filter(
                number__icontains=term,
            ).values_list("case_id", flat=True)
            case_ids_by_party = CaseParty.objects.filter(
                client__name__icontains=term,
            ).values_list("case_id", flat=True)

            cases = (
                Case.objects.filter(
                    name_query | Q(id__in=case_ids_by_number) | Q(id__in=case_ids_by_party),
                )
                .select_related()
                .prefetch_related("case_numbers", "parties__client")
                .distinct()
                .order_by("-id")[:limit]
            )

        results: list[dict[str, object]] = []
        for case in cases:
            case_numbers = [cn.number for cn in case.case_numbers.all()]
            parties = [p.client.name for p in case.parties.all() if p.client]
            results.append(
                {
                    "id": case.id,
                    "name": case.name,
                    "case_numbers": case_numbers,
                    "parties": parties,
                    "created_at": case.start_date.isoformat() if case.start_date else None,
                }
            )

        return results

    def get_case_numbers_by_case_internal(self, case_id: int) -> list[str]:
        return self.orchestrator.get_case_numbers_by_case(case_id)

    def get_case_party_names_internal(self, case_id: int) -> list[str]:
        return self.orchestrator.get_case_party_names(case_id)

    def search_cases_by_case_number_internal(self, case_number: str) -> list[CaseDTO]:
        return self.orchestrator.search_cases_by_case_number(case_number)

    def list_cases_internal(
        self, status: str | None = None, limit: int | None = None, order_by: str = "-start_date"
    ) -> list[CaseDTO]:
        return self.orchestrator.list_cases(status=status, limit=limit, order_by=order_by)

    def search_cases_internal(self, query: str, status: str | None = None, limit: int = 30) -> list[CaseDTO]:
        return self.orchestrator.search_cases(query=query, status=status, limit=limit)
