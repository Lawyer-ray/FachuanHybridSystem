from collections.abc import Iterable

from apps.cases.models import CaseNumber


class CaseNumberRepo:
    def get_primary_case_number(self, case_id: int) -> str | None:
        return CaseNumber.objects.filter(case_id=case_id).order_by("id").values_list("number", flat=True).first()

    def list_case_numbers_by_case_ids(self, case_ids: Iterable[int]) -> list[tuple[int, str]]:
        if not case_ids:
            return []
        return list(
            CaseNumber.objects.filter(case_id__in=case_ids).order_by("case_id", "id").values_list("case_id", "number")
        )

    def get_case_numbers_by_case(self, case_id: int) -> list[str]:
        case_numbers = CaseNumber.objects.filter(case_id=case_id).values_list("number", flat=True)
        return list(case_numbers)
