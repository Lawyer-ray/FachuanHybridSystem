"""Module for case assignment protocols."""

from typing import Any, Protocol


class ICaseAssignmentService(Protocol):
    def list_assignments(
        self,
        *,
        case_id: int | None = None,
        lawyer_id: int | None = None,
        user: Any | None = None,
    ) -> list[Any]: ...

    def create_assignment(self, *, case_id: int, lawyer_id: int, user: Any | None = None) -> Any: ...

    def get_assignment(self, *, assignment_id: int, user: Any | None = None) -> Any: ...

    def update_assignment(self, *, assignment_id: int, data: dict[str, Any], user: Any | None = None) -> Any: ...

    def delete_assignment(self, *, assignment_id: int, user: Any | None = None) -> Any: ...

    def sync_assignments_from_contract(
        self,
        *,
        case_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> Any: ...
