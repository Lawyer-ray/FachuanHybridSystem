"""Unit tests for EvidenceDigestService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestBuildEvidenceText:
    """Tests for build_evidence_text method."""

    @patch("apps.litigation_ai.services.evidence.evidence_digest_service.EvidenceDigestService.build_evidence_text")
    def test_build_evidence_text_called(self, mock_build):
        """Test that build_evidence_text is callable."""
        mock_build.return_value = ""
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
        svc = EvidenceDigestService()
        mock_build.return_value = "[证据#1] 1. test(证明：test，页码：-)"
        result = svc.build_evidence_text(evidence_list_ids=[1], evidence_item_ids=[2])
        assert result == "[证据#1] 1. test(证明：test，页码：-)"

    def test_build_evidence_text_returns_string(self):
        """Test that build_evidence_text returns a string."""
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
        # We cannot fully test without wiring, so just test the type
        svc = EvidenceDigestService()
        # The method calls wiring which may fail, so we test via mock
        with patch("apps.litigation_ai.services.wiring.get_evidence_query_service") as mock_svc:
            mock_svc.return_value.list_evidence_items_for_digest_internal.return_value = []
            result = svc.build_evidence_text(evidence_list_ids=[1], evidence_item_ids=[2])
            assert isinstance(result, str)
            assert result == ""


class TestBuildEvidenceTextWithItems:
    """Tests for build_evidence_text with actual mock items."""

    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_single_item(self, mock_get_svc):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        item = MagicMock()
        item.id = 1
        item.order = 1
        item.name = "合同原件"
        item.purpose = "证明合同关系"
        item.page_start = 1
        item.page_end = 3

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = [item]
        svc = EvidenceDigestService()
        result = svc.build_evidence_text(evidence_list_ids=[], evidence_item_ids=[1])
        assert "[证据#1]" in result
        assert "1. 合同原件" in result
        assert "证明：证明合同关系" in result
        assert "1-3" in result

    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_item_with_same_start_and_end_page(self, mock_get_svc):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        item = MagicMock()
        item.id = 5
        item.order = 2
        item.name = "单页证据"
        item.purpose = "证明付款"
        item.page_start = 7
        item.page_end = 7

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = [item]
        svc = EvidenceDigestService()
        result = svc.build_evidence_text(evidence_list_ids=[], evidence_item_ids=[5])
        assert "页码：7)" in result

    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_item_no_pages(self, mock_get_svc):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        item = MagicMock()
        item.id = 10
        item.order = 3
        item.name = "无页码证据"
        item.purpose = "证明其他"
        item.page_start = None
        item.page_end = None

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = [item]
        svc = EvidenceDigestService()
        result = svc.build_evidence_text(evidence_list_ids=[], evidence_item_ids=[10])
        assert "页码：-)" in result

    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_multiple_items(self, mock_get_svc):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        items = []
        for i in range(1, 4):
            item = MagicMock()
            item.id = i
            item.order = i
            item.name = f"证据{i}"
            item.purpose = f"证明{i}"
            item.page_start = i
            item.page_end = i + 1
            items.append(item)

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = items
        svc = EvidenceDigestService()
        result = svc.build_evidence_text(evidence_list_ids=[1], evidence_item_ids=[1, 2, 3])
        lines = result.strip().split("\n")
        assert len(lines) == 3


class TestSearchEvidenceForAgent:
    """Tests for search_evidence_for_agent method."""

    def test_empty_ids_returns_empty(self):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        svc = EvidenceDigestService()
        result = svc.search_evidence_for_agent("query", evidence_item_ids=[])
        assert result == []

    @patch("apps.litigation_ai.services.evidence.evidence_rag_service.EvidenceRAGService")
    def test_rag_service_used_when_available(self, mock_rag_cls):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        mock_rag = MagicMock()
        mock_rag_cls.return_value = mock_rag
        mock_chunk = MagicMock()
        mock_chunk.evidence_item_id = 1
        mock_chunk.text = "some text content"
        mock_chunk.page_start = 1
        mock_chunk.page_end = 2
        mock_chunk.evidence_item = MagicMock(name="证据A")
        mock_chunk.score = 0.9
        mock_rag.retrieve.return_value = [mock_chunk]

        svc = EvidenceDigestService()
        result = svc.search_evidence_for_agent("合同", evidence_item_ids=[1, 2])

        assert len(result) == 1
        assert result[0]["evidence_item_id"] == 1
        assert result[0]["relevance_score"] == 0.9
        mock_rag.ensure_ingested.assert_called_once_with([1, 2])
        mock_rag.retrieve.assert_called_once()

    @patch("apps.litigation_ai.models.EvidenceChunk")
    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    @patch(
        "apps.litigation_ai.services.evidence.evidence_rag_service.EvidenceRAGService",
        side_effect=ImportError("no rag"),
    )
    def test_falls_back_to_simple_search(self, mock_rag_cls, mock_get_svc, mock_chunk_cls):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = []
        svc = EvidenceDigestService()
        result = svc.search_evidence_for_agent("合同", evidence_item_ids=[1])
        assert result == []


class TestSimpleTextSearch:
    """Tests for _simple_text_search method — mock at model level."""

    def test_empty_query_returns_empty(self):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
        svc = EvidenceDigestService()
        result = svc._simple_text_search("", evidence_item_ids=[1])
        assert result == []

    @patch("apps.litigation_ai.models.EvidenceChunk")
    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_matching_text_found(self, mock_get_svc, mock_chunk_cls):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        mock_item = MagicMock()
        mock_item.id = 1
        mock_item.name = "合同"
        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = [mock_item]

        mock_chunk = MagicMock()
        mock_chunk.evidence_item_id = 1
        mock_chunk.text = "本合同约定甲方向乙方支付合同款项"
        mock_chunk_cls.objects.filter.return_value.order_by.return_value = [mock_chunk]

        svc = EvidenceDigestService()
        result = svc._simple_text_search("合同", evidence_item_ids=[1], top_k=5)
        assert len(result) == 1
        assert result[0]["evidence_item_id"] == 1
        assert result[0]["relevance_score"] == 0.3

    @patch("apps.litigation_ai.models.EvidenceChunk")
    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_no_match_returns_empty(self, mock_get_svc, mock_chunk_cls):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = []

        mock_chunk = MagicMock()
        mock_chunk.evidence_item_id = 1
        mock_chunk.text = "无关内容"
        mock_chunk_cls.objects.filter.return_value.order_by.return_value = [mock_chunk]

        svc = EvidenceDigestService()
        result = svc._simple_text_search("合同", evidence_item_ids=[1])
        assert result == []

    @patch("apps.litigation_ai.models.EvidenceChunk")
    @patch("apps.litigation_ai.services.wiring.get_evidence_query_service")
    def test_top_k_limits_results(self, mock_get_svc, mock_chunk_cls):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService

        mock_get_svc.return_value.list_evidence_items_for_digest_internal.return_value = []

        chunks = []
        for i in range(10):
            mc = MagicMock()
            mc.evidence_item_id = i
            mc.text = f"合同第{i}份"
            chunks.append(mc)
        mock_chunk_cls.objects.filter.return_value.order_by.return_value = chunks

        svc = EvidenceDigestService()
        result = svc._simple_text_search("合同", evidence_item_ids=list(range(10)), top_k=3)
        assert len(result) == 3
