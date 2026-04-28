"""Business logic services."""

import hashlib
import logging
import math
from typing import Any

from apps.core.interfaces import ServiceLocator

logger = logging.getLogger("apps.litigation_ai")


class EvidenceEmbeddingService:
    def __init__(self, llm_service: Any | None = None) -> None:
        self._llm_service = llm_service

    @property
    def llm_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = ServiceLocator.get_llm_service()
        return self._llm_service

    def embed_texts(self, texts: list[str], dims: int = 256) -> list[list[float]]:
        if not texts:
            return []
        try:
            return self.llm_service.embed_texts(texts=texts, backend="siliconflow", fallback=False)  # type: ignore[no-any-return]
        except Exception:
            logger.warning("在线向量化失败，回退本地哈希向量", exc_info=True)
        return [self._hash_embed(t, dims=dims) for t in texts]

    def _hash_embed(self, text: str, dims: int = 256) -> list[float]:
        vec = [0.0] * dims
        tokens = [t for t in (text or "").split() if t]
        if not tokens:
            return vec
        for tok in tokens:
            h = hashlib.md5(tok.encode("utf-8"), usedforsecurity=False).hexdigest()
            idx = int(h[:8], 16) % dims
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
