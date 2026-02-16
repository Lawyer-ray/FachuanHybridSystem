"""
跨模块 Protocol 兼容出口(Organization)
"""

from apps.core.protocols import (
    IClientService,
    ILawFirmService,
    ILawyerService,
    IOrganizationService,
    IPermissionService,
)

__all__: list[str] = [
    "IOrganizationService",
    "ILawyerService",
    "ILawFirmService",
    "IClientService",
    "IPermissionService",
]
