"""Round 2 coverage tests for EvidenceAdminService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import sys

import pytest


def _make_service(**kwargs):
    from apps.documents.services.evidence.evidence_admin_service import EvidenceAdminService
    return EvidenceAdminService(
        evidence_service=kwargs.get("evidence_service", MagicMock()),
        pdf_service=kwargs.get("pdf_service", MagicMock()),
        export_service=kwargs.get("export_service", MagicMock()),
    )


class TestProperties:
    def test_evidence_service_injected(self):
        svc = _make_service()
        assert svc.evidence_service is not None

    def test_pdf_service_injected(self):
        svc = _make_service()
        assert svc.pdf_service is not None

    def test_export_service_injected(self):
        svc = _make_service()
        assert svc.export_service is not None


class TestExportListWord:
    def test_delegates_to_export_service(self):
        export_svc = MagicMock()
        export_svc.export_evidence_list.return_value = (b"content", "file.docx")
        svc = _make_service(export_service=export_svc)
        content, filename = svc.export_list_word(list_id=1)
        assert content == b"content"
        assert filename == "file.docx"
        export_svc.export_evidence_list.assert_called_once_with(1)


class TestExportListWordWithTemplate:
    def test_delegates_to_export_service(self):
        export_svc = MagicMock()
        export_svc.export_evidence_list_with_template.return_value = (b"t", "t.docx")
        svc = _make_service(export_service=export_svc)
        content, filename = svc.export_list_word_with_template(list_id=1, template_id=10)
        assert content == b"t"
        export_svc.export_evidence_list_with_template.assert_called_once_with(1, 10)


class TestExportDetailWord:
    def test_delegates_to_export_service(self):
        export_svc = MagicMock()
        export_svc.export_evidence_detail.return_value = (b"d", "d.docx")
        svc = _make_service(export_service=export_svc)
        content, filename = svc.export_detail_word(list_id=1)
        assert content == b"d"
        export_svc.export_evidence_detail.assert_called_once_with(1)


class TestReorderItems:
    def test_delegates_to_evidence_service(self):
        ev_svc = MagicMock()
        ev_svc.reorder_items.return_value = True
        svc = _make_service(evidence_service=ev_svc)
        result = svc.reorder_items(list_id=1, item_ids=[2, 3, 1])
        assert result is True
        ev_svc.reorder_items.assert_called_once_with(1, [2, 3, 1])


class TestGetEvidenceListWithItems:
    def test_returns_dict_with_items(self):
        ev_svc = MagicMock()
        el = MagicMock()
        el.pk = 1
        el.title = "证据清单一"
        el.order = 1
        el.total_pages = 10
        el.start_page = 1
        el.end_page = 10
        el.page_range_display = "1-10"
        el.export_version = 2
        el.merged_pdf = True

        item = MagicMock()
        item.id = 1
        item.order = 1
        item.name = "证据1"
        item.purpose = "证明"
        item.page_count = 3
        item.page_range_display = "1-3"
        item.file = "file.pdf"
        item.file_name = "file.pdf"
        item.file_size_display = "1.0 MB"

        el.items.order_by.return_value = [item]
        ev_svc.get_evidence_list.return_value = el

        svc = _make_service(evidence_service=ev_svc)
        result = svc.get_evidence_list_with_items(list_id=1)

        assert result["id"] == 1
        assert result["title"] == "证据清单一"
        assert result["has_merged_pdf"] is True
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "证据1"


class TestGeneratePdfFilename:
    def test_standard_title(self):
        svc = _make_service()
        el = MagicMock()
        el.case.name = "测试案件"
        el.title = "证据清单一"
        el.export_version = 1

        with patch("apps.documents.services.evidence.evidence_admin_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            result = svc.generate_pdf_filename(el)

        assert "证据明细一" in result
        assert "测试案件" in result
        assert result.endswith(".pdf")

    def test_supplement_title(self):
        svc = _make_service()
        el = MagicMock()
        el.case.name = "案件"
        el.title = "补充证据清单二"
        el.export_version = 1

        with patch("apps.documents.services.evidence.evidence_admin_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            result = svc.generate_pdf_filename(el)

        assert "证据明细二" in result

    def test_custom_title(self):
        svc = _make_service()
        el = MagicMock()
        el.case.name = "案件"
        el.title = "自定义标题"
        el.export_version = 1

        with patch("apps.documents.services.evidence.evidence_admin_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20260607"
            result = svc.generate_pdf_filename(el)

        assert "证据明细" in result
        assert result.endswith(".pdf")


class TestRecountItemPages:
    @pytest.fixture(autouse=True)
    def _setup_pdf_utils_module(self):
        """Inject the broken import path into sys.modules so _recount_item_pages works."""
        import types
        import apps.documents.services.infrastructure.pdf_utils as real_mod
        # Create the intermediate package modules
        parent = types.ModuleType("apps.documents.services.evidence.infrastructure")
        parent.__path__ = []
        parent.pdf_utils = real_mod
        sys.modules["apps.documents.services.evidence.infrastructure"] = parent
        sys.modules["apps.documents.services.evidence.infrastructure.pdf_utils"] = real_mod
        yield
        sys.modules.pop("apps.documents.services.evidence.infrastructure", None)
        sys.modules.pop("apps.documents.services.evidence.infrastructure.pdf_utils", None)

    def test_no_file_resets_counts(self):
        svc = _make_service()
        item = MagicMock()
        item.file = None
        item.page_count = 5
        item.page_start = 1
        item.page_end = 5
        with patch("apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error"):
            updated, count, err = svc._recount_item_pages(item)
        assert updated == 1
        assert count == 0
        assert err is None
        assert item.page_count == 0
        assert item.page_start is None
        assert item.page_end is None

    def test_no_file_already_zero(self):
        svc = _make_service()
        item = MagicMock()
        item.file = None
        item.page_count = 0
        item.page_start = None
        item.page_end = None
        with patch("apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error"):
            updated, count, err = svc._recount_item_pages(item)
        assert updated == 0
        assert count == 0

    def test_non_pdf_file(self):
        svc = _make_service()
        item = MagicMock()
        item.file.name = "image.jpg"
        item.page_count = 1
        with patch("apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error"):
            updated, count, err = svc._recount_item_pages(item)
        assert updated == 0
        assert count == 1

    def test_pdf_file_page_count_change(self):
        svc = _make_service()
        item = MagicMock()
        item.file.name = "doc.pdf"
        item.page_count = 1

        with patch(
            "apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error",
            return_value=(5, None),
        ):
            updated, count, err = svc._recount_item_pages(item)

        assert updated == 1
        assert count == 5
        assert err is None

    def test_pdf_file_same_count(self):
        svc = _make_service()
        item = MagicMock()
        item.file.name = "doc.pdf"
        item.page_count = 5

        with patch(
            "apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error",
            return_value=(5, None),
        ):
            updated, count, err = svc._recount_item_pages(item)

        assert updated == 0
        assert count == 5

    def test_pdf_error_returns_message(self):
        svc = _make_service()
        item = MagicMock()
        item.file.name = "bad.pdf"
        item.file_name = "bad.pdf"
        item.page_count = 1

        with patch(
            "apps.documents.services.evidence.infrastructure.pdf_utils.get_pdf_page_count_with_error",
            return_value=(1, "corrupted"),
        ):
            updated, count, err = svc._recount_item_pages(item)

        assert "bad.pdf" in err
        assert "识别失败" in err
