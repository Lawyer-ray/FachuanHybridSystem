"""Business logic services."""

from typing import Any, ClassVar

from django.db.models import Case, IntegerField, Q, Value, When

from apps.core.models import CauseOfAction, Court


class CauseCourtQueryService:
    CASE_TYPE_DB_MAP: ClassVar[dict[str, list[str]]] = {
        "civil": ["civil"],
        "criminal": ["criminal"],
        "administrative": ["administrative"],
        "execution": ["civil", "criminal", "administrative"],
        "bankruptcy": [],
    }

    def has_active_causes_internal(self) -> bool:
        return CauseOfAction.objects.filter(is_active=True, is_deprecated=False).exists()

    def has_active_courts_internal(self) -> bool:
        return Court.objects.filter(is_active=True).exists()

    def get_cause_id_by_name_internal(self, name: str) -> int | None | None:
        if not name or not name.strip():
            return None
        cause = (
            CauseOfAction.objects.filter(is_active=True, is_deprecated=False, name=name.strip())
            .values_list("id", flat=True)
            .first()
        )
        return int(cause) if cause else None

    def get_cause_ancestor_codes_internal(self, cause_id: int) -> list[str]:
        cause = CauseOfAction.objects.filter(id=cause_id).select_related("parent").first()
        if not cause:
            return []

        codes: list[str] = [cause.code]
        parent = cause.parent
        while parent:
            codes.append(parent.code)
            parent = parent.parent
        return codes

    def get_cause_by_id_internal(self, cause_id: int) -> dict[str, Any] | None:
        """根据 ID 获取案由信息

        Args:
            cause_id: 案由 ID

        Returns:
            案由信息字典(包含 id, name, code, case_type),不存在返回 None
        """
        try:
            cause = CauseOfAction.objects.get(id=cause_id, is_active=True, is_deprecated=False)
            return {
                "id": cause.id,
                "name": cause.name,
                "code": cause.code,
                "case_type": cause.case_type,
            }
        except CauseOfAction.DoesNotExist:
            return None

    def get_cause_ancestor_names_internal(self, cause_id: int) -> list[str]:
        cause = CauseOfAction.objects.filter(id=cause_id).select_related("parent").first()
        if not cause:
            return []

        names: list[str] = [cause.name]
        parent = cause.parent
        while parent:
            names.append(parent.name)
            parent = parent.parent
        return names

    def search_causes_internal(self, query: str, case_type: str | None, limit: int) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        qs = CauseOfAction.objects.filter(
            is_active=True,
            is_deprecated=False,
        ).filter(Q(name__icontains=query) | Q(code__icontains=query))

        if case_type:
            db_case_types = self.CASE_TYPE_DB_MAP.get(case_type, [])
            if not db_case_types:
                return []
            qs = qs.filter(case_type__in=db_case_types)

        qs = qs.annotate(
            relevance=Case(
                When(name=query, then=Value(0)),
                When(name__startswith=query, then=Value(1)),
                When(code=query, then=Value(0)),
                When(code__startswith=query, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("relevance", "name")[:limit]
        results: list[dict[str, Any]] = []
        for cause in qs:
            results.append(
                {
                    "id": cause.code,
                    "name": f"{cause.name}-{cause.code}",
                    "code": cause.code,
                    "raw_name": cause.name,
                }
            )
        return results

    def search_courts_internal(self, query: str, limit: int) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        qs = Court.objects.filter(is_active=True).filter(Q(name__icontains=query) | Q(code__icontains=query))
        qs = qs.annotate(
            relevance=Case(
                When(name=query, then=Value(0)),
                When(name__startswith=query, then=Value(1)),
                When(code=query, then=Value(0)),
                When(code__startswith=query, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("relevance", "name")[:limit]

        return [{"id": court.code, "name": court.name} for court in qs]

    def list_causes_by_parent_internal(self, parent_id: int | None = None) -> list[dict[str, Any]]:
        base = CauseOfAction.objects.filter(is_active=True, is_deprecated=False)

        if parent_id is None:
            results: list[dict[str, Any]] = []
            for case_type in ["civil", "criminal", "administrative"]:
                type_qs = base.filter(case_type=case_type)
                top_level = type_qs.filter(parent__isnull=True)
                if top_level.exists():
                    qs = top_level
                else:
                    qs = type_qs.filter(parent__case_type__in=["civil", "criminal", "administrative"]).exclude(
                        parent__case_type=case_type
                    )

                for cause in qs.order_by("code"):
                    has_children = base.filter(parent_id=cause.id).exists()
                    results.append(
                        {
                            "id": cause.id,
                            "code": cause.code,
                            "name": cause.name,
                            "case_type": cause.case_type,
                            "level": cause.level,
                            "has_children": has_children,
                            "full_path": cause.full_path,
                        }
                    )
            return results

        qs = base.filter(parent_id=parent_id).order_by("code")
        results: list[Any] = []
        for cause in qs:
            has_children = base.filter(parent_id=cause.id).exists()
            results.append(
                {
                    "id": cause.id,
                    "code": cause.code,
                    "name": cause.name,
                    "case_type": cause.case_type,
                    "level": cause.level,
                    "has_children": has_children,
                    "full_path": cause.full_path,
                }
            )
        return results
