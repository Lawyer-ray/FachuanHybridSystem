"""Business logic services."""

from __future__ import annotations

from typing import Any, TypedDict


class PlaceholderContextData(TypedDict, total=False):
    contract: Any
    contract_id: int
    supplementary_agreement: Any
    agreement_principals: Any
    contract_principals: Any
    agreement_opposing: Any
