"""Tests for apps/automation/services/litigation/court_pleading_signals_service.py."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


def _ensure_fake_dtos() -> None:
    """注入一个假的 apps.automation.services.litigation.dtos 模块，
    因为源码中 from .dtos import CourtPleadingSignals 实际指向不存在的文件。"""
    mod_name = "apps.automation.services.litigation.dtos"
    if mod_name not in sys.modules:
        mod = types.ModuleType(mod_name)

        @dataclass(frozen=True)
        class CourtPleadingSignals:
            has_complaint: bool = False
            has_defense: bool = False
            has_counterclaim: bool = False
            has_counterclaim_defense: bool = False
            notes: str = ""

        mod.CourtPleadingSignals = CourtPleadingSignals  # type: ignore[attr-defined]
        sys.modules[mod_name] = mod


# Ensure the fake module is available before importing the service
_ensure_fake_dtos()

from apps.automation.services.litigation.court_pleading_signals_service import (
    CourtPleadingSignalsService,
)


class TestCourtPleadingSignalsService:
    """CourtPleadingSignalsService 单元测试。"""

    def _make_service(self, model: str | None = None) -> CourtPleadingSignalsService:
        return CourtPleadingSignalsService(model=model)

    def test_default_prompt_not_empty(self) -> None:
        """_default_prompt() 返回非空字符串。"""
        svc = self._make_service()
        prompt = svc._default_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "起诉状" in prompt

    def test_get_prompt_template_returns_none(self) -> None:
        """_get_prompt_template() 始终返回 None。"""
        svc = self._make_service()
        assert svc._get_prompt_template() is None

    def test_fallback_by_keywords_complaint(self) -> None:
        """关键词 '起诉状' => has_complaint=True。"""
        svc = self._make_service()
        result = svc._fallback_by_keywords(["民事起诉状"])
        assert result.has_complaint is True
        assert result.has_defense is False
        assert result.has_counterclaim is False
        assert result.notes == "fallback_keywords"

    def test_fallback_by_keywords_defense(self) -> None:
        """关键词 '答辩状' => has_defense=True。"""
        svc = self._make_service()
        result = svc._fallback_by_keywords(["民事答辩状"])
        assert result.has_defense is True
        assert result.has_complaint is False

    def test_fallback_by_keywords_counterclaim(self) -> None:
        """关键词 '反诉状' => has_counterclaim=True。"""
        svc = self._make_service()
        result = svc._fallback_by_keywords(["反诉状"])
        assert result.has_counterclaim is True

    def test_fallback_by_keywords_counterclaim_defense(self) -> None:
        """关键词 '反诉答辩状' => has_counterclaim_defense=True。"""
        svc = self._make_service()
        result = svc._fallback_by_keywords(["反诉答辩状"])
        assert result.has_counterclaim_defense is True

    def test_fallback_by_keywords_empty_list(self) -> None:
        """空列表 => 所有字段均为 False。"""
        svc = self._make_service()
        result = svc._fallback_by_keywords([])
        assert result.has_complaint is False
        assert result.has_defense is False
        assert result.has_counterclaim is False
        assert result.has_counterclaim_defense is False

    def test_get_signals_empty_docs_returns_default(self) -> None:
        """无文书名称时返回默认的空 CourtPleadingSignals。"""
        svc = self._make_service()
        with patch.object(svc, "_get_case_court_document_names", return_value=[]):
            result = svc.get_signals(case_id=123)
            assert result.has_complaint is False
            assert result.has_defense is False

    def test_get_signals_uses_llm_when_docs_exist(self) -> None:
        """有文书时调用 _classify_with_llm。"""
        svc = self._make_service()
        expected = MagicMock()
        with patch.object(svc, "_get_case_court_document_names", return_value=["起诉状"]):
            with patch.object(svc, "_classify_with_llm", return_value=expected) as mock_llm:
                result = svc.get_signals(case_id=1)
                assert result is expected
                mock_llm.assert_called_once()

    def test_get_signals_fallback_on_llm_failure(self) -> None:
        """LLM 调用失败时回退到关键词规则。"""
        svc = self._make_service()
        with patch.object(svc, "_get_case_court_document_names", return_value=["起诉状"]):
            with patch.object(svc, "_classify_with_llm", side_effect=RuntimeError("LLM down")):
                result = svc.get_signals(case_id=1)
                assert result.has_complaint is True
                assert result.notes == "fallback_keywords"
