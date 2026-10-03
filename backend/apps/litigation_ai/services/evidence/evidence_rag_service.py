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

    async def aensure_ingested(
        self, evidence_item_ids: list[int], max_pages_per_item: int = 20
    ) -> None:  # pragma: no cover
        """异步版本 — 确保证据已入库.文件 I/O 通过 sync_to_async 卸载到线程池."""
        from ..wiring import get_evidence_query_service

        extraction = EvidenceTextExtractionService()
        items = await sync_to_async(get_evidence_query_service().list_evidence_item_ids_with_files_internal)(
            evidence_item_ids
        )
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

        # 只物化轻字段（id/text）：embedding 是数十 KB 级 JSONField，原写法整表物化仅为
        # 判空。embedding 列 NOT NULL 且取值只会是 [] 或非空向量（upsert_embeddings 是
        # 唯一写入方），DB 侧 embedding=[] 与 Python not c.embedding 语义等价。
        missing_rows = list(
            EvidenceChunk.objects.filter(evidence_item_id__in=evidence_item_ids, embedding=[]).values_list("id", "text")
        )
        if missing_rows:
            missing_ids = [row[0] for row in missing_rows]
            embs = embedding_service.embed_texts([row[1] for row in missing_rows])
            store.upsert_embeddings(missing_ids, embs)

        results = store.search(query_emb, evidence_item_ids=evidence_item_ids, top_k=top_k)
        return [chunk for chunk, _score in results if (chunk.text or "").strip()]

    async def aretrieve(self, query: str, evidence_item_ids: list[int], top_k: int = 5) -> list[EvidenceChunk]:
        """异步版本 — 检索相关证据片段."""
        embedding_service = EvidenceEmbeddingService()
        store = EvidenceVectorStoreService()

        query_emb = await sync_to_async(embedding_service.embed_texts)([query])
        query_vec = query_emb[0]

        # 同步版 retrieve：只物化轻字段（id/text），避免整表物化大 embedding JSONField。
        missing_rows = [
            row
            async for row in EvidenceChunk.objects.filter(
                evidence_item_id__in=evidence_item_ids, embedding=[]
            ).values_list("id", "text")
        ]
        if missing_rows:
            missing_ids = [row[0] for row in missing_rows]
            embs = await sync_to_async(embedding_service.embed_texts)([row[1] for row in missing_rows])
            await sync_to_async(store.upsert_embeddings)(missing_ids, embs)

        results = await sync_to_async(store.search)(query_vec, evidence_item_ids=evidence_item_ids, top_k=top_k)
        return [chunk for chunk, _score in results if (chunk.text or "").strip()]
