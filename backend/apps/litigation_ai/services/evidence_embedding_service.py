"""Business logic services."""

import hashlib
import logging
import math

import openai

from apps.core.llm.config import LLMConfig

logger = logging.getLogger("apps.litigation_ai")


class EvidenceEmbeddingService:
    def embed_texts(self, texts: list[str], dims: int = 256) -> list[list[float]]:
        api_key = LLMConfig.get_api_key()
        if api_key:
            try:
                return self._embed_with_openai_compatible(texts)
            except Exception:
                logger.warning("在线向量化失败，回退本地哈希向量", exc_info=True)
        return [self._hash_embed(t, dims=dims) for t in texts]

    def _embed_with_openai_compatible(self, texts: list[str]) -> list[list[float]]:
        api_key = LLMConfig.get_api_key() or ""
        client = openai.OpenAI(
            api_key=api_key,
            base_url=LLMConfig.get_base_url(),
            timeout=LLMConfig.get_timeout(),
        )
        model = LLMConfig.get_default_model()
        resp = client.embeddings.create(model=model, input=texts)
        return [list(map(float, item.embedding or [])) for item in resp.data]

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
