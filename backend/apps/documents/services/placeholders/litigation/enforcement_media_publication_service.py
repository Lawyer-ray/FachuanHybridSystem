"""强制执行申请书 - 申请媒体公布事项占位符服务."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementMediaPublicationRequestService(BasePlaceholderService):
    """生成强制执行申请书中的“申请媒体公布事项”占位符."""

    name: str = "enforcement_media_publication_request_service"
    display_name: str = "诉讼文书-强制执行申请书申请媒体公布事项"
    description: str = "根据被申请人名称生成申请媒体公布事项"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}

        respondent_names = self._get_respondent_names(case_id=int(case_id))
        if not respondent_names:
            logger.warning("未找到被申请人名称，申请媒体公布事项为空: case_id=%s", case_id)
            return {LitigationPlaceholderKeys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST: ""}

        text = (
            f"请求贵院依法将被申请人{respondent_names}"
            "不履行法律文书确定义务的信息，通过报纸、广播、电视、互联网等媒体公布。"
        )
        return {LitigationPlaceholderKeys.ENFORCEMENT_MEDIA_PUBLICATION_REQUEST: text}

    def _get_respondent_names(self, *, case_id: int) -> str:
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)
        respondents = [
            p for p in case_parties if p.get("legal_status") in (LegalStatus.DEFENDANT, LegalStatus.RESPONDENT)
        ]
        if not respondents:
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in respondents:
            name = str(party.get("client_name", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return "、".join(names)
