"""Tests for evidence access policy, document recognition helpers, and other pure-logic modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


class TestInferCaseSideContext:
    """Test _infer_case_side with context party names."""

    def test_our_party_name_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="原告张三的委托书",
            context={"our_party_names": ["张三"]},
        )
        assert result == "our"

    def test_opponent_party_name_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="被告李四的身份证",
            context={"opponent_party_names": ["李四"]},
        )
        assert result == "opponent"

    def test_both_names_in_context(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="原告张三与被告李四",
            context={
                "our_party_names": ["张三"],
                "opponent_party_names": ["李四"],
            },
        )
        assert result == "unknown"
