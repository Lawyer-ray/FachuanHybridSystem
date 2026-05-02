from __future__ import annotations

from typing import Any

from apps.legal_research.schemas import AgentSearchRequestV1
from .service import LegalResearchCapabilityService


class LegalResearchCapabilityMcpWrapper:
    """给上层 Agent/MCP 调用的轻量封装，输出保持与 capability v1 契约一致。"""

    CONTRACT_VERSION = "v1"

    def __init__(self, *, capability_service: LegalResearchCapabilityService | None = None) -> None:
        self._capability_service = capability_service or LegalResearchCapabilityService()

    def search(
        self,
        *,
        payload: AgentSearchRequestV1,
        user: Any | None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        response = self._capability_service.search(
            payload=payload,
            user=user,
            idempotency_key=idempotency_key,
        )
        return {
            "version": self.CONTRACT_VERSION,
            "request_id": response.request_id,
            "status": response.status,
            "degradation_flags": list(response.degradation_flags),
            "query_trace": response.query_trace.model_dump(),
            "results": [self._serialize_hit(hit) for hit in response.results],
        }

    @staticmethod
    def _serialize_hit(hit: Any) -> dict[str, Any]:
        snippets = hit.snippets if hasattr(hit, "snippets") else None
        subscores = hit.subscores if hasattr(hit, "subscores") else None
        return {
            "doc_id": str(getattr(hit, "doc_id", "") or ""),
            "title": str(getattr(hit, "title", "") or ""),
            "court": str(getattr(hit, "court", "") or ""),
            "judgment_date": str(getattr(hit, "judgment_date", "") or ""),
            "score": float(getattr(hit, "score", 0.0) or 0.0),
            "decision": str(getattr(hit, "decision", "") or ""),
            "subscores": subscores.model_dump() if subscores is not None else {},
            "conflicts": [str(x) for x in (getattr(hit, "conflicts", None) or [])],
            "snippets": snippets.model_dump() if snippets is not None else {},
            "why_selected": str(getattr(hit, "why_selected", "") or ""),
            "source_url": str(getattr(hit, "source_url", "") or ""),
            "agent_summary": (
                f"{getattr(hit, 'title', '') or ''} | "
                f"{getattr(hit, 'court', '') or ''} | "
                f"score={float(getattr(hit, 'score', 0.0) or 0.0):.3f} | "
                f"{(getattr(hit, 'why_selected', '') or '')[:120]}"
            ).strip(" |"),
        }
