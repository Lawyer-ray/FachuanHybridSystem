"""
Cases Services Module
业务逻辑服务层
"""

from __future__ import annotations

from .case.case_command_service import CaseCommandService
from .case.case_query_service import CaseQueryService
from .case.case_service_adapter import CaseServiceAdapter
from .case_access_service import CaseAccessService
from .case_assignment_service import CaseAssignmentService
from .case_number_service import CaseNumberService
from .case_party_service import CasePartyService
from .caselog_service import CaseLogService
from .chat_name_config_service import ChatNameConfigService
from .data import CauseCourtDataService
from .folder_binding_service import CaseFolderBindingService


class CaseService(CaseQueryService, CaseCommandService):
    """案件服务兼容层（继承 CaseQueryService + CaseCommandService）。

    保持向后兼容：`from apps.cases.services import CaseService` 仍可用。
    """

    pass


__all__ = [
    "CaseService",
    "CaseQueryService",
    "CaseCommandService",
    "CaseServiceAdapter",
    "CaseLogService",
    "CaseAccessService",
    "CaseAssignmentService",
    "CaseNumberService",
    "CasePartyService",
    "ChatNameConfigService",
    "CaseFolderBindingService",
    "CauseCourtDataService",
]
