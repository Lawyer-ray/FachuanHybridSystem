"""合同文档快照单测。

重点锁两件事（都是真实合同上踩到的）：
1. **表格里的落款必须被抽到**——``python-docx`` 的 ``paragraphs`` 不含表格单元格，
   只取段落会丢掉「签约日期」，而它是该字段的唯一来源；
2. **超长文档裁剪不能裁掉关键条款**——收费/当事人/签署行要优先保留。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document

from apps.contracts.services.contract.intake.document_snapshot import (
    DocumentSnapshotError,
    build_snapshot,
    detect_suffix,
    select_for_prompt,
)

pytestmark = pytest.mark.unit


def _make_docx(tmp_path: Path, *, paragraphs: list[str], table: list[list[str]] | None = None) -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, cell in enumerate(row):
                grid.cell(row_index, col_index).text = cell
    path = tmp_path / "contract.docx"
    buffer = io.BytesIO()
    document.save(buffer)
    path.write_bytes(buffer.getvalue())
    return path


class TestDetectSuffix:
    @pytest.mark.parametrize("name", ["a.docx", "a.DOCX", "合同.docx"])
    def test_supported(self, name: str) -> None:
        assert detect_suffix(name) == ".docx"

    def test_unsupported_raises(self) -> None:
        with pytest.raises(DocumentSnapshotError, match="不支持的文件类型"):
            detect_suffix("a.exe")

    def test_no_extension_raises(self) -> None:
        with pytest.raises(DocumentSnapshotError):
            detect_suffix("contract")


class TestDocxExtraction:
    def test_paragraphs_extracted(self, tmp_path: Path) -> None:
        path = _make_docx(tmp_path, paragraphs=["非诉法律服务合同", "甲方：某公司"])
        snapshot = build_snapshot(path=path, filename="contract.docx")
        assert "非诉法律服务合同" in snapshot.text
        assert "甲方：某公司" in snapshot.text

    def test_table_content_extracted(self, tmp_path: Path) -> None:
        """回归：签署页在表格里，漏抽会导致签约日期丢失。"""
        path = _make_docx(
            tmp_path,
            paragraphs=["正文"],
            table=[["甲方（盖章）：", "乙方（盖章）："], ["签约日期：　年　月　日", "签约日期：　年　月　日"]],
        )
        snapshot = build_snapshot(path=path, filename="contract.docx")
        assert "签约日期" in snapshot.text
        assert snapshot.table_count == 1

    def test_blank_document_raises(self, tmp_path: Path) -> None:
        path = _make_docx(tmp_path, paragraphs=["", "   "])
        with pytest.raises(DocumentSnapshotError, match="未提取到任何文字"):
            build_snapshot(path=path, filename="contract.docx")

    def test_missing_signature_table_yields_warning(self, tmp_path: Path) -> None:
        path = _make_docx(tmp_path, paragraphs=["只有正文，没有签署页"])
        snapshot = build_snapshot(path=path, filename="contract.docx")
        assert any("签署表格" in warning for warning in snapshot.warnings)

    def test_corrupt_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.docx"
        path.write_bytes(b"not a real docx")
        with pytest.raises(DocumentSnapshotError, match="无法读取 Word"):
            build_snapshot(path=path, filename="broken.docx")


class TestPromptSelection:
    def test_short_text_returned_whole(self) -> None:
        lines = ["甲方：某公司", "律师费贰万元"]
        text, truncated = select_for_prompt(lines, max_chars=1000)
        assert truncated is False
        assert "律师费贰万元" in text

    def test_long_text_keeps_critical_lines(self) -> None:
        filler = ["本合同其他无关条款内容" * 3 for _ in range(500)]
        critical = ["律师费：贰万元整（20000.00）", "签约日期：2026年11月10日"]
        lines = ["非诉法律服务合同"] + filler[:250] + critical + filler[250:]
        text, truncated = select_for_prompt(lines, max_chars=3000)
        assert truncated is True
        assert "律师费" in text
        assert len(text) <= 3600  # 允许行粒度溢出一点，但不能失控
