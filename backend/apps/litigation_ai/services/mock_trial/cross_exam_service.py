"""质证模拟 Service."""

from __future__ import annotations

import logging
from typing import Any

from apps.litigation_ai.chains.mock_trial_chains import CrossExamChain, CrossExamResult
from apps.litigation_ai.services.session.context_service import LitigationContextService
from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

logger = logging.getLogger("apps.litigation_ai")


class CrossExamService:
    """质证模拟：逐份证据进行三性质证."""

    async def load_evidence_list(self, case_id: int) -> list[dict[str, Any]]:
        """加载案件证据列表."""
        from asgiref.sync import sync_to_async

        raw = await sync_to_async(LitigationContextService.get_evidence_list_for_agent, thread_sensitive=True)(case_id)  # type: ignore[call-arg,arg-type]
        return raw or []

    async def examine_single(self, *, case_info: dict[str, Any], evidence_info: dict[str, Any]) -> CrossExamResult:
        """对单份证据进行质证."""
        chain = CrossExamChain()
        return await chain.arun(case_info=case_info, evidence_info=evidence_info)
