"""``md_table``：HTML 表格 → GFM 的网格对齐 / 表头判定 / 降级 / 页脚剔除 / 续表合并。

测试数据全部虚构（人名用「某甲/某乙」，账号/证件号用明显假号）。
判据的真实依据见被测模块里的常量注释（164 页卷宗实测分布）。
"""

from __future__ import annotations

import logging

import pytest

from apps.pdf_splitting.services.split.md_table import (
    MAX_GFM_COLUMNS,
    GfmTable,
    drop_footer_table_lines,
    grid_col_count,
    is_footer_row,
    looks_like_header,
    merge_continuation,
    parse_grid,
    parse_table,
    split_gfm_row,
    table_years_unreliable,
)


def _table(rows: list[list[str]], *, spans: dict[tuple[int, int], tuple[int, int]] | None = None) -> str:
    """按单元格文字拼 HTML；``spans[(行,列)] = (rowspan, colspan)``。"""
    out = []
    for r, row in enumerate(rows):
        cells = []
        for c, text in enumerate(row):
            rowspan, colspan = (spans or {}).get((r, c), (1, 1))
            attrs = ""
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            cells.append(f"<td{attrs}>{text}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(out) + "</table>"


def _render(html: str, *, page_text: str = "") -> str:
    table = parse_table(html, page_text=page_text)
    assert table is not None
    return table.render()


class TestGridAlignment:
    """合并单元格按**真实网格列位置**放文字——金额错列是诉请金额的生命线。"""

    def test_colspan_文字落锚点列_被覆盖列留空(self) -> None:
        html = _table([["合计", "100.00"], ["本金", "利息", "100.00"]], spans={(0, 0): (1, 2)})
        lines = _render(html).splitlines()

        # 「合计」横跨前两列，金额必须留在第 3 列（按 td 个数补空列会把它挤到第 2 列）
        assert lines[2] == "| 合计 |  | 100.00 |"
        assert lines[3] == "| 本金 | 利息 | 100.00 |"

    def test_rowspan_文字只在首行出现(self) -> None:
        html = _table([["照片", "姓名"], ["某甲"]], spans={(0, 0): (2, 1)})
        lines = _render(html).splitlines()

        assert lines[0] == "| 照片 | 姓名 |"
        assert lines[2] == "|  | 某甲 |"

    def test_网格列数由_span_累加而非_td_个数(self) -> None:
        html = _table([["甲", "乙"], ["丙", "丁", "戊"]], spans={(0, 0): (1, 2)})
        assert grid_col_count(parse_grid(html)) == 3

    def test_竖线转义与实体反转义与空白折叠(self) -> None:
        html = "<table><tr><td>类型</td><td>备注</td></tr><tr><td>借|条</td><td>甲方&amp;乙方\n  丙</td></tr></table>"
        lines = _render(html).splitlines()

        assert lines[2] == "| 借\\|条 | 甲方&乙方 丙 |"

    def test_解析不出行时返回None(self) -> None:
        assert parse_table("") is None
        assert parse_table("<div>不是表格</div>") is None
        assert parse_table("<table><tr><td></td><td></td></tr></table>") is None


class TestHeaderDetection:
    """首行像表头才当表头；否则插空表头行，数据一行不丢。"""

    def test_th_标签即表头(self) -> None:
        html = "<table><tr><th>序号</th><th>姓名</th></tr><tr><td>1</td><td>某甲</td></tr></table>"
        table = parse_table(html)
        assert table is not None and table.has_header is True
        assert table.header == ["序号", "姓名"]
        assert table.rows == [["1", "某甲"]]

    def test_表头词命中且容忍OCR吞字(self) -> None:
        # 实测 p51 表头被读成「易日期 对方账号」，仍应认出是表头
        assert looks_like_header(["易日期", "对方账号", "金额"]) is True

    def test_全短非数值标签当表头(self) -> None:
        assert looks_like_header(["模块", "参数项名称", "输入项"]) is True

    def test_首行是数据时插空表头且不丢行(self) -> None:
        html = _table([["1", "20170201", "100.00"], ["2", "20170202", "200.00"]])
        table = parse_table(html)
        assert table is not None and table.has_header is False

        lines = table.render().splitlines()
        assert lines[0] == "|  |  |  |"
        assert lines[1] == "| --- | --- | --- |"
        assert lines[2] == "| 1 | 20170201 | 100.00 |"
        assert lines[3] == "| 2 | 20170202 | 200.00 |"

    def test_账号证件号长数字否决表头(self) -> None:
        assert looks_like_header(["*姓名", "某甲", "*证件号码", "110101199001011234"]) is False

    def test_字段名冒号值形态否决表头(self) -> None:
        # 「日期:2017年1月」是表单里的一格数据，不是列名（数字不足 6 位，靠冒号形态否决）
        assert looks_like_header(["日期:2017年1月", "金额:100元"]) is False

    def test_纯数字首格否决表头(self) -> None:
        assert looks_like_header(["1", "案例名称", "某住宅"]) is False

    def test_半数长文本格否决表头(self) -> None:
        assert looks_like_header(["物业名称", "某某市某某区某某街道某某社区某某路1号某某栋1202房"]) is False

    def test_表题粘进首格仍认表头(self) -> None:
        """实测流水表 p52/p62/p63：一格长（表题+列名粘连）、其余都是列名。

        否决它会把诉请金额所在的流水表表头丢掉，所以长格占比门槛取「半数」而不是「有一格就否决」。
        """
        cells = ["某某银行活期账户交易明细表: 易日期 对方账号", "摘要", "发生额", "当前余额", "交易卡号"]
        assert looks_like_header(cells) is True

    def test_空行不算表头(self) -> None:
        assert looks_like_header(["", ""]) is False


class TestWideTableDegradation:
    def test_超过列数上限降级为按行纯文本(self, caplog: pytest.LogCaptureFixture) -> None:
        cols = MAX_GFM_COLUMNS + 1
        html = _table([[f"格{r}-{c}" for c in range(cols)] for r in range(2)])
        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            table = parse_table(html)

        assert table is not None and table.plain_lines is not None
        assert "|" not in table.render(), "降级后不该再有怪兽表格行"
        assert table.render().splitlines()[0].startswith("格0-0 格0-1")
        assert f"格1-{cols - 1}" in table.render(), "末列内容不能丢"
        assert "降级" in caplog.text

    def test_上限内的宽表仍走GFM(self) -> None:
        html = _table([[f"列{c}" for c in range(MAX_GFM_COLUMNS)]])
        table = parse_table(html)
        assert table is not None and table.plain_lines is None
        assert table.render().startswith("|")


class TestYearCrossCheck:
    """表格年份大比例异常 + 同页纯文本年份正常 → 降级；同源同坏则不降级。"""

    @staticmethod
    def _year_table(years: list[int]) -> str:
        return _table([["日期", "金额"], *[[f"{year}年1月", "100.00"] for year in years]])

    def test_表格坏年份_纯文本好年份_降级(self) -> None:
        html = self._year_table(list(range(2700, 2712)))
        page_text = " ".join(f"{year}年1月" for year in range(2017, 2029))
        table = parse_table(html, page_text=page_text)

        assert table is not None and table.plain_lines is not None
        assert "2700年1月" in table.render()

    def test_纯文本与表格同源同坏时不降级(self) -> None:
        """MinerU 的 page.text 就是 table_body 去标签来的（实测 p151 逐字相同）。

        同源数据一样坏时拿不出独立证据，不能降级。
        """
        years = list(range(2700, 2712))
        html = self._year_table(years)
        page_text = " ".join(f"{year}年1月" for year in years)

        assert table_years_unreliable(html, page_text, current_year=2026) is False
        assert parse_table(html, page_text=page_text).plain_lines is None  # type: ignore[union-attr]

    def test_年份样本不足不降级(self) -> None:
        html = self._year_table([2700, 2701, 2702])
        page_text = " ".join(f"{year}年1月" for year in range(2017, 2029))
        assert table_years_unreliable(html, page_text, current_year=2026) is False

    def test_个别错字不降级(self) -> None:
        years = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2700]
        html = self._year_table(years)
        page_text = " ".join(f"{year}年1月" for year in years)
        assert table_years_unreliable(html, page_text, current_year=2026) is False

    def test_纯文本年份样本不足不降级(self) -> None:
        html = self._year_table(list(range(2700, 2712)))
        assert table_years_unreliable(html, "2017年1月", current_year=2026) is False


