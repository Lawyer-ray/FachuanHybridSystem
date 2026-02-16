"""
跨模块 Protocol 兼容出口(Contract)
"""

from apps.core.protocols import (
    IContractAssignmentQueryService,
    IContractFolderBindingService,
    IContractPaymentService,
    IContractService,
)

__all__: list[str] = [
    "IContractService",
    "IContractPaymentService",
    "IContractAssignmentQueryService",
    "IContractFolderBindingService",
]
