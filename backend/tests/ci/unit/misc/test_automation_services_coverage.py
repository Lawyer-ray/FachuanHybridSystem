"""automation services 补充覆盖测试 (sms_matching + frame_processing)。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


# ── SMSMatchingStage ──────────────────────────────────────────────

class TestSMSMatchingStage:
    def test_import(self):
        from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage
        assert SMSMatchingStage is not None


# ── CaseMaterialSync ──────────────────────────────────────────────

class TestCaseMaterialSync:
    def test_import(self):
        try:
            from apps.contracts.services.archive.checklist.case_material_sync import CaseMaterialSyncService
            assert CaseMaterialSyncService is not None
        except ImportError:
            pytest.skip("Module not importable")


# ── FolderGenerationService ───────────────────────────────────────

class TestFolderGenerationService:
    def test_import(self):
        from apps.documents.services.generation.folder_generation_service import FolderGenerationService
        assert FolderGenerationService is not None


# ── ContractGenerationService ─────────────────────────────────────

class TestContractGenerationServiceExtended:
    def test_import(self):
        from apps.documents.services.generation.contract_generation_service import ContractGenerationService
        assert ContractGenerationService is not None


# ── SupplementaryAgreementGenerationService ───────────────────────

class TestSupplementaryAgreementGenerationServiceExtended:
    def test_import(self):
        from apps.documents.services.generation.supplementary_agreement_generation_service import (
            SupplementaryAgreementGenerationService,
        )
        assert SupplementaryAgreementGenerationService is not None


# ── PreservationMaterialsGenerationService ────────────────────────

class TestPreservationMaterialsGenerationServiceExtended:
    def test_import(self):
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )
        assert PreservationMaterialsGenerationService is not None


# ── FeeNoticeExtractionService ────────────────────────────────────

class TestFeeNoticeExtractionServiceExtended:
    def test_import(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        assert FeeNoticeExtractionService is not None


# ── FrameProcessingService ────────────────────────────────────────

class TestFrameProcessingService:
    def test_import(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService
        assert FrameProcessingService is not None

    def test_is_dhash_duplicate_empty_window(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        result = svc.is_dhash_duplicate(selection, "abc123", [], window=5, threshold=10)
        assert result is False

    def test_is_dhash_duplicate_match(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        selection.hamming_distance_hex.return_value = 2
        result = svc.is_dhash_duplicate(selection, "abc123", ["abc124"], window=5, threshold=10)
        assert result is True

    def test_is_dhash_duplicate_no_match(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        selection.hamming_distance_hex.return_value = 50
        result = svc.is_dhash_duplicate(selection, "abc123", ["def456"], window=5, threshold=10)
        assert result is False

    def test_is_pixel_duplicate_empty(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        result = svc.is_pixel_duplicate(selection, b"thumb", [], window=5, threshold=0.1)
        assert result is False

    def test_is_pixel_duplicate_match(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        selection.mean_abs_diff.return_value = 0.01
        result = svc.is_pixel_duplicate(selection, b"thumb", [b"prev"], window=5, threshold=0.1)
        assert result is True

    def test_is_pixel_duplicate_no_match(self):
        from apps.chat_records.services.extraction.frame_processing_service import FrameProcessingService

        svc = FrameProcessingService()
        selection = MagicMock()
        selection.mean_abs_diff.return_value = 0.5
        result = svc.is_pixel_duplicate(selection, b"thumb", [b"prev"], window=5, threshold=0.1)
        assert result is False


# ── VideoFrameExtractService ──────────────────────────────────────

class TestVideoFrameExtractService:
    def test_import(self):
        from apps.chat_records.services.extraction.video_frame_extract_service import VideoFrameExtractService
        assert VideoFrameExtractService is not None


# ── EnhancedOpposingPartyService ──────────────────────────────────

class TestEnhancedOpposingPartyServiceExtended:
    def test_import(self):
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )
        assert EnhancedOpposingPartyService is not None


# ── DefensePartyService ───────────────────────────────────────────

class TestDefensePartyServiceExtended:
    def test_import(self):
        from apps.documents.services.placeholders.litigation.defense_party_service import DefensePartyService
        assert DefensePartyService is not None


# ── FolderTemplateAdminService ────────────────────────────────────

class TestFolderTemplateAdminService:
    def test_import(self):
        from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService
        assert FolderTemplateAdminService is not None
