"""案由和法院数据访问层"""

from typing import Any

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from apps.core.models import CauseOfAction, Court


class CauseCourtRepository:
    """案由和法院数据访问层"""

    def has_active_causes(self) -> bool:
        return CauseOfAction.objects.filter(is_active=True, is_deprecated=False).exists()

    def has_active_courts(self) -> bool:
        return Court.objects.filter(is_active=True).exists()

    def get_cause_by_name(self, name: str) -> CauseOfAction | None:
        return CauseOfAction.objects.filter(
            is_active=True, is_deprecated=False, name=name.strip()
        ).first()

    def get_cause_by_id(self, cause_id: int) -> CauseOfAction | None:
        return CauseOfAction.objects.filter(id=cause_id).select_related("parent").first()

    def get_active_cause_by_id(self, cause_id: int) -> CauseOfAction | None:
        return CauseOfAction.objects.filter(
            id=cause_id, is_active=True, is_deprecated=False
        ).first()

    def search_causes(
        self, query: str, case_type_filter: list[str] | None = None
    ) -> QuerySet[CauseOfAction]:
        qs = CauseOfAction.objects.filter(
            is_active=True, is_deprecated=False
        ).filter(Q(name__icontains=query) | Q(code__icontains=query))

        if case_type_filter:
            qs = qs.filter(case_type__in=case_type_filter)

        return qs.annotate(
            relevance=Case(
                When(name=query, then=Value(0)),
                When(name__startswith=query, then=Value(1)),
                When(code=query, then=Value(0)),
                When(code__startswith=query, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("relevance", "name")

    def search_courts(self, query: str) -> QuerySet[Court]:
        return (
            Court.objects.filter(is_active=True)
            .filter(Q(name__icontains=query) | Q(code__icontains=query))
            .annotate(
                relevance=Case(
                    When(name=query, then=Value(0)),
                    When(name__startswith=query, then=Value(1)),
                    When(code=query, then=Value(0)),
                    When(code__startswith=query, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("relevance", "name")
        )

    def get_causes_by_parent(
        self, parent_id: int | None, case_type: str | None = None
    ) -> QuerySet[CauseOfAction]:
        qs = CauseOfAction.objects.filter(is_active=True, is_deprecated=False)
        if parent_id is None:
            qs = qs.filter(parent__isnull=True)
        else:
            qs = qs.filter(parent_id=parent_id)
        if case_type:
            qs = qs.filter(case_type=case_type)
        return qs.order_by("name")

    def update_or_create_cause(self, code: str, defaults: dict[str, Any]) -> tuple[CauseOfAction, bool]:
        return CauseOfAction.objects.update_or_create(code=code, defaults=defaults)

    def update_or_create_court(self, code: str, defaults: dict[str, Any]) -> tuple[Court, bool]:
        return Court.objects.update_or_create(code=code, defaults=defaults)

    def get_courts_excluding_codes(self, codes: list[str]) -> QuerySet[Court]:
        return Court.objects.exclude(code__in=codes)
