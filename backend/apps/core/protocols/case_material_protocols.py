"""Module for case material protocols."""

from typing import Any, Protocol


class ICaseMaterialService(Protocol):
    def list_bind_candidates(
        self,
        *,
        case_id: int,
        user: Any,
        org_access: Any,
        perm_open_access: bool,
    ) -> list[Any]: ...

    def bind_materials(
        self,
        *,
        case_id: int,
        items: list[dict[str, Any]],
        user: Any,
        org_access: Any,
        perm_open_access: bool,
    ) -> list[Any]: ...

    def save_group_order(
        self,
        *,
        case_id: int,
        category: str,
        ordered_type_ids: list[int],
        side: str | None,
        supervising_authority_id: int | None,
        user: Any,
        org_access: Any,
        perm_open_access: bool,
    ) -> None: ...

    def get_case_materials_view(
        self,
        *,
        case_id: int,
        user: Any | None = None,
        org_access: Any | None = None,
        perm_open_access: bool = False,
    ) -> Any: ...