class TestFooterRows:
    def test_HTML表格里的页脚行被剔除(self) -> None:
        html = _table(
            [
                ["交易日期", "金额"],
                ["20170201", "100.00"],
                ["打印日期:20170720", "第2页"],
            ]
        )
        rendered = _render(html)

        assert "打印日期" not in rendered and "第2页" not in rendered
        assert "| 20170201 | 100.00 |" in rendered, "数据行不能连坐"

    def test_全是日期的数据行不被误删(self) -> None:
        assert is_footer_row(["20170201", "20170202"]) is False
        assert is_footer_row(["日期：20170822", "第6页"]) is True
        assert is_footer_row(["打印日期:20170720 第2页"]) is True

    def test_纯文本夹带的表格行同样剔页脚(self) -> None:
        """VL OCR 兜底页直接返回 GFM 文本（实测 p55/p69），页脚藏在纯文本里。"""
        text = "| 日期：20170822 |  | 第6页 |  |  |\n| 20170201 | 100.00 |\n普通正文行"
        cleaned = drop_footer_table_lines(text)

        assert "第6页" not in cleaned
        assert "| 20170201 | 100.00 |" in cleaned
        assert "普通正文行" in cleaned

    def test_无竖线文本原样返回(self) -> None:
        assert drop_footer_table_lines("打印日期:20170720 第2页") == "打印日期:20170720 第2页"

    def test_GFM行切格忽略转义竖线(self) -> None:
        assert split_gfm_row("| 借\\|条 | 100.00 |") == ["借\\|条", "100.00"]


