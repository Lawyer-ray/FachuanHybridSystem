"""质证模拟 Service."""

from __future__ import annotations

import logging
from typing import Any

from apps.litigation_ai.chains.mock_trial_chains import CrossExamChain, CrossExamResult
from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
from apps.litigation_ai.services.session.context_service import LitigationContextService

logger = logging.getLogger("apps.litigation_ai")


class CrossExamService:  # pragma: no cover
    """质证模拟：逐份证据进行三性质证."""

    async def load_evidence_list(self, case_id: int) -> list[dict[str, Any]]:  # pragma: no cover
        """加载案件证据列表."""
        from asgiref.sync import sync_to_async

        # S23-03（2026-11-23 二轮审计）：`LitigationContextService.get_evidence_list_for_agent`
        # 是**未绑定**方法（签名为 (self, case_id)），直接交给 sync_to_async 会把
        # `case_id` 当成 `self` 传进去 → 一进质证模式必抛 TypeError。
        # 这里显式绑定实例（若它是 classmethod/staticmethod，绑定也不会破坏调用）。
        svc = LitigationContextService()
        raw = await sync_to_async(svc.get_evidence_list_for_agent, thread_sensitive=True)(case_id)
        return raw or []

    async def examine_single(
        self, *, case_info: dict[str, Any], evidence_info: dict[str, Any]
    ) -> CrossExamResult:  # pragma: no cover
        """对单份证据进行质证."""
        chain = CrossExamChain()
        return await chain.arun(case_info=case_info, evidence_info=evidence_info)
