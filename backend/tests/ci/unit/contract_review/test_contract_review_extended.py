"""Extended tests for contract_review services - format_service, format_normalizer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestContractFormatService:
    """Test ContractFormatService methods."""

    @patch("apps.contract_review.services.contract_format_service.get_poi_client")
    def test_determine_method_force_poi(self, mock_get_client):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = ContractFormatService()
        assert service._determine_method("poi") == "poi"

    @patch("apps.contract_review.services.contract_format_service.get_poi_client")
    def test_determine_method_force_python(self, mock_get_client):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        service = ContractFormatService()
        assert service._determine_method("python") == "python"

    @patch("apps.contract_review.services.contract_format_service.get_poi_client")
    def test_determine_method_auto_poi_available(self, mock_get_client):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_get_client.return_value = mock_client
        service = ContractFormatService()
        assert service._determine_method(None) == "poi"

    @patch("apps.contract_review.services.contract_format_service.get_poi_client")
    def test_determine_method_auto_poi_unavailable(self, mock_get_client):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        mock_client = MagicMock()
        mock_client.health_check.return_value = False
        mock_get_client.return_value = mock_client
        service = ContractFormatService()
        assert service._determine_method(None) == "python"

    @patch("apps.contract_review.services.contract_format_service.get_poi_client")
    def test_determine_method_auto_explicit(self, mock_get_client):
        from apps.contract_review.services.contract_format_service import ContractFormatService

        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_get_client.return_value = mock_client
        service = ContractFormatService()
        assert service._determine_method("auto") == "poi"


class TestDocxFormatNormalizer:
    """Test DocxFormatNormalizer import."""

    def test_import(self):
        from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

        assert DocxFormatNormalizer is not None


class TestContractReviewWiring:
    """Test wiring module import."""

    def test_import_wiring(self):
        from apps.contract_review.services import wiring

        assert wiring is not None


class TestContractReviewExceptions:
    """Test exceptions module."""

    def test_import_exceptions(self):
        from apps.contract_review.services import exceptions

        assert exceptions is not None
