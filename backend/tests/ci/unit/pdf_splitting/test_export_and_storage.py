"""PDF 导出工具和存储服务测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from apps.pdf_splitting.services.split.export_utils import ExportUtils
from apps.pdf_splitting.services.storage import PdfSplitStorage


class TestExportUtils:
    """ExportUtils 测试。"""

    def test_deduplicate_filename_unique(self) -> None:
        """唯一文件名。"""
        seen: set[str] = set()
        result = ExportUtils.deduplicate_filename("起诉状.pdf", seen)
        assert result == "起诉状.pdf"
        assert "起诉状.pdf" in seen

    def test_deduplicate_filename_duplicate(self) -> None:
        """重复文件名。"""
        seen: set[str] = {"起诉状.pdf"}
        result = ExportUtils.deduplicate_filename("起诉状.pdf", seen)
        assert result == "起诉状_2.pdf"

    def test_deduplicate_filename_multiple_duplicates(self) -> None:
        """多次重复。"""
        seen: set[str] = {"起诉状.pdf", "起诉状_2.pdf"}
        result = ExportUtils.deduplicate_filename("起诉状.pdf", seen)
        assert result == "起诉状_3.pdf"

    def test_deduplicate_filename_no_extension(self) -> None:
        """无扩展名。"""
        seen: set[str] = set()
        result = ExportUtils.deduplicate_filename("起诉状", seen)
        assert result == "起诉状.pdf"

    def test_deduplicate_filename_empty(self) -> None:
        """空文件名。"""
        seen: set[str] = set()
        result = ExportUtils.deduplicate_filename("", seen)
        assert result == "片段.pdf"


class TestPdfSplitStorage:
    """PdfSplitStorage 测试。"""

    def test_job_root(self) -> None:
        """任务根目录。"""
        storage = PdfSplitStorage("test-job-id")
        assert "test-job-id" in str(storage.job_root)
        assert "pdf_splitting" in str(storage.job_root)

    def test_source_dir(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.source_dir.name == "source"

    def test_analysis_dir(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.analysis_dir.name == "analysis"

    def test_previews_dir(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.previews_dir.name == "previews"

    def test_exports_dir(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.exports_dir.name == "exports"

    def test_source_pdf_path(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.source_pdf_path.name == "original.pdf"

    def test_pages_json_path(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.pages_json_path.name == "pages.json"

    def test_segments_json_path(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.segments_json_path.name == "segments.json"

    def test_export_zip_path(self) -> None:
        storage = PdfSplitStorage("test-id")
        assert storage.export_zip_path.name == "split_result.zip"

    def test_ensure_dirs(self) -> None:
        """创建目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                storage = PdfSplitStorage("test-ensure")
                storage.ensure_dirs()
                assert storage.source_dir.exists()
                assert storage.analysis_dir.exists()
                assert storage.previews_dir.exists()
                assert storage.exports_dir.exists()
            finally:
                django.conf.settings.MEDIA_ROOT = old

    def test_write_json(self) -> None:
        """写入 JSON 文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                storage = PdfSplitStorage("test-json")
                storage.ensure_dirs()
                data = {"segments": [{"type": "complaint"}]}
                storage.write_json(storage.segments_json_path, data)

                written = json.loads(storage.segments_json_path.read_text(encoding="utf-8"))
                assert written["segments"][0]["type"] == "complaint"
            finally:
                django.conf.settings.MEDIA_ROOT = old

    def test_cleanup(self) -> None:
        """清理目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                storage = PdfSplitStorage("test-cleanup")
                storage.ensure_dirs()
                assert storage.job_root.exists()
                storage.cleanup()
                assert not storage.job_root.exists()
            finally:
                django.conf.settings.MEDIA_ROOT = old

    def test_uuid_job_id(self) -> None:
        """UUID 类型的 job_id。"""
        import uuid

        job_id = uuid.uuid4()
        storage = PdfSplitStorage(job_id)
        assert str(job_id) in str(storage.job_root)
