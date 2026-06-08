"""测试文件处理工具

覆盖: apps/automation/utils/file_utils.py
重点: FileUtils.validate_file_basic
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from apps.automation.utils.file_utils import FileUtils


class TestValidateFileBasic:
    """测试基础文件校验"""

    def test_nonexistent_file(self) -> None:
        result = FileUtils.validate_file_basic("/nonexistent/file.pdf")
        assert result["valid"] is False
        assert result["error"] == "文件不存在"

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path)
            assert result["valid"] is False
            assert result["error"] == "文件为空"
        finally:
            os.unlink(path)

    def test_valid_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path)
            assert result["valid"] is True
            assert result["error"] is None
            assert result["info"]["size"] > 0
            assert result["info"]["extension"] == ".pdf"
        finally:
            os.unlink(path)

    def test_extension_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path, expected_extensions=[".docx"])
            assert result["valid"] is False
            assert "文件类型不匹配" in result["error"]
        finally:
            os.unlink(path)

    def test_extension_match(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path, expected_extensions=[".pdf", ".docx"])
            assert result["valid"] is True
        finally:
            os.unlink(path)

    def test_no_expected_extensions(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path)
            assert result["valid"] is True
        finally:
            os.unlink(path)

    def test_info_contains_size_and_extension(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            path = f.name
        try:
            result = FileUtils.validate_file_basic(path)
            assert result["info"]["size"] == 11
            assert result["info"]["extension"] == ".txt"
        finally:
            os.unlink(path)
