"""法官视角分析服务."""

import logging
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger("apps.litigation_ai")


class JudgePerspectiveService:
    """法官视角分析：调用 LLM 生成结构化报告."""

    async def generate_analysis(
        self,
        *,
        case_id: int,
        session_id: str,
        evidence_item_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        from apps.litigation_ai.chains.mock_trial_chains import JudgePerspectiveChain
        from apps.litigation_ai.services.context_service import LitigationContextService
        from apps.litigation_ai.services.evidence_digest_service import EvidenceDigestService
        from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

        ctx_service = LitigationContextService()
        evidence_service = EvidenceDigestService()

        case_info = await sync_to_async(ctx_service.get_case_info_for_agent, thread_sensitive=True)(case_id)
        evidence_text = ""
        if evidence_item_ids:
            evidence_text = await sync_to_async(evidence_service.build_evidence_text, thread_sensitive=True)(
                [], evidence_item_ids
            )
        else:
            # 加载案件全部证据
            items = await sync_to_async(ctx_service.get_evidence_list_for_agent, thread_sensitive=True)(case_id)
            if items:
                lines = [f"[证据#{it['evidence_item_id']}] {it['name']}（{it['description']}）" for it in items]
                evidence_text = "\n".join(lines)

        chain = JudgePerspectiveChain()
        result = await chain.arun(case_info=case_info, evidence_text=evidence_text)

        # 持久化报告到 session metadata
        repo = LitigationSessionRepository()
        await repo.update_metadata(session_id, {
            "report": result.report,
            "report_model": result.model,
            "report_token_usage": result.token_usage,
        })

        return {
            "report": result.report,
            "model": result.model,
            "token_usage": result.token_usage,
        }
