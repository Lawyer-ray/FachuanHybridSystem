"""Tests for evidence export service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestEvidenceExportServiceInit:
    def test_init_with_placeholder_service(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        mock_ps = MagicMock()
        svc = EvidenceExportService(placeholder_service=mock_ps)
        assert svc.placeholder_service is mock_ps

    def test_init_without_placeholder_service(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        assert svc._placeholder_service is None


class TestEvidenceExportServiceGetEvidenceList:
    @pytest.mark.django_db
    def test_not_found_raises(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        from apps.core.exceptions import NotFoundError
        svc = EvidenceExportService()
        with pytest.raises(NotFoundError):
            svc._get_evidence_list(999999)


class TestEvidenceExportServiceGenerateFilename:
    def test_evidence_list_type(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        evidence_list = MagicMock()
        evidence_list.case.name = "测试案件"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        with patch("apps.evidence.services.export.evidence_export_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            with patch("apps.evidence.services.export.evidence_export_service.FilenameTemplateService") as mock_fts:
                mock_fts.render_generated_doc.return_value = "证据清单一(测试案件)V1"
                filename = svc._generate_filename(evidence_list, "证据清单", 1)
                assert filename.endswith(".docx")

    def test_evidence_detail_type(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        evidence_list = MagicMock()
        evidence_list.case.name = "测试案件"
        evidence_list.title = "证据清单一"
        evidence_list.export_version = 1
        with patch("apps.evidence.services.export.evidence_export_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            with patch("apps.evidence.services.export.evidence_export_service.FilenameTemplateService") as mock_fts:
                mock_fts.render_generated_doc.return_value = "证据明细一(测试案件)V1"
                filename = svc._generate_filename(evidence_list, "证据明细", 1)
                assert "证据明细" in filename


class TestEvidenceExportServiceIncrementVersion:
    def test_returns_current_version(self):
        from apps.evidence.services.export.evidence_export_service import EvidenceExportService
        svc = EvidenceExportService()
        evidence_list = MagicMock()
        evidence_list.export_version = 3
        assert svc._increment_version(evidence_list) == 3

