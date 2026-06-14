"""evidence/services/admin/evidence_admin_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence.services.admin.evidence_admin_service import EvidenceAdminService


def _mock_evidence_service() -> MagicMock:
    svc = MagicMock()
    evidence_list = SimpleNamespace(
        id=1,
        pk=1,
        title="证据清单一",
        order=1,
        total_pages=10,
        start_page=1,
        end_page=10,
        page_range_display="1-10",
        export_version=1,
        merged_pdf=None,
        case=SimpleNamespace(name="Test Case", id=1),
        case_id=1,
        items=MagicMock(),
    )
    svc.get_evidence_list.return_value = evidence_list
    return svc


def _mock_pdf_service() -> MagicMock:
    svc = MagicMock()
    svc.merge_evidence_files.return_value = "/path/to/merged.pdf"
    return svc


def _mock_export_service() -> MagicMock:
    svc = MagicMock()
    svc.export_evidence_list.return_value = (b"doc_content", "test.docx")
    svc.export_evidence_list_with_template.return_value = (b"template_content", "template.docx")
    svc.export_evidence_detail.return_value = (b"detail_content", "detail.docx")
    return svc


# ── merge_and_update ──────────────────────────────────────────────────


class TestMergeAndUpdate:
    def test_success(self, db: object) -> None:
        evidence_svc = _mock_evidence_service()
        evidence_list = evidence_svc.get_evidence_list.return_value
        evidence_list.refresh_from_db = MagicMock()
        evidence_list.case_id = 1
        evidence_list.order = 1
        evidence_list.total_pages = 10
        pdf_svc = _mock_pdf_service()
        admin_svc = EvidenceAdminService(
            evidence_service=evidence_svc,
            pdf_service=pdf_svc,
        )
        result = admin_svc.merge_and_update(1)
        assert result["success"] is True
        assert result["pdf_path"] == "/path/to/merged.pdf"
        pdf_svc.merge_evidence_files.assert_called_once()

    def test_calculates_pages(self, db: object) -> None:
        evidence_svc = _mock_evidence_service()
        evidence_list = evidence_svc.get_evidence_list.return_value
        evidence_list.refresh_from_db = MagicMock()
        evidence_list.case_id = 1
        evidence_list.order = 1
        evidence_list.total_pages = 10
        pdf_svc = _mock_pdf_service()
        admin_svc = EvidenceAdminService(
            evidence_service=evidence_svc,
            pdf_service=pdf_svc,
        )
        admin_svc.merge_and_update(1)
        evidence_svc.calculate_page_ranges.assert_called_once_with(1)


# ── export_list_word ──────────────────────────────────────────────────


class TestExportListWord:
    def test_delegates(self) -> None:
        export_svc = _mock_export_service()
        admin_svc = EvidenceAdminService(export_service=export_svc)
        result = admin_svc.export_list_word(1)
        assert result == (b"doc_content", "test.docx")


class TestExportListWordWithTemplate:
    def test_delegates(self) -> None:
        export_svc = _mock_export_service()
        admin_svc = EvidenceAdminService(export_service=export_svc)
        result = admin_svc.export_list_word_with_template(1, 42)
        assert result == (b"template_content", "template.docx")


class TestExportDetailWord:
    def test_delegates(self) -> None:
        export_svc = _mock_export_service()
        admin_svc = EvidenceAdminService(export_service=export_svc)
        result = admin_svc.export_detail_word(1)
        assert result == (b"detail_content", "detail.docx")


# ── reorder_items ─────────────────────────────────────────────────────


class TestReorderItems:
    def test_delegates(self) -> None:
        evidence_svc = _mock_evidence_service()
        evidence_svc.reorder_items.return_value = True
        admin_svc = EvidenceAdminService(evidence_service=evidence_svc)
        assert admin_svc.reorder_items(1, [3, 1, 2]) is True
        evidence_svc.reorder_items.assert_called_once_with(1, [3, 1, 2])


# ── get_evidence_list_with_items ──────────────────────────────────────


class TestGetEvidenceListWithItems:
    def test_returns_dict(self) -> None:
        evidence_svc = _mock_evidence_service()
        item = SimpleNamespace(
            id=10,
            order=1,
            name="Item 1",
            purpose="证明",
            page_count=3,
            page_range_display="1-3",
            file=None,
            file_name="file.pdf",
            file_size_display="100KB",
        )
        evidence_list = evidence_svc.get_evidence_list.return_value
        evidence_list.items.order_by.return_value = [item]
        admin_svc = EvidenceAdminService(evidence_service=evidence_svc)
        result = admin_svc.get_evidence_list_with_items(1)
        assert result["id"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Item 1"
        assert result["items"][0]["has_file"] is False


# ── generate_pdf_filename ────────────────────────────────────────────


class TestGeneratePdfFilename:
    def test_evidence_prefix(self) -> None:
        admin_svc = EvidenceAdminService()
        evidence_list = SimpleNamespace(
            case=SimpleNamespace(name="CaseName"),
            title="证据清单一",
            export_version=1,
        )
        with patch("apps.evidence.services.admin.evidence_admin_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.admin.evidence_admin_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "evidence_detail"
            result = admin_svc.generate_pdf_filename(evidence_list)
            assert result.endswith(".pdf")

    def test_supplement_prefix(self) -> None:
        admin_svc = EvidenceAdminService()
        evidence_list = SimpleNamespace(
            case=SimpleNamespace(name="Case"),
            title="补充证据清单二",
            export_version=2,
        )
        with patch("apps.evidence.services.admin.evidence_admin_service.FilenameTemplateService") as MockFTS, \
             patch("apps.evidence.services.admin.evidence_admin_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260101"
            MockFTS.render_generated_doc.return_value = "result"
            admin_svc.generate_pdf_filename(evidence_list)
            call_kwargs = MockFTS.render_generated_doc.call_args[1]
            assert "二" in call_kwargs["doc_type"]


# ── _recount_item_pages ───────────────────────────────────────────────


class TestRecountItemPages:
    def test_no_file_clears_counts(self) -> None:
        admin_svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=None,
            page_count=5,
            page_start=1,
            page_end=5,
            save=MagicMock(),
        )
        updated, pages, error = admin_svc._recount_item_pages(item)
        assert updated == 1
        assert pages == 0
        item.save.assert_called_once()

    def test_no_file_no_change(self) -> None:
        admin_svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=None,
            page_count=0,
            page_start=None,
            page_end=None,
            save=MagicMock(),
        )
        updated, pages, error = admin_svc._recount_item_pages(item)
        assert updated == 0

    def test_non_pdf_skips(self) -> None:
        admin_svc = EvidenceAdminService()
        item = SimpleNamespace(
            file=SimpleNamespace(name="file.docx"),
            page_count=2,
            save=MagicMock(),
        )
        updated, pages, error = admin_svc._recount_item_pages(item)
        assert updated == 0
        assert pages == 2


# ── lazy loading properties ──────────────────────────────────────────


class TestLazyLoading:
    def test_evidence_service_lazy(self) -> None:
        admin_svc = EvidenceAdminService()
        assert admin_svc._evidence_service is None

    def test_pdf_service_lazy(self) -> None:
        admin_svc = EvidenceAdminService()
        assert admin_svc._pdf_service is None

    def test_export_service_lazy(self) -> None:
        admin_svc = EvidenceAdminService()
        assert admin_svc._export_service is None
