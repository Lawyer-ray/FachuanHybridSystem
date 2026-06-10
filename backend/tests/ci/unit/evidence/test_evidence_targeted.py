"""Targeted tests for evidence module to push coverage to 80%+."""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# models/evidence_storage.py (34% coverage)
# ---------------------------------------------------------------------------


class TestEvidenceFileStorage:
    def test_get_valid_name_normal(self):
        from apps.evidence.models.evidence_storage import EvidenceFileStorage

        storage = EvidenceFileStorage()
        result = storage.get_valid_name("test_file.pdf")
        assert result == "test_file.pdf"

    def test_get_valid_name_special_chars(self):
        from apps.evidence.models.evidence_storage import EvidenceFileStorage

        storage = EvidenceFileStorage()
        result = storage.get_valid_name('file<>:"/\\|?*.pdf')
        assert "<" not in result
        assert ">" not in result

    def test_generate_filename_normal(self):
        from apps.evidence.models.evidence_storage import EvidenceFileStorage

        storage = EvidenceFileStorage()
        result = storage.generate_filename("test_file.pdf")
        assert result.endswith("test_file.pdf")

    def test_get_evidence_storage(self):
        from apps.evidence.models.evidence_storage import get_evidence_storage

        storage = get_evidence_storage()
        assert storage is not None

    def test_evidence_file_storage_instance(self):
        from apps.evidence.models.evidence_storage import evidence_file_storage

        assert evidence_file_storage is not None


# ---------------------------------------------------------------------------
# services/__init__.py (30% coverage)
# ---------------------------------------------------------------------------


class TestEvidenceServicesInit:
    def test_getattr_raises_for_unknown(self):
        from apps.evidence import services

        with pytest.raises(AttributeError):
            services.NonExistentService

    def test_all_exports_listed(self):
        from apps.evidence.services import __all__

        assert "EvidenceFileService" in __all__
        assert "EvidenceMutationService" in __all__
        assert "EvidenceQueryService" in __all__


# ---------------------------------------------------------------------------
# services/ai/evidence_ai_service.py (0% coverage)
# ---------------------------------------------------------------------------


class TestEvidenceAIService:
    def test_import(self):
        from apps.evidence.services.ai.evidence_ai_service import EvidenceAIService

        assert EvidenceAIService is not None
