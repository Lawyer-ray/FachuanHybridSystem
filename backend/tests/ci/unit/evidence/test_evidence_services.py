"""
Tests for apps.evidence.services — 证据服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestEvidencePageRangeCalculator:
    """EvidencePageRangeCalculator 测试"""

    def test_calculator_importable(self) -> None:
        from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator

        assert EvidencePageRangeCalculator is not None

    def test_calculator_instantiation(self) -> None:
        from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator

        calc = EvidencePageRangeCalculator()
        assert hasattr(calc, 'calculate_page_ranges')
        assert hasattr(calc, 'recalculate_page_ranges_for_chain')
        assert hasattr(calc, 'update_subsequent_lists_pages')


class TestEvidenceModules:
    """证据服务模块可导入性测试"""

    def test_evidence_storage_importable(self) -> None:
        from apps.evidence.services.core import evidence_storage

        assert evidence_storage is not None

    def test_evidence_file_service_importable(self) -> None:
        from apps.evidence.services.core import evidence_file_service

        assert evidence_file_service is not None

    def test_evidence_query_service_importable(self) -> None:
        from apps.evidence.services.core import evidence_query_service

        assert evidence_query_service is not None

    def test_evidence_service_importable(self) -> None:
        from apps.evidence.services.core import evidence_service

        assert evidence_service is not None

    def test_evidence_mutation_service_importable(self) -> None:
        from apps.evidence.services.mutation import evidence_mutation_service

        assert evidence_mutation_service is not None

    def test_evidence_merge_usecase_importable(self) -> None:
        from apps.evidence.services.mutation import evidence_merge_usecase

        assert evidence_merge_usecase is not None

    def test_evidence_admin_service_importable(self) -> None:
        from apps.evidence.services.admin import evidence_admin_service

        assert evidence_admin_service is not None

    def test_wiring_importable(self) -> None:
        from apps.evidence.services import wiring

        assert wiring is not None
