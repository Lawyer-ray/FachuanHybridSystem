"""Business logic services."""

import math

from apps.litigation_ai.models import EvidenceChunk


class EvidenceVectorStoreService:
    def upsert_embeddings(self, chunk_ids: list[int], embeddings: list[list[float]]) -> None:
        for chunk_id, emb in zip(chunk_ids, embeddings, strict=False):
            EvidenceChunk.objects.filter(id=chunk_id).update(embedding=emb)

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def search(
        self,
        query_embedding: list[float],
        *,
        evidence_item_ids: list[int],
        top_k: int = 5,
    ) -> list[tuple[EvidenceChunk, float]]:
        qs = EvidenceChunk.objects.filter(evidence_item_id__in=evidence_item_ids)
        scored: list[tuple[EvidenceChunk, float]] = []
        for chunk in qs:
            score = self.cosine_similarity(query_embedding, chunk.embedding or [])
            scored.append((chunk, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
