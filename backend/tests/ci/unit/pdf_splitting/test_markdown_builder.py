"""Tests for pdf_splitting 分段 Markdown 重建与 job_service 的 content_md 透出。"""

from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from apps.pdf_splitting.services.job_service import load_segments_md
from apps.pdf_splitting.services.split.markdown_builder import build_segment_markdown, build_segments_markdown
from apps.pdf_splitting.services.split.md_table import parse_table
from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft


def _page(
    page_no: int, text: str = "", *, layout: dict[str, Any] | None = None, ocr_failed: bool = False
) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text=text,
        normalized_text=text,
        head_text=text[:240],
        source_method="ocr",
        ocr_failed=ocr_failed,
        top_candidates=[],
        layout=layout,
        layout_title="",
    )


class TestBuildSegmentMarkdown:
    def test_版面块重建标题段落与表格(self) -> None:
        layout = {
            "blocks": [
                {"type": "title", "text": "证据清单"},
                {"type": "text", "text_level": 1, "text": "一、借款合同"},
                {"type": "text", "text": "证明借贷关系成立。"},
                {
                    "type": "table",
                    "text": "交易日期 金额",
                    "table_body": "<table><tr><td>交易日期</td><td>金额</td></tr><tr><td>2024-01-01</td><td>100,000</td></tr></table>",
                },
                {"type": "header", "text": "页眉噪音"},
                {"type": "image", "text": ""},
            ]
        }
        md = build_segment_markdown("证据清单及明细", [_page(1, layout=layout)])
        lines = md.splitlines()
        assert lines[0] == "# 证据清单及明细"
        assert "## 证据清单" in lines
        assert "## 一、借款合同" in lines  # text_level=1 → 段内标题 H2
        assert "证明借贷关系成立。" in lines
        assert "| 交易日期 | 金额 |" in lines
        assert "| --- | --- |" in lines
        assert "| 2024-01-01 | 100,000 |" in lines
        assert "页眉噪音" not in md

    def test_text_level_逐级映射且钳位(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": 3, "text": "三级"}]}
        assert "#### 三级" in build_segment_markdown("t", [_page(1, layout=layout)])
        deep = {"blocks": [{"type": "text", "text_level": 9, "text": "太深"}]}
        assert "###### 太深" in build_segment_markdown("t", [_page(1, layout=deep)])

    def test_无版面时退回页原文_页间空行(self) -> None:
        md = build_segment_markdown("起诉状", [_page(1, "原告张三。"), _page(2, "此致\n人民法院")])
        assert md == "# 起诉状\n\n原告张三。\n\n此致\n人民法院\n"

    def test_表格解析失败退回块文本(self) -> None:
        layout = {"blocks": [{"type": "table", "text": "交易明细 甲 乙", "table_body": "<div>not a table</div>"}]}
        assert "交易明细 甲 乙" in build_segment_markdown("t", [_page(1, layout=layout)])
        assert "|" not in build_segment_markdown("t", [_page(1, layout=layout)])

    def test_单元格竖线转义与短行补齐(self) -> None:
        table = parse_table("<table><tr><td>类型</td><td>备注</td></tr><tr><td>借|条</td></tr></table>")
        assert table is not None
        lines = table.render().splitlines()
        assert lines[0] == "| 类型 | 备注 |"
        assert lines[2] == "| 借\\|条 |  |"  # 缺列补空、| 转义


class TestBuildSegmentsMarkdown:
    def test_按drafts生成_标题取文件名stem_含gap段(self) -> None:
        pages = [_page(1, "起诉状正文"), _page(2, "身份证复印件"), _page(3, "证据正文")]
        drafts = [
            SegmentDraft(
                order=1,
                page_start=1,
                page_end=1,
                segment_type="complaint",
                filename="起诉状.pdf",
                confidence=0.9,
                source_method="llm",
                review_flag="normal",
            ),
            SegmentDraft(
                order=2,
                page_start=2,
                page_end=2,
                segment_type="unrecognized",
                filename="未识别材料_2-2.pdf",
                confidence=0.0,
                source_method="gap_fill",
                review_flag="unrecognized",
            ),
            SegmentDraft(
                order=3,
                page_start=3,
                page_end=3,
                segment_type="evidence_list",
                filename="证据清单.pdf",
                confidence=0.8,
                source_method="llm",
                review_flag="normal",
            ),
        ]
        results = build_segments_markdown(drafts, pages)
        assert [r["order"] for r in results] == [1, 2, 3]
        assert results[0]["markdown"].startswith("# 起诉状\n")
        assert results[1]["markdown"].startswith("# 未识别材料_2-2\n")
        assert results[2]["page_start"] == 3 and results[2]["page_end"] == 3


def _draft(order: int, page_start: int, page_end: int, filename: str = "材料.pdf") -> SegmentDraft:
    return SegmentDraft(
        order=order,
        page_start=page_start,
        page_end=page_end,
        segment_type="evidence_list",
        filename=filename,
        confidence=0.9,
        source_method="llm",
        review_flag="normal",
    )


def _table_block(body: str, text: str = "交易明细") -> dict[str, Any]:
    return {"type": "table", "text": text, "table_body": body}


class TestPageSpans:
    """跨模块契约：``page_spans`` 是前端按页切分/搬运 md 的唯一依据。

    不变量：``markdown[span["start"]:span["end"]]`` 恰好等于该页重建出的正文
    （左闭右开、只含产出非空内容的页、不含注入的段标题）。
    """

    def test_多页偏移按最终字符串精确计算(self) -> None:
        pages = [_page(1, "第一页正文"), _page(2, "第二页正文")]
        entry = build_segments_markdown([_draft(1, 1, 2)], pages)[0]
        md = entry["markdown"]

        assert md == "# 材料\n\n第一页正文\n\n第二页正文\n"
        assert entry["page_spans"] == [
            {"page": 1, "start": 6, "end": 11},
            {"page": 2, "start": 13, "end": 18},
        ]
        assert md[6:11] == "第一页正文"
        assert md[13:18] == "第二页正文"

    def test_注入标题不计入偏移(self) -> None:
        entry = build_segments_markdown([_draft(1, 1, 1)], [_page(1, "正文")])[0]
        span = entry["page_spans"][0]

        assert entry["markdown"][: span["start"]] == "# 材料\n\n"
        assert entry["markdown"][span["start"] : span["end"]] == "正文"

    def test_空页不产出span(self) -> None:
        pages = [_page(1, "第一页"), _page(2, ""), _page(3, "第三页")]
        entry = build_segments_markdown([_draft(1, 1, 3)], pages)[0]

        assert [s["page"] for s in entry["page_spans"]] == [1, 3]
        for span, expected in zip(entry["page_spans"], ["第一页", "第三页"], strict=True):
            assert entry["markdown"][span["start"] : span["end"]] == expected

    def test_页内多块的偏移含块间空行(self) -> None:
        layout = {"blocks": [{"type": "text", "text": "甲"}, {"type": "text", "text": "乙"}]}
        entry = build_segments_markdown([_draft(1, 1, 1)], [_page(1, layout=layout)])[0]
        span = entry["page_spans"][0]

        assert entry["markdown"][span["start"] : span["end"]] == "甲\n\n乙"

    def test_标题去重后偏移仍精确(self) -> None:
        layout = {"blocks": [{"type": "title", "text": "借款合同"}, {"type": "text", "text": "正文"}]}
        entry = build_segments_markdown([_draft(1, 1, 1, "借款合同.pdf")], [_page(1, layout=layout)])[0]
        md = entry["markdown"]

        assert md == "## 借款合同\n\n正文\n", "段名与文档首标题同名时不再重复注入"
        span = entry["page_spans"][0]
        assert span["start"] == 0
        assert md[span["start"] : span["end"]] == "## 借款合同\n\n正文"

    def test_无正文时只有标题且无span(self) -> None:
        entry = build_segments_markdown([_draft(1, 1, 1)], [_page(1, "")])[0]

        assert entry["markdown"] == "# 材料\n"
        assert entry["page_spans"] == []

    def test_跨页续表合并后的偏移口径(self) -> None:
        """续表行并到上一张表后，本页贡献的就是接在表尾的那几行（仍是连续区间）。"""
        page1 = _page(
            1,
            layout={
                "blocks": [
                    _table_block(
                        "<table><tr><td>交易日期</td><td>金额</td></tr>"
                        "<tr><td>20170201</td><td>100.00</td></tr></table>"
                    )
                ]
            },
        )
        page2 = _page(
            2,
            layout={"blocks": [_table_block("<table><tr><td>20170202</td><td>200.00</td></tr></table>")]},
        )
        entry = build_segments_markdown([_draft(1, 1, 2)], [page1, page2])[0]
        md = entry["markdown"]
        first, second = entry["page_spans"]

        assert md.count("| --- | --- |") == 1, "合并成一张表，不是两张"
        assert md[first["start"] : first["end"]] == ("| 交易日期 | 金额 |\n| --- | --- |\n| 20170201 | 100.00 |")
        assert md[second["start"] : second["end"]] == "| 20170202 | 200.00 |"
        # 续表行与上一表之间是单换行（空行会把 GFM 表切成两张）
        assert md[first["end"] : second["start"]] == "\n"

    def test_三页连续续表不重复渲染(self) -> None:
        """锚点表是原地扩充的：上一页必须在合并前定格，否则会把后续页的行重复输出。"""
        pages = [
            _page(
                1,
                layout={
                    "blocks": [
                        _table_block(
                            "<table><tr><td>交易日期</td><td>金额</td></tr>"
                            "<tr><td>20170201</td><td>100.00</td></tr></table>"
                        )
                    ]
                },
            ),
            _page(2, layout={"blocks": [_table_block("<table><tr><td>20170202</td><td>200.00</td></tr></table>")]}),
            _page(3, layout={"blocks": [_table_block("<table><tr><td>20170203</td><td>300.00</td></tr></table>")]}),
        ]
        entry = build_segments_markdown([_draft(1, 1, 3)], pages)[0]
        md = entry["markdown"]

        assert md.count("20170201") == 1
        assert md.count("20170202") == 1
        assert md.count("20170203") == 1
        assert sum(1 for ln in md.splitlines() if ln.startswith("| ---")) == 1
        for span, expected in zip(
            entry["page_spans"],
            [
                "| 交易日期 | 金额 |\n| --- | --- |\n| 20170201 | 100.00 |",
                "| 20170202 | 200.00 |",
                "| 20170203 | 300.00 |",
            ],
            strict=True,
        ):
            assert md[span["start"] : span["end"]] == expected

    def test_列数不同的跨页表不合并(self) -> None:
        page1 = _page(
            1,
            layout={"blocks": [_table_block("<table><tr><td>交易日期</td><td>金额</td></tr></table>")]},
        )
        page2 = _page(
            2,
            layout={"blocks": [_table_block("<table><tr><td>持证人</td><td>某甲</td><td>登记日期</td></tr></table>")]},
        )
        entry = build_segments_markdown([_draft(1, 1, 2)], [page1, page2])[0]
        md = entry["markdown"]

        assert sum(1 for ln in md.splitlines() if ln.startswith("| ---")) == 2
        assert md[entry["page_spans"][0]["end"] : entry["page_spans"][1]["start"]] == "\n\n"

    def test_各页区间互不重叠且覆盖全部正文(self) -> None:
        pages = [_page(1, "甲"), _page(2, "乙"), _page(3, "丙")]
        entry = build_segments_markdown([_draft(1, 1, 3)], pages)[0]
        md = entry["markdown"]
        spans = entry["page_spans"]

        assert md[spans[0]["start"] : spans[-1]["end"]] == "甲\n\n乙\n\n丙"
        for left, right in itertools.pairwise(spans):
            assert left["end"] <= right["start"]
            assert md[left["end"] : right["start"]] in {"\n", "\n\n"}


class TestMarkdownSanitization:
    def test_无版面页的原始HTML被净化(self) -> None:
        page = _page(1, '面谈笔录<img src="imgs/img_in_image_box_1_2_3_4.jpg"><div>正文</div>')
        md = build_segment_markdown("面谈笔录", [page])

        assert "<img" not in md and "<div" not in md
        assert "正文" in md
        assert "[图片]" not in md, "图片内容没 OCR 出来时不编造占位文字"

    def test_版面块文本里的HTML也被净化(self) -> None:
        layout = {"blocks": [{"type": "text", "text": "<div>第一条 借款</div>"}]}
        md = build_segment_markdown("合同", [_page(1, layout=layout)])

        assert "第一条 借款" in md and "<div" not in md

    def test_段名与文档首标题同名时不重复注入(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": 1, "text": "个人房产抵押贷款合同"}]}
        md = build_segment_markdown("个人房产抵押贷款合同", [_page(1, layout=layout)])

        assert md == "## 个人房产抵押贷款合同\n"

    def test_段名与首标题不同名时仍注入(self) -> None:
        layout = {"blocks": [{"type": "text", "text_level": 1, "text": "借款合同"}]}
        md = build_segment_markdown("个人房产抵押贷款合同", [_page(1, layout=layout)])

        assert md.startswith("# 个人房产抵押贷款合同\n\n## 借款合同")

    def test_超宽表格降级为按行纯文本(self) -> None:
        cols = 31
        body = (
            "<table>"
            + "".join("<tr>" + "".join(f"<td>格{r}-{c}</td>" for c in range(cols)) + "</tr>" for r in range(2))
            + "</table>"
        )
        md = build_segment_markdown("登记信息", [_page(1, layout={"blocks": [_table_block(body)]})])

        assert "| --- |" not in md
        assert "格0-0 格0-1" in md and f"格1-{cols - 1}" in md

    def test_表格内页脚行被剔除(self) -> None:
        body = (
            "<table><tr><td>交易日期</td><td>金额</td></tr>"
            "<tr><td>20170201</td><td>100.00</td></tr>"
            "<tr><td>打印日期:20170720</td><td>第2页</td></tr></table>"
        )
        md = build_segment_markdown("流水", [_page(1, layout={"blocks": [_table_block(body)]})])

        assert "打印日期" not in md and "第2页" not in md
        assert "| 20170201 | 100.00 |" in md

    def test_跨页重复印章核验语被滤而正文保留(self) -> None:
        pages = [
            _page(
                no,
                layout={
                    "blocks": [
                        {"type": "text", "text": "已核对与原件相符"},
                        {"type": "text", "text": f"正文第{no}段"},
                    ]
                },
            )
            for no in range(1, 5)
        ]
        md = build_segment_markdown("档案", pages)

        assert "已核对与原件相符" not in md
        for no in range(1, 5):
            assert f"正文第{no}段" in md

    def test_每页重复的条款行不被滤(self) -> None:
        """防「优化银行档案、劣化法院文书」：条款骨架每页重复也必须留下。"""
        pages = [
            _page(
                no,
                layout={"blocks": [{"type": "text", "text": "第一条 借款用途"}, {"type": "text", "text": f"正文{no}"}]},
            )
            for no in range(1, 5)
        ]
        md = build_segment_markdown("判决书", pages)

        assert md.count("第一条 借款用途") == 4


class TestStampBoilerplateEndToEnd:
    """短语锚定路端到端：版面块路径与单页段都要清掉印章套话（频次路够不到的缺口）。"""

    def test_单页段的印章套话被剔(self) -> None:
        layout = {
            "blocks": [
                {"type": "text", "text": "已核对与原件相符"},
                {"type": "text", "text": "借款人确认以上信息属实。"},
            ]
        }
        md = build_segment_markdown("面谈笔录", [_page(1, layout=layout)])

        assert "已核对与原件相符" not in md
        assert "借款人确认以上信息属实。" in md

    def test_单页段只剩套话时无正文也无页锚点(self) -> None:
        page = _page(1, "已核对与原件相符\n扫描件与留档资料相符\n经办人：测试甲 测试乙")
        entry = build_segments_markdown([_draft(1, 1, 1)], [page])[0]

        assert entry["markdown"] == "# 材料\n"
        assert entry["page_spans"] == []

    def test_经办人尾巴粘着权证正文时整行保留(self) -> None:
        text = "经办人：测试甲 测试乙根据《中华人民共和国物权法》等法律法规，准予登记，颁发此证。"
        md = build_segment_markdown("不动产权证", [_page(1, layout={"blocks": [{"type": "text", "text": text}]})])

        assert "准予登记，颁发此证。" in md

    def test_法院文书单页段零误剔(self) -> None:
        layout = {
            "blocks": [
                {"type": "text", "text": "本院认为"},
                {"type": "text", "text": "如不服本判决，可在判决书送达之日起十五日内上诉。"},
            ]
        }
        md = build_segment_markdown("民事判决书", [_page(1, layout=layout)])

        assert "本院认为" in md
        assert "如不服本判决" in md

    def test_表格行里的套话不动(self) -> None:
        body = (
            "<table><tr><td>交易日期</td><td>金额</td></tr>"
            "<tr><td>已核对与原件相符 经办人：测试甲</td><td></td></tr></table>"
        )
        md = build_segment_markdown("流水", [_page(1, layout={"blocks": [_table_block(body)]})])

        assert "已核对与原件相符" in md, "表格行受保护：剔它会破坏行列结构"

    def test_频次路仍然生效(self) -> None:
        """非套话词表的重复短行仍靠跨页频次路（两条路互补，不是替代）。"""
        pages = [
            _page(
                no, layout={"blocks": [{"type": "text", "text": "内部核对标记"}, {"type": "text", "text": f"正文{no}"}]}
            )
            for no in range(1, 5)
        ]
        md = build_segment_markdown("档案", pages)

        assert "内部核对标记" not in md
        assert "正文1" in md and "正文4" in md


class TestLoadSegmentsMd:
    def test_缺失文件回空表(self, tmp_path: Any) -> None:
        assert load_segments_md(tmp_path / "segments_md.json") == {}

    def test_正常读取按order建映射(self, tmp_path: Any) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "markdown": "# a"}, {"order": 2, "markdown": "# b"}], ensure_ascii=False),
            encoding="utf-8",
        )
        assert load_segments_md(path) == {1: "# a", 2: "# b"}

    def test_损坏或非列表载荷回空表(self, tmp_path: Any) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert load_segments_md(broken) == {}
        non_list = tmp_path / "non_list.json"
        non_list.write_text('{"order": 1}', encoding="utf-8")
        assert load_segments_md(non_list) == {}


