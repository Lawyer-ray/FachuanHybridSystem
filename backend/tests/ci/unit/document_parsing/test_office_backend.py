"""Office 后端（docx / xlsx）：正文、Markdown、结构与定位。

为什么不用 OnlyOffice 抽文本，见 office_backend.py 模块头注释。这里的用例
守住两条容易退化的性质：
  ① 正文与表格必须按**文档流顺序**输出（分开读会把表格全挪到文末）；
  ② 块结构必须保留（曾被按行切合，导致 12 个块塌成 1 个、coverage 判不可用）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.core.exceptions import ValidationException


@pytest.fixture
def docx_with_structure(tmp_path: Path) -> Path:
    """含标题 / 正文 / 表格 / 尾部正文的 docx。"""
    import docx

    d = docx.Document()
    d.add_heading("一级标题", level=1)
    d.add_paragraph("正文段落内容")
    d.add_heading("二级标题", level=2)
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "姓名"
    table.cell(0, 1).text = "金额"
    table.cell(1, 0).text = "张三"
    table.cell(1, 1).text = "100"
    d.add_paragraph("表格之后的正文")
    path = tmp_path / "sample.docx"
    d.save(str(path))
    return path


@pytest.fixture
def xlsx_workbook(tmp_path: Path) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "流水"
    ws.append(["日期", "金额", "摘要"])
    ws.append(["2024-01-01", 12000, "转账"])
    ws.append(["2024-02-01", 34000, "还款"])
    path = tmp_path / "sample.xlsx"
    wb.save(str(path))
    return path


class TestDocx:
    def test_markdown_keeps_headings_and_tables(self, docx_with_structure: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(docx_with_structure))
        md = parsed.markdown or ""
        assert "# 一级标题" in md
        assert "## 二级标题" in md
        # 表格转成 GFM，而不是把单元格用制表符糊成一行
        assert "| 姓名 | 金额 |" in md
        assert "| 张三 | 100 |" in md

    def test_document_flow_order_is_preserved(self, docx_with_structure: Path) -> None:
        """表格必须留在它在正文中的**原位置**，不能被挪到文末。

        这是本后端最容易写错的地方：先读 paragraphs 再读 tables 会让所有表格
        堆到文末，Markdown 顺序与原文不符，下游分段也跟着错。
        """
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        md = OfficeBackend().parse_document(str(docx_with_structure)).markdown or ""
        assert md.index("正文段落内容") < md.index("| 姓名 | 金额 |") < md.index("表格之后的正文")

    def test_block_structure_is_kept(self, docx_with_structure: Path) -> None:
        """块不能塌成一个（曾按行切合，导致 coverage.has_blocks=False）。"""
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(docx_with_structure))
        assert parsed.blocks is not None
        assert len(parsed.blocks) >= 4
        assert parsed.coverage.has_blocks is True
        types = {b.type for b in parsed.blocks}
        assert "table" in types
        assert "title" in types

    def test_locators_present_for_positioning(self, docx_with_structure: Path) -> None:
        """定位信息必须真的落到页块上（识别定位靠它）。"""
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(docx_with_structure))
        blocks = (parsed.layout or {}).get("pages", [{}])[0].get("blocks", [])
        locators = [b.get("locator") for b in blocks if isinstance(b, dict) and b.get("locator")]
        assert locators, "页块应带 locator（段落序 / 表格序）"
        assert any(loc.get("kind") in {"paragraph", "table"} for loc in locators if isinstance(loc, dict))

    def test_bbox_is_marked_approximate(self, docx_with_structure: Path) -> None:
        """Office 没有像素坐标：给整页框并标 approx，不给假精度。"""
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(docx_with_structure))
        assert (parsed.layout or {}).get("bbox_approx") is True
        blocks = (parsed.layout or {}).get("pages", [{}])[0].get("blocks", [])
        assert all(b.get("bbox") == [0.0, 0.0, 1.0, 1.0] for b in blocks if isinstance(b, dict))

    def test_extract_text_returns_plain_text(self, docx_with_structure: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        result = OfficeBackend().extract_text(str(docx_with_structure))
        assert result.success is True
        assert "正文段落内容" in result.text
        # Markdown 标记不该混进纯文本
        assert "#" not in result.text.split("\n")[0]


class TestExcel:
    def test_sheet_becomes_markdown_table(self, xlsx_workbook: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(xlsx_workbook))
        md = parsed.markdown or ""
        assert "## 流水" in md
        assert "| 日期 | 金额 | 摘要 |" in md
        assert "| 2024-01-01 | 12000 | 转账 |" in md

    def test_rows_become_text_lines(self, xlsx_workbook: Path) -> None:
        """纯文本按行铺开：下游分段/当事人识别是按行扫的。"""
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(xlsx_workbook))
        assert "日期 金额 摘要" in parsed.text
        assert "2024-01-01 12000 转账" in parsed.text

    def test_row_locator_has_sheet_and_row(self, xlsx_workbook: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        parsed = OfficeBackend().parse_document(str(xlsx_workbook))
        blocks = (parsed.layout or {}).get("pages", [{}])[0].get("blocks", [])
        locators = [b["locator"] for b in blocks if isinstance(b, dict) and b.get("locator")]
        assert locators
        assert locators[0]["kind"] == "cell_row"
        assert locators[0]["sheet"] == "流水"
        assert isinstance(locators[0]["row"], int)


class TestErrors:
    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        bad = tmp_path / "a.txt"
        bad.write_text("x", encoding="utf-8")
        with pytest.raises(ValidationException, match="不支持"):
            OfficeBackend().parse_document(str(bad))

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        with pytest.raises(FileNotFoundError):
            OfficeBackend().parse_document(str(tmp_path / "nope.docx"))

    def test_extract_text_swallows_errors(self, tmp_path: Path) -> None:
        """extract_text 与云端后端同款：失败返回 success=False 而不是抛。"""
        from apps.document_parsing.services.backends.office_backend import OfficeBackend

        bad = tmp_path / "a.txt"
        bad.write_text("x", encoding="utf-8")
        result = OfficeBackend().extract_text(str(bad))
        assert result.success is False


class TestRegistration:
    def test_registered_in_factory(self) -> None:
        from apps.document_parsing.services.parser_factory import ParserFactory

        assert "office" in ParserFactory._BACKEND_REGISTRY
