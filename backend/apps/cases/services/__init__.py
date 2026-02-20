"""
Cases Services Module
业务逻辑服务层
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.interfaces import IContractService

    from .case.case_access_policy import CaseAccessPolicy
    from .case.case_search_service import CaseSearchService

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

    def __init__(
        self,
        contract_service: IContractService | None = None,
        search_service: CaseSearchService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        from .case.case_access_policy import CaseAccessPolicy as _CaseAccessPolicy
        from .case.case_search_service import CaseSearchService as _CaseSearchService

        resolved_policy: _CaseAccessPolicy = access_policy or _CaseAccessPolicy()
        resolved_search: _CaseSearchService = search_service or _CaseSearchService(access_policy=resolved_policy)
        CaseQueryService.__init__(self, search_service=resolved_search, access_policy=resolved_policy)
        CaseCommandService.__init__(self, contract_service=contract_service, access_policy=resolved_policy)


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
