"""Tests for plugins.court_automation.preservation_quote.service_adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.preservation_quote.service_adapter import (
    EnhancedPreservationQuoteService,
    PreservationQuoteServiceAdapter,
)


class TestPreservationQuoteServiceAdapter:
    """Test adapter instantiation and lazy-loading properties."""

    def test_inject_all_deps(self) -> None:
        mock_token = MagicMock()
        mock_client = MagicMock()
        mock_auto = MagicMock()
        adapter = PreservationQuoteServiceAdapter(
            token_service=mock_token,
            insurance_client=mock_client,
            auto_token_service=mock_auto,
        )
        assert adapter.token_service is mock_token
        assert adapter.insurance_client is mock_client
        assert adapter.auto_token_service is mock_auto

    def test_lazy_service_creation(self) -> None:
        mock_token = MagicMock()
        mock_client = MagicMock()
        mock_auto = MagicMock()
        adapter = PreservationQuoteServiceAdapter(
            token_service=mock_token,
            insurance_client=mock_client,
            auto_token_service=mock_auto,
        )
        service = adapter.service
        assert service is not None
        # Calling again returns the same instance
        assert adapter.service is service

    def test_create_quote_delegates(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._token_service = MagicMock()
        adapter._insurance_client = MagicMock()
        adapter._auto_token_service = MagicMock()
        adapter._service = MagicMock()
        adapter._service.create_quote.return_value = "quote_result"

        result = adapter.create_quote(
            case_name="测试案件",
            target_amount=100000,
            applicant_name="申请人",
            respondent_name="被申请人",
            court_name="佛山法院",
        )
        assert result == "quote_result"
        adapter._service.create_quote.assert_called_once()

    def test_get_quote_by_id_delegates(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.get_quote.return_value = "quote_data"

        result = adapter.get_quote_by_id(42)
        assert result == "quote_data"
        adapter._service.get_quote.assert_called_once_with(42)

    def test_get_quote_alias(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.get_quote.return_value = "data"
        result = adapter.get_quote(99)
        assert result == "data"

    def test_list_quotes_with_page(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.list_quotes.return_value = (["q1", "q2"], 2)

        result = adapter.list_quotes(page=2, page_size=10)
        assert result["page"] == 2
        assert result["page_size"] == 10
        assert result["quotes"] == ["q1", "q2"]
        assert result["total"] == 2
        adapter._service.list_quotes.assert_called_once_with(2, 10, None)

    def test_list_quotes_fallback_from_offset(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.list_quotes.return_value = ([], 0)

        result = adapter.list_quotes(limit=20, offset=40)
        assert result["page"] == 3  # (40 // 20) + 1
        assert result["page_size"] == 20

    def test_create_quote_internal_calls_create_quote(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.create_quote.return_value = "ok"

        result = adapter.create_quote_internal(
            case_name="c", target_amount=1, applicant_name="a", respondent_name="r", court_name="crt"
        )
        assert result == "ok"

    def test_execute_quote_internal_delegates(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._token_service = MagicMock()
        # execute_quote calls asyncio.run; mock it
        with patch("asyncio.run", return_value={"status": "ok"}):
            result = adapter.execute_quote_internal(1)
            assert result == {"status": "ok"}

    def test_get_quote_by_id_internal(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.get_quote.return_value = "ok"
        assert adapter.get_quote_by_id_internal(1) == "ok"

    def test_list_quotes_internal(self) -> None:
        adapter = PreservationQuoteServiceAdapter.__new__(PreservationQuoteServiceAdapter)
        adapter._service = MagicMock()
        adapter._service.list_quotes.return_value = ([], 0)
        result = adapter.list_quotes_internal(page=1, page_size=5)
        assert result["page"] == 1