class TestTableSplitIntoCells:
    """大表格拆格：一个框罩住十几行时，律师点不中具体某一格。

    真实痛点（p22，68 格表单）：整表 bbox 高 40% 页面，一个框盖住 17 行 × 4 列，
    想点「*房产证编号」那一格根本点不中。
    """

    @staticmethod
    def _html(rows: int, cols: int) -> str:
        body = "".join("<tr>" + "".join(f"<td>R{r}C{c}</td>" for c in range(cols)) + "</tr>" for r in range(rows))
        return f"<table>{body}</table>"

    def test_没有几何时不拆格_只留整表框(self) -> None:
        """PR-2 起默认**不再均分**：没有量到的几何就没有可点的格子。

        均分不可能用任何便宜判据证明可靠（列宽离散度拿不到），留着它等于留着一个
        已知会指错地方的路径（p10「件数」列偏 0.185 页宽 ≈ 110pt）。
        """
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        # 6 行 × 4 列 = 24 格，行数与格数都在门槛内 —— 旧实现会在这里拆成 24 个均分格
        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 200, 500, 800], "table_body": self._html(6, 4)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert [b["type"] for b in blocks] == ["table"]
        assert blocks[0]["rect"]["precision"] == "page"
        assert blocks[0]["table_rows"] == 6 and blocks[0]["table_cols"] == 4

    def test_回滚开关打开时仍按行列均分(self) -> None:
        """``legacy_uniform=True``（``PDF_SPLIT_TABLE_UNIFORM_FALLBACK=1``）恢复旧行为。"""
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 200, 500, 800], "table_body": self._html(6, 4)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru", legacy_uniform=True)
        cells = [b for b in blocks if b["type"] == "table_cell"]

        assert len(cells) == 24
        # 首格落在表格左上角，末格落在右下角
        assert cells[0]["rect"]["x"] == pytest.approx(0.1, abs=0.01)
        assert cells[0]["rect"]["y"] == pytest.approx(0.2, abs=0.01)
        assert cells[-1]["rect"]["y"] > cells[0]["rect"]["y"]
        # 均分推算 → 必须标 approx，不谎报精度
        assert all(c["rect"]["approx"] is True for c in cells)

    def test_中等表在行数门槛内仍拆到行不拆格(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        # 10 行 × 13 列 = 130 格：行数 ≤ 12 允许拆，但格数 > 120 只拆到行
        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 100, 900, 900], "table_body": self._html(10, 13)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru", legacy_uniform=True)
        rows = [b for b in blocks if b["type"] == "table_row"]
        cells = [b for b in blocks if b["type"] == "table_cell"]

        assert len(rows) == 10
        assert cells == []
        # 每行保留该行全部单元格文字
        assert rows[0]["text"].startswith("R0C0 R0C1 R0C2")

    def test_矮表格不拆保持原样(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        # 高度只占 8% 页面 → 低于拆格门槛，拆了反而让绿框密度过高
        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "表内容", "bbox": [100, 100, 900, 180], "table_body": self._html(2, 2)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert [b["type"] for b in blocks] == ["table"]

    def test_无表格结构时回退整块(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        # table_body 缺失（Textin 之类不给 HTML）→ 拆不出来，保留原整块
        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [{"type": "table", "text": "只有纯文本", "bbox": [100, 100, 900, 900]}],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert [b["type"] for b in blocks] == ["table"]

    def test_长表格整表保留并透出行列数(self) -> None:
        """行数超过门槛时整表一个块——均分坐标是编造的，不能拿去给律师点。

        真实痛点（p62，52 行银行流水）：原实现把表切成 52 个 ``table_row``，
        律师点中第 37 行实际高亮第 35 行（标题行/表头行更高，误差从头累积）。
        """
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 100, 900, 900], "table_body": self._html(52, 6)}
            ],
        }
        blocks = build_positioned_blocks([_page(62, layout=layout)], bbox_backend="mineru")

        assert [b["type"] for b in blocks] == ["table"]
        # 只保留整表真 bbox，不带任何推算出来的行/格
        assert blocks[0]["rect"]["x"] == pytest.approx(0.1)
        assert blocks[0]["rect"]["y"] == pytest.approx(0.1)
        # 结构信息透出：前端靠它告诉律师「这是一张 52 行 × 6 列的表」
        assert blocks[0]["table_rows"] == 52
        assert blocks[0]["table_cols"] == 6

    def test_稀疏表行数超标仍拆格(self) -> None:
        """稀疏表例外：有字格占比 < 30% 时行数多也允许拆。

        空行不承载内容、律师不会去点，且列宽均等，均分误差不叠加到横向。
        """
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        # 17 行 × 4 列 = 68 格位，只填前 12 格 → 有字率 17.6%，低于 30%
        rows = "".join(
            f"<tr>{'<td></td>' * 4}</tr>" if r >= 3 else f"<tr>{'<td>字段</td>' * 4}</tr>" for r in range(17)
        )
        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {
                    "type": "table",
                    "text": "x" * 100,
                    "bbox": [192, 154, 790, 554],
                    "table_body": f"<table>{rows}</table>",
                }
            ],
        }
        blocks = build_positioned_blocks([_page(22, layout=layout)], bbox_backend="mineru", legacy_uniform=True)
        cells = [b for b in blocks if b["type"] == "table_cell"]

        assert len(cells) == 12
        assert all(c["rect"]["precision"] == "cell" for c in cells)


