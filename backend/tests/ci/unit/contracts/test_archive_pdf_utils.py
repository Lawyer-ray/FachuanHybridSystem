"""
Unit tests for contracts/services/archive/generation/pdf_utils.py.

Covers:
  - Constants (A4 dimensions, tolerance)
  - scale_pages_to_a4 (no materials path)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.generation.pdf_utils import (
    A4_H,
    A4_W,
    TOLERANCE,
)


class TestConstants:
    def test_a4_dimensions(self) -> None:
        assert A4_W == 595.0
        assert A4_H == 842.0

    def test_tolerance(self) -> None:
        assert TOLERANCE == 1.0


class TestScalePagesToA4:
    def test_no_materials(self) -> None:
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4

        contract = MagicMock()
        contract.id = 1
        with patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value = []
            result = scale_pages_to_a4(contract)
        assert result["success"] is True
        assert result["scaled_count"] == 0


class TestAddPageNumbers:
    def test_function_callable(self) -> None:
        """Verify add_page_numbers function exists and is callable."""
        from apps.contracts.services.archive.generation.pdf_utils import add_page_numbers
        assert callable(add_page_numbers)
