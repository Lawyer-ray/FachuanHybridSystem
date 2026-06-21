"""Tests for history_recorder — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from plugins.court_automation.token.history_recorder import TokenHistoryRecorder


class TestTokenHistoryRecorderInit:
    def test_default_db_service(self) -> None:
        recorder = TokenHistoryRecorder()
        assert recorder.db_service is not None

    def test_injected_db_service(self) -> None:
        mock_svc = MagicMock()
        recorder = TokenHistoryRecorder(db_service=mock_svc)
        assert recorder.db_service is mock_svc


@pytest.mark.asyncio
class TestGetRecentStatistics:
    async def test_exception_returns_empty(self) -> None:
        recorder = TokenHistoryRecorder()
        with patch("plugins.court_automation.token.history_recorder.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = await recorder.get_recent_statistics(site_name="court")
            assert result["total_acquisitions"] == 0
            assert result["success_rate"] == 0

    async def test_no_filter(self) -> None:
        recorder = TokenHistoryRecorder()
        with patch("plugins.court_automation.token.history_recorder.TokenAcquisitionHistory") as mock_hist:
            mock_qs = MagicMock()
            mock_qs.count.return_value = 5
            mock_hist.objects.filter.return_value = mock_qs
            result = await recorder.get_recent_statistics(site_name=None)
            assert result["period_hours"] == 24

    async def test_with_filter(self) -> None:
        recorder = TokenHistoryRecorder()
        with patch("plugins.court_automation.token.history_recorder.TokenAcquisitionHistory") as mock_hist:
            mock_qs = MagicMock()
            mock_qs.count.return_value = 3
            mock_hist.objects.filter.return_value = mock_qs
            result = await recorder.get_recent_statistics(site_name="court", hours=48)
            assert result["period_hours"] == 48


@pytest.mark.asyncio
class TestGetAccountPerformance:
    async def test_exception_returns_empty(self) -> None:
        recorder = TokenHistoryRecorder()
        with patch("plugins.court_automation.token.history_recorder.TokenAcquisitionHistory") as mock_hist:
            mock_hist.objects.filter.side_effect = Exception("db error")
            result = await recorder.get_account_performance("test@test.com", "court")
            assert result["total_attempts"] == 0

    async def test_success(self) -> None:
        recorder = TokenHistoryRecorder()
        with patch("plugins.court_automation.token.history_recorder.TokenAcquisitionHistory") as mock_hist:
            mock_qs = MagicMock()
            mock_qs.count.return_value = 10
            mock_hist.objects.filter.return_value = mock_qs
            result = await recorder.get_account_performance("test@test.com", "court", days=7)
            assert result["account"] == "test@test.com"
            assert result["site_name"] == "court"
