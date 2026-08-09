"""Extended tests for contract_review services - format_normalizer."""

from __future__ import annotations


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
