"""evidence 模块 0% 覆盖率文件单元测试

覆盖文件:
- apps/evidence/services/ai/evidence_ocr_service.py
- apps/evidence/services/mutation/evidence_merge_usecase.py
- apps/evidence/services/wiring.py
- apps/evidence/tasks.py
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── services/ai/evidence_ocr_service.py ─────────────────────────


class TestEvidenceOCRServiceExtractAndSave:
    """EvidenceOCRService.extract_and_save 测试"""

    def test_item_not_found(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        with patch("apps.evidence.models.EvidenceItem") as MockItem:
            MockItem.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockItem.objects.get.side_effect = MockItem.DoesNotExist
            svc.extract_and_save(999)

    def test_item_no_file(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        with patch("apps.evidence.models.EvidenceItem") as MockItem:
            MockItem.DoesNotExist = type("DoesNotExist", (Exception,), {})
            item = SimpleNamespace(file=None, file_name="test.pdf")
            MockItem.objects.get.return_value = item
            svc.extract_and_save(1)
            MockItem.objects.filter.assert_not_called()

    def test_extract_text_pdf(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        item = SimpleNamespace(file_name="document.pdf", file=MagicMock())
        with patch.object(svc, "_extract_from_pdf", return_value="pdf text") as mock_pdf:
            result = svc._extract_text(item)
            assert result == "pdf text"
            mock_pdf.assert_called_once_with(item.file)

    def test_extract_text_image(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]:
            item = SimpleNamespace(file_name=f"img{ext}", file=MagicMock())
            with patch.object(svc, "_extract_from_image", return_value="img text"):
                result = svc._extract_text(item)
                assert result == "img text"

    def test_extract_text_unsupported(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        item = SimpleNamespace(file_name="doc.docx", file=MagicMock())
        result = svc._extract_text(item)
        assert result == ""

    def test_extract_text_no_filename(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        item = SimpleNamespace(file_name=None, file=MagicMock())
        result = svc._extract_text(item)
        assert result == ""


class TestEvidenceOCRServicePdfExtraction:
    """PDF 提取测试"""

    def test_extract_from_pdf_success(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png_bytes"
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.__len__ = MagicMock(return_value=1)

        with patch("fitz.open", return_value=mock_doc):
            with patch.object(svc, "_ocr_image_bytes", return_value="page text"):
                file_field = MagicMock()
                file_field.read.return_value = b"pdf_data"

                result = svc._extract_from_pdf(file_field)
                assert "page text" in result
                mock_doc.close.assert_called_once()

    def test_extract_from_pdf_exception(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        file_field = MagicMock()
        file_field.read.side_effect = Exception("read error")
        result = svc._extract_from_pdf(file_field)
        assert result == ""


class TestEvidenceOCRServiceImageExtraction:
    """图片提取测试"""

    def test_extract_from_image_success(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        file_field = MagicMock()
        file_field.read.return_value = b"img_data"

        with patch.object(svc, "_ocr_image_bytes", return_value="image text"):
            result = svc._extract_from_image(file_field)
            assert result == "image text"

    def test_extract_from_image_exception(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        file_field = MagicMock()
        file_field.read.side_effect = Exception("read error")
        result = svc._extract_from_image(file_field)
        assert result == ""

    def test_ocr_image_bytes_result_no_text_attr(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceOCRService

        svc = EvidenceOCRService()
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = "raw_string_result"

        with patch("apps.core.interfaces.ServiceLocator") as mock_locator:
            mock_locator.get_ocr_service.return_value = mock_ocr
            result = svc._ocr_image_bytes(b"img")
            assert result == "raw_string_result"


class TestEvidenceSearchService:
    """EvidenceSearchService.search 测试"""

    def test_search_calls_filter(self):
        from apps.evidence.services.ai.evidence_ocr_service import EvidenceSearchService

        svc = EvidenceSearchService()
        with patch("apps.evidence.models.EvidenceItem") as MockItem:
            mock_qs = MagicMock()
            MockItem.objects.filter.return_value.filter.return_value.select_related.return_value.order_by.return_value = mock_qs
            result = svc.search(case_id=1, query="test")
            assert result == mock_qs


# ── services/mutation/evidence_merge_usecase.py ─────────────────


class TestMergeProgressReporter:
    """MergeProgressReporter 测试"""

    def test_report_updates_db(self):
        from apps.evidence.services.mutation.evidence_merge_usecase import MergeProgressReporter

        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0)
        with patch("apps.evidence.models.EvidenceList") as MockList:
            reporter.report(current=5, total=10, message="half done")
            MockList.objects.filter.assert_called_once_with(pk=1)

    def test_report_skips_duplicate_progress_within_interval(self):
        from apps.evidence.services.mutation.evidence_merge_usecase import MergeProgressReporter

        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=999)
        reporter._last_progress = 50
        reporter._last_update_ts = time.time()

        with patch("apps.evidence.models.EvidenceList") as MockList:
            reporter.report(current=5, total=10, message="half done")
            MockList.objects.filter.assert_not_called()

    def test_report_zero_total(self):
        from apps.evidence.services.mutation.evidence_merge_usecase import MergeProgressReporter

        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0)
        with patch("apps.evidence.models.EvidenceList") as MockList:
            reporter.report(current=0, total=0, message="no files")
            MockList.objects.filter.assert_called_once()


class TestEvidenceMergeUseCase:
    """EvidenceMergeUseCase 测试"""

    def test_merge_list_not_found(self):
        from apps.evidence.services.mutation.evidence_merge_usecase import EvidenceMergeUseCase

        uc = EvidenceMergeUseCase()
        with patch("apps.evidence.models.EvidenceList") as MockList:
            MockList.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockList.objects.select_for_update.return_value.select_related.return_value.get.side_effect = MockList.DoesNotExist

            with patch("apps.evidence.services.mutation.evidence_merge_usecase.transaction") as mock_tx:
                mock_tx.atomic.return_value.__enter__ = MagicMock()
                mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)
                result = uc.merge(list_id=999)
                assert result["status"] == "failed"
                assert "不存在" in result["error"]

    def test_merge_delegates_to_merge(self):
        from apps.evidence.services.mutation.evidence_merge_usecase import EvidenceMergeUseCase

        uc = EvidenceMergeUseCase()
        with patch.object(uc, "merge", return_value={"list_id": 1, "status": "success"}):
            result = uc.merge(list_id=1)
            assert result["status"] == "success"


# ── services/wiring.py ──────────────────────────────────────────


class TestEvidenceWiring:
    """evidence/services/wiring.py 工厂函数测试"""

    def test_get_case_service(self):
        from apps.evidence.services.wiring import get_case_service

        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_locator:
            mock_svc = MagicMock()
            mock_locator.get_case_service.return_value = mock_svc
            result = get_case_service()
            assert result == mock_svc

    def test_get_evidence_list_placeholder_service(self):
        from apps.evidence.services.wiring import get_evidence_list_placeholder_service

        with patch("apps.evidence.services.admin.evidence_list_placeholder_service.EvidenceListPlaceholderService") as MockSvc:
            mock_instance = MagicMock()
            MockSvc.return_value = mock_instance
            result = get_evidence_list_placeholder_service()
            assert result == mock_instance

    def test_get_evidence_service(self):
        from apps.evidence.services.wiring import get_evidence_service

        with patch("apps.core.infrastructure.service_locator.ServiceLocator") as mock_locator:
            mock_case_svc = MagicMock()
            mock_locator.get_case_service.return_value = mock_case_svc

            with patch("apps.evidence.services.core.evidence_service.EvidenceService") as MockES:
                mock_instance = MagicMock()
                MockES.return_value = mock_instance
                result = get_evidence_service()
                assert result == mock_instance


# ── tasks.py ────────────────────────────────────────────────────


class TestEvidenceTasks:
    """evidence/tasks.py 异步任务测试"""

    def test_merge_evidence_pdf_task(self):
        from apps.evidence.tasks import merge_evidence_pdf_task

        with patch("apps.evidence.services.mutation.evidence_merge_usecase.EvidenceMergeUseCase") as MockUC:
            mock_instance = MagicMock()
            mock_instance.merge.return_value = {"list_id": 1, "status": "success"}
            MockUC.return_value = mock_instance

            result = merge_evidence_pdf_task(1)
            assert result["status"] == "success"
            mock_instance.merge.assert_called_once_with(list_id=1)

    def test_ocr_evidence_item_task(self):
        from apps.evidence.tasks import ocr_evidence_item_task

        with patch("apps.evidence.services.ai.evidence_ocr_service.EvidenceOCRService") as MockOCR:
            mock_instance = MagicMock()
            MockOCR.return_value = mock_instance

            ocr_evidence_item_task(42)
            mock_instance.extract_and_save.assert_called_once_with(42)
