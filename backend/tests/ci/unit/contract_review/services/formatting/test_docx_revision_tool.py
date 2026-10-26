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
    enable_track_changes,
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
        enable_track_changes(doc)
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

    def _template_para(self):
        """复刻合同模板「鉴于」段的 run 结构：斜体+下划线的空位 run 夹在普通 run 间。

        真实事故（2026-10-26，/projects/393）：文档里空位是两个空格
        `'与' + '/ 拖欠  '(i+u) + '之事宜'`，编辑器复制出的选区只剩一个空格，
        跨 run 精确 find 必然失配 → 「无法精确定笔」。
        """
        from docx import Document

        doc = Document()
        para = doc.add_paragraph()
        para.add_run("甲方拟")
        para.add_run("就")
        para.add_run("与")
        blank = para.add_run("/ 拖欠  ")
        blank.italic = True
        blank.underline = True
        para.add_run("之事宜")
        para.add_run("，拟委托法律服务机构提供专项法律服务。")
        return para

    def test_apply_revision_whitespace_collapsed_selection(self):
        """选区空白被编辑器折叠（两空格→一空格）也能落笔，del 写文档实际文本。"""
        from docx.oxml.ns import qn

        tool = DocxRevisionTool()
        para = self._template_para()
        assert tool.apply_revision(para, "甲方拟就与/ 拖欠 之事宜", "鉴于甲方拟就对方拖欠货款事宜") is True
        dts = [t.text for t in para._element.iter(qn("w:delText"))]
        # del 内容是文档实际区间（保留双空格），不是选区文本
        assert dts == ["甲方拟就与/ 拖欠  之事宜"]

    def test_apply_revision_whitespace_free_selection(self):
        """选区完全没空格（下划线空位复制时被丢弃）也能落笔。"""
        tool = DocxRevisionTool()
        para = self._template_para()
        assert tool.apply_revision(para, "甲方拟就与/拖欠之事宜", "鉴于甲方拟就对方拖欠货款事宜") is True

    def test_apply_revision_selection_with_extra_space(self):
        """反向差异：选区带空格、文档没有，同样要能落笔。"""
        tool = DocxRevisionTool()
        para = self._template_para()
        assert tool.apply_revision(para, "之事宜， 拟委托", "之事宜，现拟委托") is True

    def test_apply_revision_real_content_difference_still_fails(self):
        """空白容忍不是无底线：真实内容不同必须返回 False（防误删）。"""
        tool = DocxRevisionTool()
        para = self._template_para()
        assert tool.apply_revision(para, "乙方系依法设立的证券公司", "x") is False
        assert "w:del" not in para._element.xml

    def test_find_span_maps_back_to_original_coordinates(self):
        from apps.contract_review.services.formatting.docx_revision_tool import _find_span

        assert _find_span("abc", "abc") == (0, 3)
        assert _find_span("xabcx", "abc") == (1, 4)
        # 去空白等价：区间映射回原坐标（含中间空白、不含尾后空白）
        assert _find_span("A  B C", "A B") == (0, 4)
        assert _find_span("A  B C", "AB C") == (0, 6)
        assert _find_span("A  B C", "zzz") is None
        assert _find_span("A  B C", "   ") is None

    def _revised_para(self):
        """先落一次修订的段落：直接 run + w:del + w:ins 混排。

        真实事故（2026-10-26 第二跳）：第一轮改写落盘后，段落现行文本住在
        w:ins 里，python-docx 的 paragraph.runs/text 看不见——第二轮改写
        「文档中已找不到这段原文」。此夹具复刻该状态。
        """
        from docx import Document

        doc = Document()
        para = doc.add_paragraph()
        para.add_run("第一句。")
        para.add_run("第二句")
        tool = DocxRevisionTool()
        assert tool.apply_revision(para, "第二句", "改后的第二句") is True
        para.add_run("第三句。")
        return para

    def test_visible_text_includes_ins_and_excludes_del(self):
        """现行文本口径：修订插入是正文、已删内容不是。"""
        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        para = self._revised_para()
        assert visible_text(para) == "第一句。改后的第二句第三句。"
        # python-docx 原生口径看不见 ins ——这正是旧 bug 的根源
        assert para.text == "第一句。第三句。"

    def test_apply_revision_on_ins_resident_text(self):
        """改写住在 w:ins 里的现行文本：撤回旧 ins（不留删除痕迹）、落新 ins。"""
        from docx.oxml.ns import qn

        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        para = self._revised_para()
        assert DocxRevisionTool().apply_revision(para, "改后的第二句", "再度改写的第二句") is True
        assert visible_text(para) == "第一句。再度改写的第二句第三句。"
        # 旧 ins 被撤回而不是包进 del（未接受的插入不留删除痕迹）；
        # 第一轮的 del 保留原样
        dts = [t.text for t in para._element.iter(qn("w:delText"))]
        assert dts == ["第二句"]
        # ins 里的每个 w:t 文本
        ins_texts = [t.text for t in para._element.iter(qn("w:ins")) for t in t.iter(qn("w:t"))]
        assert ins_texts == ["再度改写的第二句"]

    def test_apply_revision_spanning_direct_and_ins(self):
        """选区横跨直接 run 与 ins（第一句。+ 改后的第二句）：两半都按各自语义处理。"""
        from docx.oxml.ns import qn

        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        para = self._revised_para()
        assert DocxRevisionTool().apply_revision(para, "第一句。改后的第二句", "开篇两句合并") is True
        assert visible_text(para) == "开篇两句合并第三句。"
        # 直接 run 的「第一句。」进 del；ins 部分被撤回
        dts = [t.text for t in para._element.iter(qn("w:delText"))]
        assert "第一句。" in dts and "改后的第二句" not in dts

    def test_apply_revision_partial_ins_keeps_remainder_as_ins(self):
        """区间只吃掉 ins 的一部分：残余仍待在 ins 里，不降级成普通文本。"""
        from docx.oxml.ns import qn

        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        para = self._revised_para()
        # 只改 ins 文本的前半「改后的」
        assert DocxRevisionTool().apply_revision(para, "改后的", "调整后的") is True
        assert visible_text(para) == "第一句。调整后的第二句第三句。"
        # 残余「第二句」必须仍住在某个 w:ins 里
        ins_texts = [t.text for t in para._element.iter(qn("w:ins")) for t in t.iter(qn("w:t"))]
        assert "调整后的" in ins_texts and "第二句" in ins_texts
        # 无嵌套修订容器
        for child in para._element:
            tag = child.tag.split("}")[1]
            if tag in ("ins", "del"):
                assert not [c for c in child if c.tag.endswith("}ins") or c.tag.endswith("}del")]

    def test_apply_revision_del_text_never_matches(self):
        """已删除内容（delText）不参与匹配：改「第二句」不能再命中删除线里的旧文。"""
        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        para = self._revised_para()
        # 现行文本里没有「第二句」裸词（只有「改后的第二句」整体在 ins、
        # 「第二句」在 del 里）——要求改「第二句」应改到 ins 内的那份
        assert DocxRevisionTool().apply_revision(para, "第二句", "新句") is True
        assert "新句" in visible_text(para)
