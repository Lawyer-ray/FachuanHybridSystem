"""Business logic services."""

import hashlib
import math

from apps.core.llm.config import LLMConfig


class EvidenceEmbeddingService:
    def embed_texts(self, texts: list[str], dims: int = 256) -> list[list[float]]:
        api_key = LLMConfig.get_api_key()
        if api_key:
            return self._embed_with_openai_compatible(texts)
        return [self._hash_embed(t, dims=dims) for t in texts]

    def _embed_with_openai_compatible(self, texts: list[str]) -> list[list[float]]:
        from langchain_openai import OpenAIEmbeddings

        api_key = LLMConfig.get_api_key() or ""
        embeddings = OpenAIEmbeddings(
            api_key=api_key,  # type: ignore[arg-type]
            base_url=LLMConfig.get_base_url(),
            timeout=LLMConfig.get_timeout(),
        )
        return embeddings.embed_documents(texts)

    def _hash_embed(self, text: str, dims: int = 256) -> list[float]:
        vec = [0.0] * dims
        tokens = [t for t in (text or "").split() if t]
        if not tokens:
            return vec
        for tok in tokens:
            h = hashlib.md5(tok.encode("utf-8")).hexdigest()
            idx = int(h[:8], 16) % dims
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
