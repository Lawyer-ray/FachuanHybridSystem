"""文档模板占位符提取、PDF 工具、批量打印存储、浏览器工具测试。"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from apps.documents.services.document_template.placeholder_extractor import PLACEHOLDER_PATTERN
from apps.documents.services.infrastructure.pdf_utils import _read_source_bytes
from apps.batch_printing.services.storage import BatchPrintStorage


class TestPlaceholderPattern:
    """占位符正则模式测试。"""

    def test_match_double_braces(self) -> None:
        """匹配双花括号占位符。"""
        assert PLACEHOLDER_PATTERN.search("{{ party_name }}") is not None
        assert PLACEHOLDER_PATTERN.search("{{party_name}}") is not None

    def test_match_chinese_placeholder(self) -> None:
        """匹配中文占位符。"""
        assert PLACEHOLDER_PATTERN.search("{{当事人姓名}}") is not None

    def test_no_match_single_brace(self) -> None:
        """单花括号不匹配。"""
        assert PLACEHOLDER_PATTERN.search("{party_name}") is None

    def test_no_match_empty(self) -> None:
        """空占位符不匹配。"""
        assert PLACEHOLDER_PATTERN.search("{{ }}") is None

    def test_extract_multiple(self) -> None:
        """提取多个占位符。"""
        text = "姓名：{{name}}，地址：{{address}}，电话：{{phone}}"
        matches = PLACEHOLDER_PATTERN.findall(text)
        assert "name" in matches
        assert "address" in matches
        assert "phone" in matches

    def test_match_with_dots(self) -> None:
        """匹配带点号的占位符。"""
        assert PLACEHOLDER_PATTERN.search("{{ party.name }}") is not None

    def test_match_with_parens(self) -> None:
        """匹配带括号的占位符。"""
        assert PLACEHOLDER_PATTERN.search("{{ func(arg) }}") is not None


class TestReadSourceBytes:
    """_read_source_bytes 测试。"""

    def test_none_raises(self) -> None:
        """None 源抛出异常。"""
        try:
            _read_source_bytes(None)
            assert False, "应抛出 ValueError"
        except ValueError as e:
            assert "None" in str(e)

    def test_bytes_input(self) -> None:
        """bytes 输入。"""
        result = _read_source_bytes(b"hello")
        assert result == b"hello"

    def test_file_path(self) -> None:
        """文件路径输入。"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(b"fake pdf")
            f.flush()
            result = _read_source_bytes(f.name)
            assert result == b"fake pdf"


class TestBatchPrintStorage:
    """BatchPrintStorage 测试。"""

    def test_job_root(self) -> None:
        storage = BatchPrintStorage("test-id")
        assert "batch_printing" in str(storage.job_root)
        assert "test-id" in str(storage.job_root)

    def test_source_dir(self) -> None:
        storage = BatchPrintStorage("test-id")
        assert storage.source_dir.name == "source"

    def test_prepared_dir(self) -> None:
        storage = BatchPrintStorage("test-id")
        assert storage.prepared_dir.name == "prepared"

    def test_artifacts_dir(self) -> None:
        storage = BatchPrintStorage("test-id")
        assert storage.artifacts_dir.name == "artifacts"

    def test_source_file_path(self) -> None:
        storage = BatchPrintStorage("test-id")
        path = storage.source_file_path(order=1, filename="test.pdf")
        assert path.name == "001_test.pdf"

    def test_prepared_pdf_path(self) -> None:
        storage = BatchPrintStorage("test-id")
        path = storage.prepared_pdf_path(order=1, filename_stem="test")
        assert path.name == "001_test.pdf"

    def test_ensure_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                storage = BatchPrintStorage("test-ensure")
                storage.ensure_dirs()
                assert storage.source_dir.exists()
                assert storage.prepared_dir.exists()
                assert storage.artifacts_dir.exists()
            finally:
                django.conf.settings.MEDIA_ROOT = old

    def test_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                storage = BatchPrintStorage("test-cleanup")
                storage.ensure_dirs()
                assert storage.job_root.exists()
                storage.cleanup()
                assert not storage.job_root.exists()
            finally:
                django.conf.settings.MEDIA_ROOT = old

    def test_uuid_job_id(self) -> None:
        import uuid

        job_id = uuid.uuid4()
        storage = BatchPrintStorage(job_id)
        assert str(job_id) in str(storage.job_root)
