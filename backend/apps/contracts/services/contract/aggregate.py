"""Business logic services."""


from __future__ import annotations
from .contract_service import ContractService

ContractAggregate = ContractService
ContractServiceRoot = ContractService

__all__: list[str] = [
    "ContractAggregate",
    "ContractServiceRoot",
]
