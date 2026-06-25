"""Tests for async reconciler parse/reconcile methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.evidence_sorting.services.reconciler import ReconcilerService


@pytest.mark.asyncio
class TestParseStatementAsync:
    async def test_valid_llm_json_response(self):
        svc = ReconcilerService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"month": "2022-08", "total_amount": 50000, "signed": true, "line_items": [{"date": "20220815", "amount": 50000, "description": "test"}]}'
        mock_llm.achat = AsyncMock(return_value=mock_response)

        with patch("apps.core.llm.get_llm_service", return_value=mock_llm):
            result = await svc.parse_statement_async("对账单 2022年8月 ¥50000")

        assert result.month == "2022-08"
        assert result.total_amount == 50000.0
        assert result.signed is True
        assert len(result.line_items) == 1
        assert result.line_items[0].date == "20220815"

    async def test_llm_error_returns_empty_statement(self):
        svc = ReconcilerService()
        mock_llm = MagicMock()
        mock_llm.achat = AsyncMock(side_effect=Exception("LLM down"))

        with patch("apps.core.llm.get_llm_service", return_value=mock_llm):
            result = await svc.parse_statement_async("text")

        assert result.month == ""
        assert result.total_amount is None

    async def test_llm_json_in_markdown_block(self):
        svc = ReconcilerService()
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n{"month": "2023-01", "total_amount": 100, "signed": false, "line_items": []}\n```'
        mock_llm.achat = AsyncMock(return_value=mock_response)

        with patch("apps.core.llm.get_llm_service", return_value=mock_llm):
            result = await svc.parse_statement_async("text")

        assert result.month == "2023-01"
        assert result.signed is False
        assert result.line_items == []


@pytest.mark.asyncio
class TestReconcileAsync:
    async def test_concurrent_statement_parsing(self):
        """Multiple statements should be parsed concurrently via asyncio.gather."""
        svc = ReconcilerService()
        parse_order: list[str] = []

        async def fake_parse(text, backend=None, model=None):
            parse_order.append(text)
            from apps.evidence_sorting.services.reconciler import StatementInfo
            return StatementInfo(month="2022-08", total_amount=100, signed=True)

        svc.parse_statement_async = fake_parse  # type: ignore[assignment]

        statements = [
            {"ocr_text": "stmt1"},
            {"ocr_text": "stmt2"},
            {"ocr_text": "stmt3"},
        ]

        result = await svc.reconcile_async(
            statements=statements,
            deliveries=[],
            receipts=[],
            others=[],
        )

        assert len(parse_order) == 3
        assert set(parse_order) == {"stmt1", "stmt2", "stmt3"}

    async def test_empty_inputs(self):
        """Empty inputs should return empty result."""
        svc = ReconcilerService()
        result = await svc.reconcile_async(
            statements=[],
            deliveries=[],
            receipts=[],
            others=[],
        )
        assert len(result.month_groups) == 0
        assert len(result.unmatched_deliveries) == 0