class TestContinuationMerge:
    @staticmethod
    def _stmt(rows: list[list[str]], *, header: bool) -> GfmTable:
        html = _table(([["交易日期", "金额"], *rows]) if header else rows)
        table = parse_table(html)
        assert table is not None
        return table

    def test_列数相同且首行非表头时合并(self) -> None:
        prev = self._stmt([["20170201", "100.00"]], header=True)
        nxt = self._stmt([["20170202", "200.00"]], header=False)

        assert merge_continuation(prev, nxt) is True
        assert prev.header == ["交易日期", "金额"]
        assert prev.rows == [["20170201", "100.00"], ["20170202", "200.00"]]
        lines = prev.render().splitlines()
        assert len(lines) == 4 and lines[1] == "| --- | --- |", "合并后仍是一张表（一行表头）"

    def test_列数不同不合并(self) -> None:
        prev = self._stmt([["20170201", "100.00"]], header=True)
        nxt = parse_table(_table([["持证人", "某甲", "登记日期"]]))
        assert nxt is not None
        assert merge_continuation(prev, nxt) is False

    def test_下一页首行是表头时视为新表(self) -> None:
        prev = self._stmt([["20170201", "100.00"]], header=True)
        nxt = self._stmt([["20170202", "200.00"]], header=True)
        assert merge_continuation(prev, nxt) is False

    def test_降级表不参与合并(self) -> None:
        prev = GfmTable(width=31, plain_lines=["一行纯文本"])
        nxt = self._stmt([["20170202", "200.00"]], header=False)
        assert merge_continuation(prev, nxt) is False

    def test_续表无数据行不合并(self) -> None:
        prev = self._stmt([["20170201", "100.00"]], header=True)
        nxt = GfmTable(width=2, header=["", ""], rows=[], has_header=False)
        assert merge_continuation(prev, nxt) is False

    def test_只渲染数据行(self) -> None:
        nxt = self._stmt([["20170202", "200.00"]], header=False)
        assert nxt.render_rows_only() == "| 20170202 | 200.00 |"
