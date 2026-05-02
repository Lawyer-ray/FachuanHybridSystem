"""
诉讼文书草稿生成服务

提供诉讼文书草稿的生成功能.

Requirements: 2.4
"""

import logging
from collections.abc import Callable
from typing import Any

from apps.litigation_ai.models import LitigationSession

logger = logging.getLogger("apps.litigation_ai")


class DraftService:
    """
    草稿生成服务(简化版,供 Agent 工具调用)
    """

    def generate_draft_for_agent(
        self,
        case_id: int,
        document_type: str,
        litigation_goal: str,
        evidence_context: str,
    ) -> dict[str, Any]:
        """
        生成诉讼文书草稿(供 Agent 工具调用)

        Args:
            case_id: 案件 ID
            document_type: 文书类型
            litigation_goal: 诉讼目标
            evidence_context: 证据上下文摘要

        Returns:
            生成结果,包含 display_text, draft, model 等字段
        """
        import asyncio

        from apps.litigation_ai.chains import LitigationDraftChain

        from ..session.context_service import LitigationContextService

        context_service = LitigationContextService()
        case_info = context_service.build_case_info(case_id, document_type)

        chain = LitigationDraftChain()

        # 同步执行异步方法
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            chain.arun(
                case_info=case_info,
                document_type=document_type,
                litigation_goal=litigation_goal,
                evidence_text=evidence_context,
            )
        )

        return {
            "display_text": result.display_text,
            "draft": result.draft,
            "model": result.model,
        }


class LitigationDraftService:
    async def generate_draft_async(
        self,
        *,
        case_id: int,
        session_id: str,
        document_type: str,
        litigation_goal: str,
        evidence_list_ids: list[int],
        evidence_item_ids: list[int],
        our_evidence_item_ids: list[int] | None = None,
        opponent_evidence_item_ids: list[int] | None = None,
        stream_callback: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.chains import LitigationDraftChain

        from ..session.context_service import LitigationContextService
        from ..evidence.evidence_digest_service import EvidenceDigestService

        context_service = LitigationContextService()
        evidence_service = EvidenceDigestService()

        case_info = await sync_to_async(context_service.build_case_info)(case_id, document_type)
        our_evidence_item_ids = our_evidence_item_ids or []
        opponent_evidence_item_ids = opponent_evidence_item_ids or []

        evidence_text = await sync_to_async(evidence_service.build_evidence_text)(evidence_list_ids, evidence_item_ids)
        if document_type in ["defense", "counterclaim_defense"]:
            our_text = await sync_to_async(evidence_service.build_evidence_text)([], our_evidence_item_ids)
            opponent_text = await sync_to_async(evidence_service.build_evidence_text)([], opponent_evidence_item_ids)
            parts = []
            if opponent_text:
                parts.extend(["# 对方证据摘要", opponent_text, ""])
            if our_text:
                parts.extend(["# 我方证据摘要", our_text, ""])
            evidence_text = "\n".join(parts).strip() or evidence_text

        rag_ids = evidence_item_ids
        if document_type in ["defense", "counterclaim_defense"]:
            rag_ids = list(dict.fromkeys(opponent_evidence_item_ids + our_evidence_item_ids))

        if rag_ids:
            from ..evidence.evidence_rag_service import EvidenceRAGService

            rag = EvidenceRAGService()
            await sync_to_async(rag.ensure_ingested)(rag_ids)
            retrieved = await sync_to_async(rag.retrieve)(
                f"{document_type};{case_info.get('cause_of_action', '')};{litigation_goal}",
                rag_ids,
                5,
            )
            if retrieved:
                evidence_text = "\n".join(
                    [
                        evidence_text,
                        "",
                        "# 证据摘录(检索匹配)",
                        *[
                            f"[证据#{c.evidence_item_id} p{c.page_start}] {c.text[:500]}".strip()
                            for c in retrieved
                            if c.text
                        ],
                    ]
                ).strip()

        chain = LitigationDraftChain()
        result = await chain.arun(
            case_info=case_info,
            document_type=document_type,
            litigation_goal=litigation_goal,
            evidence_text=evidence_text,
            stream_callback=stream_callback,
        )

        await sync_to_async(self._persist_draft)(session_id, result.draft)

        return {
            "display_text": result.display_text,
            "draft": result.draft,
            "model": result.model,
            "token_usage": result.token_usage,
        }

    def _persist_draft(self, session_id: str, draft: dict[str, Any]) -> None:
        session = LitigationSession.objects.filter(session_id=session_id).first()
        if not session:
            return
        metadata = session.metadata or {}
        metadata["draft"] = draft
        session.metadata = metadata
        session.save(update_fields=["metadata"])
