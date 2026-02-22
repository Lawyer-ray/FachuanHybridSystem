"""Business logic services."""

from typing import Any, ClassVar

from apps.core.repositories import CauseCourtRepository


class CauseCourtQueryService:
    CASE_TYPE_DB_MAP: ClassVar[dict[str, list[str]]] = {
        "civil": ["civil"],
        "criminal": ["criminal"],
        "administrative": ["administrative"],
        "execution": ["civil", "criminal", "administrative"],
        "bankruptcy": [],
    }

    def __init__(self, *, repository: CauseCourtRepository | None = None) -> None:
        self._repository = repository or CauseCourtRepository()

    def has_active_causes_internal(self) -> bool:
        return self._repository.has_active_causes()

    def has_active_courts_internal(self) -> bool:
        return self._repository.has_active_courts()

    def get_cause_id_by_name_internal(self, name: str) -> int | None | None:
        if not name or not name.strip():
            return None
        cause = self._repository.get_cause_by_name(name.strip())
        return cause.id if cause else None

    def get_cause_ancestor_codes_internal(self, cause_id: int) -> list[str]:
        cause = self._repository.get_cause_by_id(cause_id)
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
        cause = self._repository.get_active_cause_by_id(cause_id)
        if cause is None:
            return None
        return {
            "id": cause.id,
            "name": cause.name,
            "code": cause.code,
            "case_type": cause.case_type,
        }

    def get_cause_ancestor_names_internal(self, cause_id: int) -> list[str]:
        cause = self._repository.get_cause_by_id(cause_id)
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

        db_case_types = None
        if case_type:
            db_case_types = self.CASE_TYPE_DB_MAP.get(case_type, [])
            if not db_case_types:
                return []

        qs = self._repository.search_causes(query, db_case_types)[:limit]
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

        qs = self._repository.search_courts(query)[:limit]
        return [{"id": court.code, "name": court.name} for court in qs]

    def list_causes_by_parent_internal(self, parent_id: int | None = None) -> list[dict[str, Any]]:
        if parent_id is None:
            results: list[dict[str, Any]] = []
            for case_type in ["civil", "criminal", "administrative"]:
                type_qs = self._repository.get_causes_by_parent(None, case_type)
                top_level = type_qs.filter(parent__isnull=True)
                if top_level.exists():
                    qs = top_level
                else:
                    qs = type_qs.filter(parent__case_type__in=["civil", "criminal", "administrative"]).exclude(
                        parent__case_type=case_type
                    )

                for cause in qs.order_by("code"):
                    has_children = self._repository.get_causes_by_parent(cause.id).exists()
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

        qs = self._repository.get_causes_by_parent(parent_id)
        parent_results: list[dict[str, Any]] = []
        for cause in qs:
            has_children = self._repository.get_causes_by_parent(cause.id).exists()
            parent_results.append(
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
        return parent_results
