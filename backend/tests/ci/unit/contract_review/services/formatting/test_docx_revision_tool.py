"""Tests for contract_review.services.formatting.docx_revision_tool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.contract_review.services.formatting.docx_revision_tool import (
    DocxRevisionTool,
    _create_del,
    _create_ins,
    _make_run,
    _next_rev_id,
)


class TestNextRevId:
    def test_returns_string(self):
        result = _next_rev_id()
        assert isinstance(result, str)

    def test_increments(self):
        id1 = _next_rev_id()
        id2 = _next_rev_id()
        assert int(id2) > int(id1)


class TestMakeRun:
    def test_creates_run_element(self):
        from lxml import etree

        source = MagicMock()
        source._element = MagicMock()
        source._element.find.return_value = None
        result = _make_run("text", source)
        assert result is not None

    def test_with_del_text_tag(self):
        source = MagicMock()
        source._element = MagicMock()
        source._element.find.return_value = None
        result = _make_run("deleted", source, tag="w:delText")
        assert result is not None


class TestCreateDel:
    def test_creates_del_element(self):
        from lxml import etree

        source = MagicMock()
        source._element = MagicMock()
        source._element.find.return_value = None
        result = _create_del("old text", "author", "2024-01-01T00:00:00Z", source)
        assert result is not None


class TestCreateIns:
    def test_creates_ins_element(self):
        source = MagicMock()
        source._element = MagicMock()
        source._element.find.return_value = None
        result = _create_ins("new text", "author", "2024-01-01T00:00:00Z", source)
        assert result is not None


class TestDocxRevisionTool:
    def test_enable_track_changes(self):
        doc = MagicMock()
        settings_elem = MagicMock()
        doc.settings.element = settings_elem
        settings_elem.findall.return_value = []
        DocxRevisionTool.enable_track_changes(doc)
        settings_elem.append.assert_called_once()

    def test_apply_revision_not_found(self):
        tool = DocxRevisionTool()
        para = MagicMock()
        para.text = "no match here"
        para.runs = [MagicMock(text="no match here")]
        result = tool.apply_revision(para, "original", "replacement")
        assert result is False

    def test_apply_revision_single_run_match(self):
        """Test that single run match finds the text and returns True."""
        tool = DocxRevisionTool()
        # Create a real docx paragraph to test with
        from docx import Document

        doc = Document()
        para = doc.add_paragraph("prefix original suffix")
        result = tool.apply_revision(para, "original", "replacement")
        assert result is True
        # Verify del and ins elements were inserted
        xml_str = para._element.xml
        assert "w:del" in xml_str
        assert "w:ins" in xml_str

    def test_apply_revision_empty_runs(self):
        tool = DocxRevisionTool()
        para = MagicMock()
        para.text = ""
        para.runs = []
        result = tool.apply_revision(para, "original", "replacement")
        assert result is False

    def test_apply_revision_cross_run(self):
        """Test cross-run matching with real docx elements."""
        tool = DocxRevisionTool()
        from docx import Document

        doc = Document()
        para = doc.add_paragraph()
        # Add text split across runs
        run1 = para.add_run("hello ")
        run2 = para.add_run("world")
        result = tool.apply_revision(para, "hello world", "new text")
        assert result is True
        xml_str = para._element.xml
        assert "w:del" in xml_str
        assert "w:ins" in xml_str

    def test_apply_revision_cross_run_inserted_before_trailing_run(self):
        """跨 run 修订块必须插在被替换首 run 的原位，而非段落末尾。

        构造 4-run 段落（前缀/中间/尾巴/末尾），对「中间+尾巴」跨 run 文本做修订：
        del/ins 块应位于「前缀」run 之后、「末尾」run 之前，且末尾 run 原文保留。
        """
        from docx import Document
        from lxml import etree

        tool = DocxRevisionTool()
        doc = Document()
        para = doc.add_paragraph()
        prefix_run = para.add_run("前缀AAA")
        para.add_run("中间BBB")
        para.add_run("尾巴CCC")
        tail_run = para.add_run("末尾DDD")

        result = tool.apply_revision(para, "中间BBB尾巴CCC", "替换EE")
        assert result is True

        children = list(para._element)
        prefix_idx = children.index(prefix_run._element)
        tail_idx = children.index(tail_run._element)
        assert prefix_idx < tail_idx

        # del/ins 修订块夹在前缀与末尾之间（旧 bug 会落到段尾，夹层为空）
        in_between = children[prefix_idx + 1 : tail_idx]
        localnames = [etree.QName(c).localname for c in in_between]
        assert "del" in localnames
        assert "ins" in localnames
        # 前缀与末尾 run 原文保留、语序不变
        assert prefix_run.text == "前缀AAA"
        assert tail_run.text == "末尾DDD"
        assert children.index(prefix_run._element) < children.index(tail_run._element)
