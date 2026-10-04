"""Doxify 清洗包装器补充测试 — 正常路径（注入假 doxify 函数）与清洗链路顺序。

真实 doxify.py 位于 ~/.workbuddy（CI 不存在），正常路径通过 monkeypatch
``_import_doxify_clean`` 注入确定性实现来锁定包装器的编排契约。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.labor_arbitration.services import doxify_service


@pytest.fixture
def fake_doxify(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """注入可观测的假 doxify 清洗函数。"""
    calls: list[str] = []

    def _latex(text: str) -> str:
        calls.append("latex")
        return text.replace("$\\underline{x}$", "<u>x</u>")

    def _merge(text: str) -> tuple[str, int]:
        calls.append("merge")
        lines = text.split("\n")
        return "\n".join(lines), 2

    def _footnotes(text: str) -> tuple[str, int]:
        calls.append("footnotes")
        return text.replace("^1^", "[^1]"), 1

    def _watermarks(text: str) -> tuple[str, int]:
        calls.append("watermark")
        return "\n".join(ln for ln in text.split("\n") if "Filed By" not in ln), 3

    def _detect(text: str) -> list[str]:
        calls.append("detect")
        return ["hello", "world"]

    def _import() -> tuple[Any, Any, Any, Any, Any]:
        return (_watermarks, _merge, _footnotes, _latex, _detect)

    monkeypatch.setattr(doxify_service, "_import_doxify_clean", _import)
    return {"calls": calls}


class TestCleanText:
    def test_pipeline_order_latex_merge_watermark(self, fake_doxify: dict[str, Any]) -> None:
        text = "第一段\nFiled By: someone\n第二行 $\\underline{x}$"
        cleaned, report = doxify_service.clean_text(text)

        assert fake_doxify["calls"] == ["latex", "merge", "watermark"]
        assert "Filed By" not in cleaned
        assert "<u>x</u>" in cleaned
        assert report == {"paragraphs_merged": 2, "watermark_lines_removed": 3}

    def test_report_counts_from_fake(self, fake_doxify: dict[str, Any]) -> None:
        _, report = doxify_service.clean_text("任意文本")
        assert report["paragraphs_merged"] == 2
        assert report["watermark_lines_removed"] == 3
        # clean_text 不做脚注归一化
        assert "footnotes_normalized" not in report


class TestCleanMarkdown:
    def test_pipeline_includes_footnotes(self, fake_doxify: dict[str, Any]) -> None:
        md = "# 标题\n\n正文^1^\nFiled By: bot"
        cleaned, report = doxify_service.clean_markdown(md)

        assert fake_doxify["calls"] == ["latex", "merge", "footnotes", "watermark"]
        assert "[^1]" in cleaned
        assert "Filed By" not in cleaned
        assert report == {
            "paragraphs_merged": 2,
            "footnotes_normalized": 1,
            "watermark_lines_removed": 3,
        }


class TestCheckResidualEnglish:
    def test_returns_detected_words(self, fake_doxify: dict[str, Any]) -> None:
        assert doxify_service.check_residual_english("混合 english 文本") == ["hello", "world"]

    def test_import_exception_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> tuple[object, ...]:
            raise ImportError("gone")

        monkeypatch.setattr(doxify_service, "_import_doxify_clean", _raise)
        assert doxify_service.check_residual_english("text") == []
