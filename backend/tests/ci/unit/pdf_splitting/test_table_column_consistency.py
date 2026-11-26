"""表格「列数一致性」判据。

## 这条判据是怎么来的（别当它是拍脑袋加的）

2026-11-26 拿 OXR 与 MinerU 在同一批银行流水上对照时，发现我们原来的口径
（**单元格总数**）是错的：

- p57：OXR 51 行 × 4 列 = 204 格，MinerU **0 格**（整页糊成三行）；
- p66：MinerU 54 行 × 7 列 = 378 格，OXR 只有 4 列。

按"格子多"算 MinerU 赢，但**真实流水是 5 列以上** —— 4 列意味着并了列，而并列会让
数字挂到错误表头下（余额被当成发生额）。单元格总数对这种错误完全免疫。

所以判据改成「同一份流水的**相邻页**列数应当一致」：突变只有两种可能（换模板 / 引擎并拆列），
两种都该交人工。只比相邻页而不是全卷众数：一份卷宗里合同、流水、审批表混排，
全局众数只会天天误报。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.pdf_splitting.services.split import table_geometry_pass
from apps.pdf_splitting.services.split.table_geometry import DENSE_TABLE_MIN_ROWS, column_count_anomalies


class TestColumnCountAnomalies:
    def test_列数一致时不报(self) -> None:
        samples = [(57, 51, 4), (58, 50, 4), (59, 51, 4)]
        assert column_count_anomalies(samples) == []

    def test_相邻密表列数突变就报(self) -> None:
        """实测形态：同一份流水的连续两页，一页 4 列、下一页 3 列（列被并了）。"""
        samples = [(57, 51, 4), (58, 50, 3)]
        out = column_count_anomalies(samples)
        assert out == [{"page_no": 58, "prev_page_no": 57, "cols": 3, "prev_cols": 4}]

    def test_不相邻的两页抓不到_这是已知边界(self) -> None:
        """实测里 p57 是 4 列、p59 是 3 列，但这两页**不相邻**，本判据不会响。

        生产上 58 页也在同一批测量里，所以只要 57/58/59 是连续流水页就会被抓到；
        **但如果中间夹了别的材料（或那页没量到表），这条判据就会漏报**——这是
        刻意选的保守边界：跨断层比较会把"换了文档"当成"引擎并了列"，天天误报。
        真要兜住这种漏报，得靠 L0 跨页一致性的其它判据，不要指望这一条。
        """
        assert column_count_anomalies([(57, 51, 4), (59, 51, 3)]) == []

    def test_稀疏表不参与比对(self) -> None:
        """三五行的审批表/签字块，列数本来就可以各不相同。"""
        sparse = DENSE_TABLE_MIN_ROWS - 1
        samples = [(20, sparse, 6), (21, sparse, 2)]
        assert column_count_anomalies(samples) == []

    def test_一侧稀疏一侧密表也不报(self) -> None:
        """流水页后面跟一张小表单：不是同一张表，列数不同很正常。"""
        samples = [(57, 51, 4), (58, 3, 9)]
        assert column_count_anomalies(samples) == []

    def test_不连续页不比对(self) -> None:
        """中间夹了别的材料（p57 → p60），差异可能只是换了文档，不该报。"""
        samples = [(57, 51, 4), (60, 50, 7)]
        assert column_count_anomalies(samples) == []

    def test_多页连续突变逐条记录且按页号升序(self) -> None:
        samples = [(66, 50, 4), (65, 51, 3), (67, 51, 5)]
        out = column_count_anomalies(samples)
        assert [item["page_no"] for item in out] == [66, 67]

    def test_空输入不炸(self) -> None:
        assert column_count_anomalies([]) == []


def _artifact(pages: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """最小产物：``{页号: {"tables": {...}}}``，tables 里只要 rows/cols。"""
    return {
        "pages": {
            str(page): {
                "tables": {"0": {"rows": rows, "cols": cols, "cells": [], "diagnostics": {"cross_page": False}}},
                "skipped": {},
            }
            for page, (rows, cols) in pages.items()
        }
    }


class TestSummaryWiring:
    def test_汇总里落下异常页与计数(self) -> None:
        artifact = _artifact({57: (51, 4), 58: (50, 4), 59: (51, 3)})
        summary: dict[str, Any] = {
            "pages_total": 3,
            "pages_failed": 0,
            "pages_skipped": 0,
            "reason_counts": {},
            "page_reason_counts": {},
            "duration_ms": 0,
        }
        from collections import Counter

        table_geometry_pass._finish_summary(
            summary, artifact=artifact, reasons=Counter(), processed={57, 58, 59}, started=0.0
        )
        assert summary["column_anomaly_pages"] == [59]
        assert summary["column_anomalies"][0]["prev_cols"] == 4

    def test_没有表格的页不进比对也不会炸(self) -> None:
        artifact = {
            "pages": {
                "57": {"tables": {}, "skipped": {}},
                "58": {"tables": {"0": {"rows": 51, "cols": 4, "cells": [], "diagnostics": {"cross_page": False}}}},
            }
        }
        summary: dict[str, Any] = {
            "pages_total": 2,
            "pages_failed": 0,
            "pages_skipped": 0,
            "reason_counts": {},
            "page_reason_counts": {},
            "duration_ms": 0,
        }
        from collections import Counter

        table_geometry_pass._finish_summary(
            summary, artifact=artifact, reasons=Counter(), processed={57, 58}, started=0.0
        )
        assert summary["column_anomalies"] == []

    def test_形状固定_开关关着也有两个键(self) -> None:
        """与 engine_disagreements 同一纪律：键时有时无会让前端为每种情况写分支。"""
        block = table_geometry_pass.summary_block(None, enabled=False)
        assert block["column_anomalies"] == []
        assert block["column_anomaly_pages"] == []

    def test_阈值边界_等于阈值算密表(self) -> None:
        assert column_count_anomalies([(1, DENSE_TABLE_MIN_ROWS, 4), (2, DENSE_TABLE_MIN_ROWS, 5)]) != []

    def test_阈值边界_差一行不算密表(self) -> None:
        sparse = DENSE_TABLE_MIN_ROWS - 1
        assert column_count_anomalies([(1, sparse, 4), (2, sparse, 5)]) == []
