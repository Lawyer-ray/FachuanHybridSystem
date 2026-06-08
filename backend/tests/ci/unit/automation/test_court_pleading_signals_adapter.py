"""Tests for apps/automation/services/litigation/court_pleading_signals_service_adapter.py."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


def _ensure_fake_dtos() -> None:
    """注入假的 dtos 模块，避免 from .dtos import CourtPleadingSignals 报错。"""
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


_ensure_fake_dtos()

# Now import the module — it will also try to import court_pleading_signals_service which
# needs the fake dtos too (already injected above).
from apps.automation.services.litigation.court_pleading_signals_service_adapter import (
    CourtPleadingSignalsServiceAdapter,
)


class TestCourtPleadingSignalsServiceAdapter:
    """CourtPleadingSignalsServiceAdapter.get_signals_internal 单元测试。"""

    def _make_adapter_with_mock_svc(self):
        """手动构建 adapter 实例，避免 __init__ 内部导入失败。"""
        adapter = CourtPleadingSignalsServiceAdapter.__new__(CourtPleadingSignalsServiceAdapter)
        mock_svc = MagicMock()
        adapter._svc = mock_svc
        return adapter, mock_svc

    def test_get_signals_internal_returns_dto(self) -> None:
        """返回 CourtPleadingSignalsDTO。"""
        adapter, mock_svc = self._make_adapter_with_mock_svc()

        signals = MagicMock()
        signals.has_complaint = True
        signals.has_defense = False
        signals.has_counterclaim = True
        signals.has_counterclaim_defense = False
        signals.notes = "test"
        mock_svc.get_signals.return_value = signals

        result = adapter.get_signals_internal(case_id=42)

        assert result.has_complaint is True
        assert result.has_defense is False
        assert result.has_counterclaim is True
        assert result.has_counterclaim_defense is False
        assert result.notes == "test"

    def test_get_signals_internal_bool_coercion(self) -> None:
        """getattr 返回的值被强制转换为 bool。"""
        adapter, mock_svc = self._make_adapter_with_mock_svc()

        signals = MagicMock()
        signals.has_complaint = 1
        signals.has_defense = 0
        signals.has_counterclaim = "yes"
        signals.has_counterclaim_defense = None
        signals.notes = ""
        mock_svc.get_signals.return_value = signals

        result = adapter.get_signals_internal(case_id=1)

        assert result.has_complaint is True
        assert result.has_defense is False
        assert result.has_counterclaim is True
        assert result.has_counterclaim_defense is False

    def test_get_signals_internal_notes_none_fallback(self) -> None:
        """notes 为 None 时回退为空字符串。"""
        adapter, mock_svc = self._make_adapter_with_mock_svc()

        signals = MagicMock()
        signals.has_complaint = False
        signals.has_defense = False
        signals.has_counterclaim = False
        signals.has_counterclaim_defense = False
        signals.notes = None
        mock_svc.get_signals.return_value = signals

        result = adapter.get_signals_internal(case_id=1)
        assert result.notes == ""

    def test_get_signals_internal_all_false(self) -> None:
        """所有信号均为 False 时也能正常返回。"""
        adapter, mock_svc = self._make_adapter_with_mock_svc()

        signals = MagicMock()
        signals.has_complaint = False
        signals.has_defense = False
        signals.has_counterclaim = False
        signals.has_counterclaim_defense = False
        signals.notes = ""
        mock_svc.get_signals.return_value = signals

        result = adapter.get_signals_internal(case_id=1)
        assert result.has_complaint is False
        assert result.has_defense is False
        assert result.has_counterclaim is False
        assert result.has_counterclaim_defense is False
