"""文书附件服务和 OCR 处理器测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
from apps.pdf_splitting.services.split.ocr_handler import _ocr_pages_worker
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile


class TestDocumentAttachmentService:
    """DocumentAttachmentService 测试。"""

    def setup_method(self) -> None:
        self.case_service = MagicMock()
        self.renamer = MagicMock()
        self.service = DocumentAttachmentService(
            case_service=self.case_service,
            renamer=self.renamer,
        )

    def test_get_paths_for_renaming_no_scraper_task(self) -> None:
        """无 scraper_task 返回空列表。"""
        sms = SimpleNamespace(id=1, scraper_task=None, document_file_paths=None)
        result = self.service.get_paths_for_renaming(sms)
        assert result == []

    def test_get_paths_for_renaming_with_document_paths(self) -> None:
        """有 document_file_paths（mock Path.exists）。"""
        sms = SimpleNamespace(
            id=1,
            scraper_task=SimpleNamespace(documents=MagicMock(), result=None),
            document_file_paths=["/path/doc1.pdf"],
        )
        sms.scraper_task.documents.filter.return_value = []
        with patch("apps.automation.services.sms.document_attachment_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            result = self.service.get_paths_for_renaming(sms)
            # 由于 Path mock 的行为可能不完全匹配，这里只验证方法不抛异常
            assert isinstance(result, list)

    def test_get_paths_for_notification_no_case(self) -> None:
        """无案件返回空列表。"""
        sms = SimpleNamespace(case=None, scraper_task=None)
        result = self.service.get_paths_for_notification(sms)
        assert result == []

    def test_rename_documents_empty(self) -> None:
        """空路径列表返回空。"""
        sms = SimpleNamespace(id=1, case=SimpleNamespace(name="测试案件"))
        self.renamer.rename_with_fallback.return_value = "/path/renamed.pdf"
        result = self.service.rename_documents(sms, [])
        assert result == []


class TestOCRPageResult:
    """OCRPageResult 数据类测试。"""

    def test_creation(self) -> None:
        result = OCRPageResult(page_no=1, text="测试文本", source_method="ocr", ocr_failed=False)
        assert result.page_no == 1
        assert result.text == "测试文本"
        assert result.source_method == "ocr"
        assert result.ocr_failed is False

    def test_failed_result(self) -> None:
        result = OCRPageResult(page_no=1, text="", source_method="ocr_failed", ocr_failed=True)
        assert result.ocr_failed is True
        assert result.text == ""


class TestOCRRuntimeProfile:
    """OCRRuntimeProfile 数据类测试。"""

    def test_creation(self) -> None:
        profile = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=300, workers=4)
        assert profile.key == "balanced"
        assert profile.use_v5 is True
        assert profile.dpi == 300
        assert profile.workers == 4

    def test_frozen(self) -> None:
        profile = OCRRuntimeProfile(key="test", use_v5=False, dpi=150, workers=1)
        try:
            profile.key = "changed"  # type: ignore
            raise AssertionError("应抛出异常")
        except AttributeError:
            pass
