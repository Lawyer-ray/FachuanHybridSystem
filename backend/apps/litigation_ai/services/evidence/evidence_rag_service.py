"""Business logic services."""

from asgiref.sync import sync_to_async

from apps.litigation_ai.models import EvidenceChunk

from .evidence_embedding_service import EvidenceEmbeddingService
from .evidence_text_extraction_service import EvidenceTextExtractionService
from .evidence_vector_store_service import EvidenceVectorStoreService


class EvidenceRAGService:
    def ensure_ingested(self, evidence_item_ids: list[int], max_pages_per_item: int = 20) -> None:  # pragma: no cover
        from ..wiring import get_evidence_query_service

        extraction = EvidenceTextExtractionService()
        items = get_evidence_query_service().list_evidence_item_ids_with_files_internal(evidence_item_ids)
        for item in items:
            if not item.file_path:
                continue
            if EvidenceChunk.objects.filter(evidence_item_id=item.id).exists():
                continue
            chunks = extraction.extract_chunks(item.file_path, max_pages=max_pages_per_item)
            EvidenceChunk.objects.bulk_create(
                [
                    EvidenceChunk(
                        evidence_item_id=item.id,
                        page_start=c.get("page_start"),
                        page_end=c.get("page_end"),
                        text=c.get("text", ""),
                        extraction_method=c.get("extraction_method"),
                    )
                    for c in chunks
                ]
            )

    async def aensure_ingested(self, evidence_item_ids: list[int], max_pages_per_item: int = 20) -> None:  # pragma: no cover
        """异步版本 — 确保证据已入库.文件 I/O 通过 sync_to_async 卸载到线程池."""
        from ..wiring import get_evidence_query_service

        extraction = EvidenceTextExtractionService()
        items = await sync_to_async(get_evidence_query_service().list_evidence_item_ids_with_files_internal)(evidence_item_ids)
        for item in items:
            if not item.file_path:
                continue
            if await EvidenceChunk.objects.filter(evidence_item_id=item.id).aexists():
                continue
            chunks = await sync_to_async(extraction.extract_chunks)(item.file_path, max_pages=max_pages_per_item)
            await EvidenceChunk.objects.abulk_create(
                [
                    EvidenceChunk(
                        evidence_item_id=item.id,
                        page_start=c.get("page_start"),
                        page_end=c.get("page_end"),
                        text=c.get("text", ""),
                        extraction_method=c.get("extraction_method"),
                    )
                    for c in chunks
                ]
            )

    def retrieve(self, query: str, evidence_item_ids: list[int], top_k: int = 5) -> list[EvidenceChunk]:
        embedding_service = EvidenceEmbeddingService()
        store = EvidenceVectorStoreService()

        query_emb = embedding_service.embed_texts([query])[0]

        chunks = list(EvidenceChunk.objects.filter(evidence_item_id__in=evidence_item_ids))
        missing = [c for c in chunks if not c.embedding]
        if missing:
            embs = embedding_service.embed_texts([c.text for c in missing])
            store.upsert_embeddings([c.id for c in missing], embs)

        results = store.search(query_emb, evidence_item_ids=evidence_item_ids, top_k=top_k)
        return [chunk for chunk, _score in results if (chunk.text or "").strip()]

    async def aretrieve(self, query: str, evidence_item_ids: list[int], top_k: int = 5) -> list[EvidenceChunk]:
        """异步版本 — 检索相关证据片段."""
        embedding_service = EvidenceEmbeddingService()
        store = EvidenceVectorStoreService()

        query_emb = await sync_to_async(embedding_service.embed_texts)([query])
        query_vec = query_emb[0]

        chunks = [c async for c in EvidenceChunk.objects.filter(evidence_item_id__in=evidence_item_ids)]
        missing = [c for c in chunks if not c.embedding]
        if missing:
            embs = await sync_to_async(embedding_service.embed_texts)([c.text for c in missing])
            await sync_to_async(store.upsert_embeddings)([c.id for c in missing], embs)

        results = await sync_to_async(store.search)(query_vec, evidence_item_ids=evidence_item_ids, top_k=top_k)
        return [chunk for chunk, _score in results if (chunk.text or "").strip()]
