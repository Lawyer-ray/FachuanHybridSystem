"""documents template_matching + placeholders 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


# ── TemplateMatchingService ────────────────────────────────────────

class TestTemplateMatchingServiceCache:
    @patch("apps.documents.services.template.template_matching_service.cache")
    def test_get_document_templates_cache_version(self, mock_cache):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        mock_cache.add.return_value = True
        mock_cache.get.return_value = 5
        svc = TemplateMatchingService()
        version = svc._get_document_templates_cache_version()
        assert version == 5

    @patch("apps.documents.services.template.template_matching_service.cache")
    def test_get_folder_templates_cache_version(self, mock_cache):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        mock_cache.add.return_value = True
        mock_cache.get.return_value = 3
        svc = TemplateMatchingService()
        version = svc._get_folder_templates_cache_version()
        assert version == 3

    @patch("apps.documents.services.template.template_matching_service.cache")
    def test_cache_version_default(self, mock_cache):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        mock_cache.add.return_value = True
        mock_cache.get.return_value = None
        svc = TemplateMatchingService()
        version = svc._get_document_templates_cache_version()
        assert version == 1


class TestFindMatchingCaseDocumentTemplateNames:
    @patch("apps.documents.services.template.template_matching_service.DocumentTemplate")
    def test_matching_case_type(self, mock_model):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        template = MagicMock()
        template.name = "起诉状模板"
        template.case_types = ["litigation"]
        mock_model.objects.filter.return_value = [template]

        svc = TemplateMatchingService()
        result = svc.find_matching_case_document_template_names("litigation")
        assert "起诉状模板" in result

    @patch("apps.documents.services.template.template_matching_service.DocumentTemplate")
    def test_all_case_types_matches_any(self, mock_model):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService
        from apps.documents.models.choices import LegalStatusMatchMode

        template = MagicMock()
        template.name = "通用模板"
        template.case_types = [LegalStatusMatchMode.ALL]
        mock_model.objects.filter.return_value = [template]

        svc = TemplateMatchingService()
        result = svc.find_matching_case_document_template_names("litigation")
        assert "通用模板" in result

    @patch("apps.documents.services.template.template_matching_service.DocumentTemplate")
    def test_empty_case_types_matches_any(self, mock_model):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        template = MagicMock()
        template.name = "默认模板"
        template.case_types = []
        mock_model.objects.filter.return_value = [template]

        svc = TemplateMatchingService()
        result = svc.find_matching_case_document_template_names("criminal")
        assert "默认模板" in result

    @patch("apps.documents.services.template.template_matching_service.DocumentTemplate")
    def test_no_match(self, mock_model):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        template = MagicMock()
        template.name = "诉讼模板"
        template.case_types = ["litigation"]
        mock_model.objects.filter.return_value = [template]

        svc = TemplateMatchingService()
        result = svc.find_matching_case_document_template_names("criminal")
        assert len(result) == 0


class TestMissingSentinel:
    def test_sentinel_value(self):
        from apps.documents.services.template.template_matching_service import TemplateMatchingService

        assert TemplateMatchingService._MISSING_SENTINEL == "__documents_template_matching_missing__"


# ── EnhancedOpposingPartyService ──────────────────────────────────

class TestEnhancedOpposingPartyService:
    def test_import(self):
        """Verify the module is importable."""
        from apps.documents.services.placeholders.contract import enhanced_opposing_party_service
        assert enhanced_opposing_party_service is not None


# ── DefensePartyService ───────────────────────────────────────────

class TestDefensePartyService:
    def test_import(self):
        """Verify the module is importable."""
        from apps.documents.services.placeholders.litigation import defense_party_service
        assert defense_party_service is not None


# ── ContractGenerationService ─────────────────────────────────────

class TestContractGenerationService:
    def test_import(self):
        """Verify the module is importable."""
        from apps.documents.services.generation import contract_generation_service
        assert contract_generation_service is not None


# ── SupplementaryAgreementGenerationService ───────────────────────

class TestSupplementaryAgreementGenerationService:
    def test_import(self):
        """Verify the module is importable."""
        from apps.documents.services.generation import supplementary_agreement_generation_service
        assert supplementary_agreement_generation_service is not None


# ── PreservationMaterialsGenerationService ────────────────────────

class TestPreservationMaterialsGenerationService:
    def test_import(self):
        """Verify the module is importable."""
        from apps.documents.services.generation import preservation_materials_generation_service
        assert preservation_materials_generation_service is not None
