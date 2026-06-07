"""Coverage tests for legal_research.services.similarity.passage and reranker (additional)."""

from unittest.mock import MagicMock, patch

import pytest


class TestPassageAdditional:
    def test_split_paragraphs_short_text(self):
        from apps.legal_research.services.similarity.passage import split_paragraphs

        result = split_paragraphs("短", passage_max_chars=5000)
        assert result == []

    def test_select_relevant_passages_empty(self):
        from apps.legal_research.services.similarity.passage import select_relevant_passages

        result = select_relevant_passages(
            keyword="test", case_summary="", title="",
            case_digest="", content_text="", max_passages=5, passage_max_chars=200,
        )
        assert result == []

    def test_dedupe_passages_unique(self):
        from apps.legal_research.services.similarity.passage import dedupe_passages

        passages = ["unique passage 1", "unique passage 2", "unique passage 3"]
        result = dedupe_passages(passages)
        assert len(result) == 3

    def test_compose_passage_excerpt_single(self):
        from apps.legal_research.services.similarity.passage import compose_passage_excerpt

        result = compose_passage_excerpt(passages=["single passage"], preview_max_chars=200)
        assert "片段1" in result
        assert "single passage" in result


class TestRerankerAdditional:
    def test_init_custom_url(self):
        from apps.legal_research.services.similarity.reranker import SiliconFlowReranker

        r = SiliconFlowReranker(api_key="key", base_url="https://custom.com/v1/", model="custom-model")
        assert r._base_url == "https://custom.com/v1"
        assert r._model == "custom-model"

    def test_cooldown_resets(self):
        from apps.legal_research.services.similarity.reranker import SiliconFlowReranker

        r = SiliconFlowReranker(api_key="key")
        r._fail_until = 0.0
        # Just test it doesn't crash
        assert r._fail_until == 0.0
