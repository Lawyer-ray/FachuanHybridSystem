"""Data repository layer."""

from apps.cases.models import Case


class CaseRepo:
    def get_case_by_id(self, case_id: int) -> Case | None:
        return Case.objects.select_related("contract").filter(id=case_id).first()

    def get_cases_by_contract(self, contract_id: int) -> list[Case]:
        return list(Case.objects.filter(contract_id=contract_id).select_related("contract"))

    def get_cases_by_ids(self, case_ids: list[int]) -> list[Case]:
        if not case_ids:
            return []
        return list(Case.objects.filter(id__in=case_ids).select_related("contract"))

    def validate_case_active(self, case_id: int) -> bool:
        return Case.objects.filter(id=case_id, status="active").exists()

    def get_case_current_stage(self, case_id: int) -> str | None:
        case = Case.objects.filter(id=case_id).only("current_stage").first()
        return case.current_stage if case else None

    def list_cases(
        self, status: str | None = None, limit: int | None = None, order_by: str = "-start_date"
    ) -> list[Case]:
        qs = Case.objects.select_related("contract").prefetch_related("parties__client")
        if status:
            qs = qs.filter(status=status)
        if order_by:
            qs = qs.order_by(order_by, "-id")
        if limit:
            qs = qs[:limit]
        return list(qs)
