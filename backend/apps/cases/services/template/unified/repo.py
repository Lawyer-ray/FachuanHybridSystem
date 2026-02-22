"""Data repository layer."""

from __future__ import annotations

from typing import Any


class CasePartyRepository:
    def is_our_party(self, case: Any, *, client_id: int) -> Any:
        return case.parties.filter(client_id=client_id, client__is_our_client=True).exists()

    def count_our_parties(self, case: Any) -> Any:
        return case.parties.filter(client__is_our_client=True).count()
