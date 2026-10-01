"""Doxify 清洗包装器的契约测试。

doxify.py 位于 ~/.workbuddy（用户机器外部脚本），CI 环境没有。
这里只锁定包装器自身的行为契约：空值直通、导入失败降级不抛错。
真实清洗效果不在单测范围（依赖外部脚本版本）。
"""

from __future__ import annotations

import pytest

from apps.labor_arbitration.services import doxify_service


class TestEmptyInputs:
    def test_clean_text_empty(self) -> None:
        assert doxify_service.clean_text("") == ("", {})
        assert doxify_service.clean_text("   \n  ") == ("   \n  ", {})

    def test_clean_markdown_empty(self) -> None:
        assert doxify_service.clean_markdown("") == ("", {})

    def test_check_residual_english_empty(self) -> None:
        assert doxify_service.check_residual_english("") == []
        assert doxify_service.check_residual_english("  ") == []


class TestDegradeOnImportFailure:
    @pytest.fixture(autouse=True)
    def _break_doxify_import(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> tuple[object, ...]:
            raise ImportError("No module named 'doxify'")

        monkeypatch.setattr(doxify_service, "_import_doxify_clean", _raise)

    def test_clean_text_returns_original_with_error_report(self) -> None:
        text = "原文保持不变\n$\\underline{x}$"
        cleaned, report = doxify_service.clean_text(text)
        assert cleaned == text
        assert "error" in report

    def test_clean_markdown_returns_original_with_error_report(self) -> None:
        md = "# 标题\n\n正文^1^"
        cleaned, report = doxify_service.clean_markdown(md)
        assert cleaned == md
        assert "error" in report

    def test_check_residual_english_returns_empty(self) -> None:
        assert doxify_service.check_residual_english("some english text") == []
