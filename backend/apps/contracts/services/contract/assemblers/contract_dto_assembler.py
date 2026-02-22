"""Business logic services."""


from __future__ import annotations

from typing import Any


class ContractDtoAssembler:
    def to_dto(self, contract: Any) -> Any:
        from apps.core.interfaces import ContractDTO

        return ContractDTO.from_model(contract)
