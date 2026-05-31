"""Unit tests for DocTextExtractor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.workbench.services.doc_extractor import DocTextExtractor

@pytest.fixture
def extractor() -> DocTextExtractor:
    return DocTextExtractor()

class TestExtractTxt:
    def test_extract_txt_file(self, extractor) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("这是测试文本内容\n第二行")
            f.flush()
            result = extractor.extract_text(f.name)
            assert "测试文本内容" in result
            assert "第二行" in result
        Path(f.name).unlink(missing_ok=True)

    def test_extract_empty_txt(self, extractor) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("")
            f.flush()
            result = extractor.extract_text(f.name)
            assert result == ""
        Path(f.name).unlink(missing_ok=True)

class TestExtractTextErrors:
    def test_file_not_found_raises(self, extractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_text("/nonexistent/path/file.docx")

    def test_unsupported_format_raises(self, extractor) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test")
            f.flush()
            with pytest.raises(ValueError, match="不支持"):
                extractor.extract_text(f.name)
        Path(f.name).unlink(missing_ok=True)

class TestCleanup:
    def test_cleanup_no_error(self, extractor) -> None:
        extractor.cleanup()  # Should not raise

    def test_cleanup_with_temp_dirs(self, extractor) -> None:
        # Simulate some temp dirs
        with tempfile.TemporaryDirectory() as d:
            extractor._single_temp_dirs.append(d)
            extractor.cleanup()
            assert len(extractor._single_temp_dirs) == 0
