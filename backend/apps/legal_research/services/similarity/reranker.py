"""交叉编码器重排序 — Reranker API。"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RerankerClient:  # pragma: no cover
    """调用 /v1/rerank 端点做交叉编码器打分。"""

    RERANK_TIMEOUT_SECONDS = 30
    FAIL_COOLDOWN_SECONDS = 120

    def __init__(  # pragma: no cover
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "BAAI/bge-reranker-v2-m3",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._fail_until: float = 0.0

    def rerank(  # pragma: no cover
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """返回按相关性排序的 (原始索引, 分数) 列表。"""
        if not query or not documents:
            return []
        now = time.time()
        if now < self._fail_until:
            return []

        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_k": min(top_k, len(documents)),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.RERANK_TIMEOUT_SECONDS) as client:
                resp = client.post(f"{self._base_url}/rerank", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            self._fail_until = time.time() + self.FAIL_COOLDOWN_SECONDS
            logger.info("Reranker API 调用失败，回退", extra={"error": str(exc)})
            return []

        results = data.get("results") or []
        out: list[tuple[int, float]] = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score")
            if isinstance(idx, int) and isinstance(score, (int, float)):
                out.append((idx, max(0.0, min(1.0, float(score)))))
        out.sort(key=lambda x: x[1], reverse=True)
        return out


def create_reranker_from_tuning(tuning: Any) -> RerankerClient | None:  # pragma: no cover
    """从 tuning config 创建 reranker 实例，若未启用或缺少 API Key 则返回 None。"""
    if not getattr(tuning, "reranker_enabled", False):
        return None
    try:
        from apps.core.interfaces import ServiceLocator

        config_service = ServiceLocator.get_system_config_service()
        api_key = str(config_service.get_value("OPENAI_COMPATIBLE_API_KEY", "") or "").strip()
    except (TypeError, ValueError):
        api_key = ""
    if not api_key:
        return None
    base_url = getattr(tuning, "reranker_api_base_url", "")
    if not base_url:
        return None
    return RerankerClient(
        api_key=api_key,
        base_url=base_url,
        model=getattr(tuning, "reranker_model", "BAAI/bge-reranker-v2-m3"),
    )
