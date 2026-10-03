"""EvidenceRAGService.retrieve 缺失 embedding 判定的行为等价测试。

retrieve 由「整表物化后 Python 判空（not c.embedding）」改为
「DB 侧 embedding=[] 过滤 + values_list("id", "text") 轻字段」，
本文件用真实数据库验证两种口径在 embedding 取值约定（[] 或非空向量）下一致，
并验证 retrieve 只对缺失 embedding 的 chunk 触发向量化。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from apps.litigation_ai.models import EvidenceChunk


def _make_chunks(db: Any, case: Any) -> int:
    """构造 1 个证据条目：2 个无向量 chunk + 1 个有向量 chunk，返回 item id。"""
    from apps.evidence.models.evidence import EvidenceItem, EvidenceList

    elist = EvidenceList.objects.create(case=case, list_type="list_1", title="RAG 等价测试清单")
    item = EvidenceItem.objects.create(evidence_list=elist, order=1, name="证据1", purpose="证明")
    EvidenceChunk.objects.create(evidence_item=item, text="显式空向量", embedding=[])
    EvidenceChunk.objects.create(evidence_item=item, text="默认空向量")  # embedding 缺省为 []
    EvidenceChunk.objects.create(evidence_item=item, text="已有向量", embedding=[0.1, 0.2, 0.3])
    return item.id


class TestRetrieveMissingEmbeddingEquivalence:
    def test_db_filter_matches_python_truthiness(self, db: Any, case: Any) -> None:
        """DB 侧 embedding=[] 过滤与旧口径（物化后 not c.embedding）结果一致。"""
        item_id = _make_chunks(db, case)
        item_ids = [item_id]

        # 旧口径：整表物化（含大 embedding JSONField）后 Python 判空
        chunks = list(EvidenceChunk.objects.filter(evidence_item_id__in=item_ids))
        old_missing = sorted((c.id, c.text) for c in chunks if not c.embedding)

        # 新口径：DB 侧 embedding=[] 过滤 + 轻字段
        new_missing = sorted(
            EvidenceChunk.objects.filter(evidence_item_id__in=item_ids, embedding=[]).values_list("id", "text")
        )

        assert old_missing == new_missing
        assert len(new_missing) == 2
        assert {text for _, text in new_missing} == {"显式空向量", "默认空向量"}
        # 已有向量的 chunk 不在 missing 集合中
        present_ids = {
            c.id for c in EvidenceChunk.objects.filter(evidence_item_id__in=item_ids) if c.embedding
        }
        assert not present_ids & {row_id for row_id, _ in new_missing}

    def test_retrieve_upserts_only_missing_chunks(self, db: Any, case: Any) -> None:
        """retrieve 仅对缺 embedding 的 chunk 调 embed_texts / upsert_embeddings，顺序与 DB 行一致。"""
        from apps.litigation_ai.services.evidence import evidence_rag_service as rag_module
        from apps.litigation_ai.services.evidence.evidence_rag_service import EvidenceRAGService

        item_id = _make_chunks(db, case)

        expected_missing = list(
            EvidenceChunk.objects.filter(evidence_item_id__in=[item_id], embedding=[]).values_list("id", "text")
        )
        assert len(expected_missing) == 2

        fake_embed = MagicMock()
        fake_embed.embed_texts.side_effect = [[0.05], ["v1", "v2"]]
        fake_store = MagicMock()
        fake_store.search.return_value = []

        with (
            patch.object(rag_module, "EvidenceEmbeddingService", return_value=fake_embed),
            patch.object(rag_module, "EvidenceVectorStoreService", return_value=fake_store),
        ):
            result = EvidenceRAGService().retrieve("query", [item_id])

        assert result == []
        # 第一次调用：查询向量；第二次调用：仅缺失 chunk 的文本
        assert fake_embed.embed_texts.call_count == 2
        assert fake_embed.embed_texts.call_args_list[1].args == ([text for _, text in expected_missing],)
        fake_store.upsert_embeddings.assert_called_once_with([row_id for row_id, _ in expected_missing], ["v1", "v2"])