class TestTableSplitTrustworthiness:
    """整页被误判成表格时不拆格——「框得不准」比「没有框」更糟。

    真实痛点（576 号材料包 p29/p30 结婚证，律师直接指着截图反馈「框不精确」）：
    这两页**整页就是一张扫描图**，MinerU 把它归成一个占满页面的 table 块，
    再按行列均分，得到 5 个高度 25%、宽度 46% 的格子 —— 比它要圈的那行字
    大一个数量级，落在页面上纯属误导。

    p29 与 p30 是同一毛病的两种形态，两条都必须挡住：

    | 页 | HTML 特征 | 靠哪条判据挡下 |
    |:--|:--|:--|
    | p29 | 格子里是 ``<img>``（证件照/印章） | 含图片 |
    | p30 | 纯文字，但 3 行塞下 166 字 | 每格字数过多 |

    如果只挡 ``<img>``（当初的第一版就是这么写的），p30 会继续画 5 个错位框。
    """

    #: p29 的 table_body：保留真实结构（rowspan + colspan + 两个 <img>），人名脱敏
    _P29 = (
        '<table><tr><td rowspan="2"><img src="images/eb8c.jpg"/></td>'
        '<td colspan="2">结婚申请,符合《中华人民共和国婚姻法》规定,予以登记,发给此证。</td></tr>'
        '<tr><td>登记机</td><td><img src="images/b0ba.jpg"/></td></tr>'
        "<tr><td>中华人民共和国民政部监制</td><td>婚姻登记员</td><td>某某</td></tr></table>"
    )

    #: p30 同形态 table_body：**没有 img**，3 行 6 格塞上百字。
    #:
    #: 只保留触发判据的**形态**（每格一整段字段文本，而不是一个字段值），
    #: 人名与证件号均为仅用于本测试的假数据。
    _P30 = (
        "<table>"  # privacy-allow
        "<tr><td>持证人张某 登记日期 2000年01月01日结婚证字号 J000000000-2000-000000备注</td><td></td></tr>"
        "<tr><td>姓名 张某 国籍 中国身份证件号 110101190001010000</td><td>性别男出生日期 1900年01月01日</td></tr>"
        "<tr><td>姓名 李某 国籍 中国身份证件号 110101190001010000</td><td>性别女出生日期 1900年01月01日</td></tr>"
        "</table>"  # privacy-allow
    )

    @staticmethod
    def _blocks(page_no: int, bbox: list[int], body: str, *, legacy_uniform: bool = False) -> list[Any]:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [{"type": "table", "text": "整页表格", "bbox": bbox, "table_body": body}],
        }
        return build_positioned_blocks(
            [_page(page_no, layout=layout)], bbox_backend="mineru", legacy_uniform=legacy_uniform
        )

    @classmethod
    def _blocks_uniform(cls, page_no: int, bbox: list[int], body: str) -> list[Any]:
        """同上，但走回滚开关（旧均分路径）——用来证明闸门本身没被改松/改紧。"""
        return cls._blocks(page_no, bbox, body, legacy_uniform=True)

    def test_p29_格子里有图片时整页不拆(self) -> None:
        blocks = self._blocks(29, [19, 9, 960, 818], self._P29)

        # 只有一个整块，绝不出现 5 个 25%×46% 的格子
        assert [b["type"] for b in blocks] == ["table"]
        assert [b for b in blocks if b["type"] == "table_cell"] == []

    def test_p30_每格塞整段正文时不拆(self) -> None:
        # 这页没有 <img>，只能靠「格子里字数太多」这条判据 —— 正是它当初漏掉的
        blocks = self._blocks(30, [47, 4, 988, 821], self._P30)

        assert [b["type"] for b in blocks] == ["table"]
        assert [b for b in blocks if b["type"] == "table_cell"] == []

    def test_退回整块时标_approx_不谎报精确(self) -> None:
        # 整块框是「整页内容外接框」，不是某块字的精确位置，前端要画虚线
        assert self._blocks(30, [47, 4, 988, 821], self._P30)[0]["rect"]["approx"] is True

    def test_单行表格不横拆(self) -> None:
        # p147 宗地图：[WDZ7] 一个格子，拆出来等于把 1 行文字按列数编造横坐标
        body = "<table><tr><td>[WDZ7]</td></tr></table>"
        assert self._blocks(147, [27, 8, 960, 818], body)[0]["type"] == "table"

    def test_长正文假表格不拆(self) -> None:
        # p106 合同正文：35 行 rowspan 全跨成一个大格，不是表格
        body = (
            '<table><tr><td rowspan="35" colspan="2">'
            + "五、甲方决定中途不卖或逾期____天仍未交付房地产时," * 8
            + "</td></tr></table>"
        )
        blocks = self._blocks(106, [35, 34, 929, 797], body)
        assert [b["type"] for b in blocks] == ["table"]

    def test_行数门槛内的真表单仍然拆格(self) -> None:
        """守住原有能力：判据不能把短表单一起挡掉。

        12 行以内的真表单，律师确实要逐格点，列宽均等时纵向误差也在 1 行内。
        """
        rows = "".join(f"<tr><td>押品信息</td><td>字段{r}</td><td>输入项</td><td>暂无</td></tr>" for r in range(10))
        blocks = self._blocks_uniform(22, [192, 154, 790, 554], f"<table>{rows}</table>")
        cells = [b for b in blocks if b["type"] == "table_cell"]

        assert len(cells) == 40
        # 单格只占页面 1% 量级 —— 这才是「点得中某一格」的粒度
        assert max(c["rect"]["w"] * c["rect"]["h"] for c in cells) < 0.02


