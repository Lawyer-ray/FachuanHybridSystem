"""Tests for evidence services."""

import pytest
from unittest.mock import MagicMock, patch


class TestEvidencePageRangeCalculator:
    @patch("apps.documents.services.evidence.page_range_calculator.EvidenceItem")
    def test_calculate_page_ranges(self, mock_model):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()

        evidence_list = MagicMock()
        evidence_list.start_page = 1

        item1 = MagicMock()
        item1.page_count = 3
        item2 = MagicMock()
        item2.page_count = 2

        evidence_list.items.filter.return_value.order_by.return_value = [item1, item2]

        calculator.calculate_page_ranges(evidence_list=evidence_list)

        assert item1.page_start == 1
        assert item1.page_end == 3
        assert item2.page_start == 4
        assert item2.page_end == 5

    @patch("apps.documents.services.evidence.page_range_calculator.EvidenceItem")
    def test_calculate_empty_list(self, mock_model):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()

        evidence_list = MagicMock()
        evidence_list.start_page = 1
        evidence_list.items.filter.return_value.order_by.return_value = []

        calculator.calculate_page_ranges(evidence_list=evidence_list)
        assert evidence_list.total_pages == 0

    @patch("apps.documents.services.evidence.page_range_calculator.EvidenceItem")
    def test_calculate_with_zero_page_count(self, mock_model):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()

        evidence_list = MagicMock()
        evidence_list.start_page = 1

        item1 = MagicMock()
        item1.page_count = 0
        item2 = MagicMock()
        item2.page_count = 5

        evidence_list.items.filter.return_value.order_by.return_value = [item1, item2]

        calculator.calculate_page_ranges(evidence_list=evidence_list)

        assert item2.page_start == 1
        assert item2.page_end == 5

    @patch("apps.documents.services.evidence.page_range_calculator.EvidenceItem")
    def test_custom_start_page(self, mock_model):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()

        evidence_list = MagicMock()
        evidence_list.start_page = 10

        item1 = MagicMock()
        item1.page_count = 2

        evidence_list.items.filter.return_value.order_by.return_value = [item1]

        calculator.calculate_page_ranges(evidence_list=evidence_list)

        assert item1.page_start == 10
        assert item1.page_end == 11


class TestEvidenceQueryService:
    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_empty(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        service = EvidenceQueryService()
        result = service._build_dtos([])
        assert result == []

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_with_items(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        service = EvidenceQueryService()

        mock_field = MagicMock()
        mock_field.storage.path.side_effect = lambda x: f"/media/{x}"
        mock_model._meta.get_field.return_value = mock_field

        items = [
            {
                "id": 1,
                "order": 1,
                "name": "证据1",
                "purpose": "证明借贷关系",
                "page_start": 1,
                "page_end": 3,
                "file": "path/to/file.pdf",
            },
            {
                "id": 2,
                "order": 2,
                "name": "证据2",
                "purpose": "证明转账",
                "page_start": 4,
                "page_end": 5,
                "file": None,
            },
        ]
        result = service._build_dtos(items)
        assert len(result) == 2
        assert result[0].name == "证据1"
        assert result[1].name == "证据2"
        assert result[1].file_path is None

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_build_dtos_file_path_error(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        service = EvidenceQueryService()

        mock_field = MagicMock()
        mock_field.storage.path.side_effect = Exception("storage error")
        mock_model._meta.get_field.return_value = mock_field

        items = [{"id": 1, "order": 1, "name": "test", "purpose": "", "page_start": 1, "page_end": 1, "file": "bad"}]
        result = service._build_dtos(items)
        assert len(result) == 1
        assert result[0].file_path is None

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_list_evidence_items_empty_ids(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        service = EvidenceQueryService()
        result = service.list_evidence_items_for_digest_internal([], [])
        assert result == []

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_list_evidence_item_ids_with_files_empty(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        service = EvidenceQueryService()
        result = service.list_evidence_item_ids_with_files_internal([])
        assert result == []

    @patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem")
    def test_list_evidence_items_for_case_empty(self, mock_model):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        mock_model.objects.filter.return_value.order_by.return_value.values.return_value = []
        service = EvidenceQueryService()
        result = service.list_evidence_items_for_case_internal(999)
        assert result == []
