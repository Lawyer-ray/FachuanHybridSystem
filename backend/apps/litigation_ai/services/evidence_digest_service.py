"""
证据摘要服务

提供证据文本构建和 RAG 检索功能.

Requirements: 2.3, 4.1, 4.3, 4.4
"""

import logging
from typing import Any

logger = logging.getLogger("apps.litigation_ai")


class EvidenceDigestService:
    """
    证据摘要服务

    负责构建证据文本摘要和执行 RAG 检索.
    """

    def build_evidence_text(self, evidence_list_ids: list[int], evidence_item_ids: list[int]) -> str:
        """
        构建证据文本摘要

        Args:
            evidence_list_ids: 证据清单 ID 列表
            evidence_item_ids: 证据项 ID 列表

        Returns:
            格式化的证据文本
        """
        from .wiring import get_evidence_query_service

        items = get_evidence_query_service().list_evidence_items_for_digest_internal(
            evidence_list_ids=evidence_list_ids,
            evidence_item_ids=evidence_item_ids,
        )
        lines = []
        for item in items:
            page_start = item.page_start
            page_end = item.page_end
            if page_start and page_end:
                page_range = f"{page_start}-{page_end}" if page_start != page_end else str(page_start)
            else:
                page_range = "-"
            lines.append(f"[证据#{item.id}] {item.order}. {item.name}(证明：{item.purpose}，页码：{page_range})")
        return "\n".join(lines)

    def search_evidence_for_agent(
        self,
        query: str,
        evidence_item_ids: list[int],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        在指定证据中检索相关内容(供 Agent 工具调用)

        使用 RAG 检索在证据内容中查找与查询相关的片段.

        Args:
            query: 检索查询文本
            evidence_item_ids: 要检索的证据项 ID 列表
            top_k: 返回结果数量

        Returns:
            相关证据片段列表,每项包含:
            - evidence_item_id: 证据项 ID
            - text: 检索到的文本片段
            - page_start: 起始页码
            - page_end: 结束页码
            - source_name: 证据来源名称
            - relevance_score: 相关性分数
        """
        if not evidence_item_ids:
            return []

        try:
            # 尝试使用 RAG 服务
            from .evidence_rag_service import EvidenceRAGService

            rag_service = EvidenceRAGService()

            # 确保证据已被索引
            rag_service.ensure_ingested(evidence_item_ids)

            # 执行检索
            chunks = rag_service.retrieve(query, evidence_item_ids, top_k)

            results: list[Any] = []
            for chunk in chunks:
                results.append(
                    {
                        "evidence_item_id": chunk.evidence_item_id,
                        "text": chunk.text[:500] if chunk.text else "",  # 限制长度
                        "page_start": getattr(chunk, "page_start", None),
                        "page_end": getattr(chunk, "page_end", None),
                        "source_name": (
                            getattr(chunk.evidence_item, "name", "") if hasattr(chunk, "evidence_item") else ""
                        ),
                        "relevance_score": getattr(chunk, "score", 0.0),
                    }
                )

            return results

        except ImportError:
            logger.warning("RAG 服务不可用,使用简单文本匹配")
            return self._simple_text_search(query, evidence_item_ids, top_k)
        except Exception as e:
            logger.error(f"RAG 检索失败: {e}")
            return self._simple_text_search(query, evidence_item_ids, top_k)

    def _simple_text_search(
        self,
        query: str,
        evidence_item_ids: list[int],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        简单文本搜索(RAG 不可用时的回退方案)

        Args:
            query: 检索查询文本
            evidence_item_ids: 要检索的证据项 ID 列表
            top_k: 返回结果数量

        Returns:
            匹配的证据片段列表
        """
        from apps.litigation_ai.models import EvidenceChunk

        from .wiring import get_evidence_query_service

        query_lower = (query or "").lower()
        if not query_lower:
            return []

        id_to_name = {
            item.id: item.name
            for item in get_evidence_query_service().list_evidence_items_for_digest_internal(
                evidence_list_ids=[],
                evidence_item_ids=evidence_item_ids,
            )
        }

        results: list[dict[str, Any]] = []
        chunks = EvidenceChunk.objects.filter(evidence_item_id__in=evidence_item_ids).order_by("evidence_item_id", "id")
        for chunk in chunks:
            text = chunk.text or ""
            if query_lower not in text.lower():
                continue

            idx = text.lower().find(query_lower)
            start = max(0, idx - 100)
            end = min(len(text), idx + len(query_lower) + 100)
            snippet = text[start:end]

            results.append(
                {
                    "evidence_item_id": chunk.evidence_item_id,
                    "text": f"...{snippet}...",
                    "page_start": getattr(chunk, "page_start", None),
                    "page_end": getattr(chunk, "page_end", None),
                    "source_name": id_to_name.get(chunk.evidence_item_id, ""),
                    "relevance_score": 0.3,
                }
            )

            if len(results) >= top_k:
                break

        return results