class TestPrecisionField:
    """``precision`` 拆开 ``approx`` 混用的两种语义（整页近似 vs 半格误差）。

    ``approx`` 同时表示「整页近似框」与「表格均分的半格误差框」，前端只能
    按最保守的一种统一处理，于是半格框也被当成整页框弱化。三档分开后，
    前端才能给 ``exact`` 画实线、``cell`` 画虚线、``page`` 画整页提示。
    """

    @staticmethod
    def _html(rows: int, cols: int) -> str:
        body = "".join("<tr>" + "".join(f"<td>R{r}C{c}</td>" for c in range(cols)) + "</tr>" for r in range(rows))
        return f"<table>{body}</table>"

    def test_真实bbox的正文块标_exact(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [{"type": "text", "text": "企业信用报告", "bbox": [100, 100, 500, 140]}],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert blocks[0]["rect"]["precision"] == "exact"
        # exact 仍带 approx=False——老前端读 approx 画实线，与 precision 一致
        assert blocks[0]["rect"]["approx"] is False

    def test_均分回滚路径的格子标_cell(self) -> None:
        """``cell`` 现在只在回滚开关打开时出现（默认走 ``grid`` 或整表框 ``page``）。"""
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 100, 900, 900], "table_body": self._html(6, 4)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru", legacy_uniform=True)

        assert all(b["rect"]["precision"] == "cell" for b in blocks)
        assert all(b["rect"]["approx"] is True for b in blocks)

    def test_整表未拆标_page(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "x" * 100, "bbox": [100, 100, 900, 900], "table_body": self._html(52, 6)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert blocks[0]["rect"]["precision"] == "page"
        assert blocks[0]["rect"]["approx"] is True

    def test_矮表格整块保留也标_page(self) -> None:
        """没到拆格高度门槛的矮表格：坐标可信但未拆分，算「整表一个块」。"""
        from apps.pdf_splitting.services.split.markdown_builder import build_positioned_blocks

        layout = {
            "width": 1000,
            "height": 1000,
            "blocks": [
                {"type": "table", "text": "表内容", "bbox": [100, 100, 900, 180], "table_body": self._html(2, 2)}
            ],
        }
        blocks = build_positioned_blocks([_page(1, layout=layout)], bbox_backend="mineru")

        assert blocks[0]["rect"]["precision"] == "page"
        # 整表未拆才带结构字段：前端据此告诉律师「这是 2 行 × 2 列的表」
        assert blocks[0]["table_rows"] == 2
        assert blocks[0]["table_cols"] == 2
