"""base_court_scraper 单元测试 — 下载目录、保存链路与批量落库。

覆盖模块函数（media_download_rel_dir / media_download_target / as_sync_page /
as_sync_context）与 ``BaseCourtDocumentScraper`` 的文书记录保存方法。
全部 mock page/document_service，不起浏览器。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.automation.services.scraper.scrapers.court_document.base_court_scraper import (
    BaseCourtDocumentScraper,
    as_sync_context,
    as_sync_page,
    media_download_rel_dir,
    media_download_target,
)


def _make_scraper(document_service: Any = None, task_id: int = 42) -> BaseCourtDocumentScraper:
    """跳过 BaseScraper.__init__（会连 ServiceLocator），手工补齐所需属性。"""
    scraper = BaseCourtDocumentScraper.__new__(BaseCourtDocumentScraper)
    scraper.task = SimpleNamespace(id=task_id, case=None, case_id=None)
    scraper.site_name = "court_document"
    scraper.debug_info = {}
    scraper._document_service = document_service
    scraper.page = None
    return scraper


class TestMediaPathHelpers:
    def test_rel_dir_layout(self) -> None:
        assert media_download_rel_dir(7) == "case_logs/7/documents"

    @override_settings(MEDIA_ROOT="/tmp/fachuan-test-media")
    def test_media_download_target_creates_parent(self, tmp_path: Path) -> None:
        with patch("apps.automation.services.scraper.scrapers.court_document.base_court_scraper.to_media_abs") as m_abs:
            target = tmp_path / "case_logs" / "7" / "documents" / "doc.pdf"
            m_abs.return_value = target
            abs_path, rel_path = media_download_target(7, "doc.pdf")

        m_abs.assert_called_once_with("case_logs/7/documents/doc.pdf")
        assert abs_path == target
        assert target.parent.is_dir()
        assert rel_path == "case_logs/7/documents/doc.pdf"


class TestSyncPageHelpers:
    def test_as_sync_page_returns_page(self) -> None:
        page = object()
        assert as_sync_page(page) is page  # type: ignore[arg-type]

    def test_as_sync_page_none_raises(self) -> None:
        with pytest.raises(AssertionError, match="浏览器页面未初始化"):
            as_sync_page(None)

    def test_as_sync_context_returns_context(self) -> None:
        context = object()
        assert as_sync_context(context) is context  # type: ignore[arg-type]

    def test_as_sync_context_none_raises(self) -> None:
        with pytest.raises(AssertionError, match="浏览器上下文未初始化"):
            as_sync_context(None)


class TestSaveDocumentToDb:
    def _doc_service(self, document: Any) -> MagicMock:
        svc = MagicMock()
        svc.create_document_from_api_data.return_value = document
        svc.update_download_status.return_value = document
        return svc

    def test_success_with_existing_file_records_size(self, tmp_path: Path) -> None:
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"12345")
        document = SimpleNamespace(id=11, c_wsmc="裁定书", download_status="pending")
        svc = self._doc_service(document)
        scraper = _make_scraper(document_service=svc)

        result = scraper._save_document_to_db({"c_wsmc": "裁定书"}, (True, str(pdf), None))

        assert result == 11
        svc.update_download_status.assert_called_once_with(
            document_id=11, status="success", local_file_path=str(pdf), file_size=5
        )

    def test_success_with_missing_file_size_none(self, tmp_path: Path) -> None:
        document = SimpleNamespace(id=12, c_wsmc="判决书", download_status="pending")
        svc = self._doc_service(document)
        scraper = _make_scraper(document_service=svc)

        result = scraper._save_document_to_db({"c_wsmc": "判决书"}, (True, str(tmp_path / "missing.pdf"), None))

        assert result == 12
        assert svc.update_download_status.call_args.kwargs["file_size"] is None

    def test_failure_marks_failed_status(self) -> None:
        document = SimpleNamespace(id=13, c_wsmc="决定书", download_status="pending")
        svc = self._doc_service(document)
        scraper = _make_scraper(document_service=svc)

        result = scraper._save_document_to_db({}, (False, None, "下载超时"))

        assert result == 13
        svc.update_download_status.assert_called_once_with(document_id=13, status="failed", error_message="下载超时")

    def test_exception_returns_none_without_raising(self) -> None:
        svc = MagicMock()
        svc.create_document_from_api_data.side_effect = RuntimeError("db down")
        scraper = _make_scraper(document_service=svc)

        assert scraper._save_document_to_db({}, (True, "/x.pdf", None)) is None


class TestSaveDocumentsBatch:
    def _doc(self, doc_id: int) -> SimpleNamespace:
        return SimpleNamespace(id=doc_id, c_wsmc=f"文书{doc_id}", download_status="success")

    def test_mixed_results_aggregate_stats(self) -> None:
        svc = MagicMock()
        docs = {11: self._doc(11), 12: self._doc(12)}
        created = iter([docs[11], docs[12]])
        svc.create_document_from_api_data.side_effect = lambda **kwargs: next(created)
        svc.update_download_status.side_effect = lambda *, document_id, **kw: docs[document_id]
        # 第三条让 create 抛错 → 记 failed
        svc2_calls = {"n": 0}

        def _create(**kwargs: Any) -> Any:
            svc2_calls["n"] += 1
            if svc2_calls["n"] == 3:
                raise RuntimeError("第三条失败")
            return docs[11 if svc2_calls["n"] == 1 else 12]

        svc.create_document_from_api_data.side_effect = _create
        scraper = _make_scraper(document_service=svc)

        result = scraper._save_documents_batch(
            [
                ({"idx": 1}, (True, "/a.pdf", None)),
                ({"idx": 2}, (False, None, "err")),
                ({"idx": 3}, (True, "/c.pdf", None)),
            ]
        )

        assert result == {"total": 3, "success": 2, "failed": 1, "document_ids": [11, 12]}

    def test_empty_input_returns_zero_stats(self) -> None:
        scraper = _make_scraper(document_service=MagicMock())
        result = scraper._save_documents_batch([])
        assert result == {"total": 0, "success": 0, "failed": 0, "document_ids": []}


class TestPageStateWithoutPage:
    def test_save_page_state_page_none_returns_placeholders(self) -> None:
        scraper = _make_scraper()
        result = scraper._save_page_state("after_click")
        assert result == {"name": "after_click", "screenshot": None, "html": None, "analysis": None}


class TestSaveDebugInfo:
    def test_debug_info_stored(self) -> None:
        scraper = _make_scraper()
        scraper._save_debug_info("step", {"k": "v"})
        assert scraper.debug_info["step"] == {"k": "v"}


class TestPrepareDownloadDir:
    def test_prepare_download_dir_creates_media_layout(self, tmp_path: Path) -> None:
        target = tmp_path / "case_logs" / "9" / "documents"
        scraper = _make_scraper(task_id=9)
        with patch(
            "apps.automation.services.scraper.scrapers.court_document.base_court_scraper.to_media_abs",
            return_value=target,
        ) as m_abs:
            result = scraper._prepare_download_dir()

        m_abs.assert_called_once_with("case_logs/9/documents")
        assert result == target
        assert target.is_dir()
