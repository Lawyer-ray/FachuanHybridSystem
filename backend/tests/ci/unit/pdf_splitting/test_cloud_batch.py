"""云端分批解析的单元测试。

背景：某个 164 页扫描卷宗任务整本一次性交给 MinerU，进程中途一死就
把 135 页成果全部归零，连续两次死在同位置。分批 + 每批落盘是根治办法。

这里锁住四条不变量：
1. 页号必须按**连续区间**切（否则切片与页码换算会错）；
2. 稀疏页号不能把无关页夹进批次；
3. 单批失败不能拖垮其他批（其他批的成果必须照常落盘）；
4. 页码必须映射回**原始页号**而不是小 PDF 内的相对页号。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.pdf_splitting.services.split import cloud_batch


class TestPlanBatches:
    def test_contiguous_pages_split_by_size(self) -> None:
        batches = cloud_batch.plan_batches(list(range(1, 165)), size=40)
        assert [[b[0], b[-1]] for b in batches] == [
            [1, 40],
            [41, 80],
            [81, 120],
            [121, 160],
            [161, 164],
        ]

    def test_every_page_appears_exactly_once(self) -> None:
        pages = list(range(1, 165))
        flat = [page for batch in cloud_batch.plan_batches(pages, size=40) for page in batch]
        assert sorted(flat) == pages

    def test_sparse_pages_never_mix_disjoint_runs(self) -> None:
        """稀疏页号必须按连续段分组——把 3 和 5 放进同一批会夹进第 4 页，
        而第 4 页可能根本不需要云端解析，页码映射随之错位。"""
        batches = cloud_batch.plan_batches([1, 2, 3, 5, 6, 9], size=2)
        assert batches == [[1, 2], [3], [5, 6], [9]]

    def test_empty_input(self) -> None:
        assert cloud_batch.plan_batches([]) == []

    def test_duplicate_pages_deduped(self) -> None:
        assert cloud_batch.plan_batches([1, 1, 2, 2], size=10) == [[1, 2]]

    @pytest.mark.parametrize("size", [1, 7, 40, 1000])
    def test_size_never_loses_pages(self, size: int) -> None:
        pages = list(range(1, 101))
        flat = [p for batch in cloud_batch.plan_batches(pages, size=size) for p in batch]
        assert sorted(flat) == pages


class TestSlicePdfGuard:
    def test_rejects_non_contiguous(self, tmp_path: Path) -> None:
        """切片函数必须自己守住连续性，不能只靠 plan_batches。"""
        with pytest.raises(ValueError, match="连续"):
            cloud_batch.slice_pdf(tmp_path / "x.pdf", [1, 3])

    def test_rejects_empty(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            cloud_batch.slice_pdf(tmp_path / "x.pdf", [])


class TestParseInBatches:
    def test_page_numbers_map_back_to_original(self) -> None:
        """最关键的一条：第 2 批（41-80）返回的相对页 1 必须映射成原始页 41。"""
        seen: dict[int, Any] = {}

        def fake_slice(_source: Path, pages: list[int]) -> bytes:
            # 把本批页号编码进返回值，供 parse_one 反推
            fake_slice.current = pages  # type: ignore[attr-defined]
            return b"pdf"

        def parse_one(_path: Path) -> dict[int, Any]:
            pages = fake_slice.current  # type: ignore[attr-defined]
            # 小 PDF 内的相对页 1..n
            return {index + 1: f"text@{original}" for index, original in enumerate(pages)}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cloud_batch, "slice_pdf", fake_slice)
            result = cloud_batch.parse_in_batches(
                source_path=Path("dummy.pdf"),
                page_numbers=[1, 2, 3, 4, 5, 6],
                parse_one=parse_one,
                on_batch_done=lambda _b, mapped: seen.update(mapped),
                size=3,
                concurrency=1,
            )

        assert sorted(result) == [1, 2, 3, 4, 5, 6]
        # 值里带着原始页号，证明映射没错位
        assert result[4] == "text@4"
        assert result[6] == "text@6"

    def test_one_failed_batch_does_not_discard_others(self) -> None:
        """单批失败必须只丢那一批，已成功批次的成果要照常回调落盘。"""
        done: dict[int, Any] = {}

        def fake_slice(_source: Path, pages: list[int]) -> bytes:
            fake_slice.current = pages  # type: ignore[attr-defined]
            return b"pdf"

        def parse_one(_path: Path) -> dict[int, Any]:
            pages = fake_slice.current  # type: ignore[attr-defined]
            if pages[0] == 4:  # 第二批炸掉
                raise RuntimeError("mineru down")
            return {index + 1: f"text@{original}" for index, original in enumerate(pages)}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cloud_batch, "slice_pdf", fake_slice)
            result = cloud_batch.parse_in_batches(
                source_path=Path("dummy.pdf"),
                page_numbers=[1, 2, 3, 4, 5, 6],
                parse_one=parse_one,
                on_batch_done=lambda _b, mapped: done.update(mapped),
                size=3,
                concurrency=1,
            )

        # 第一批活着并落盘
        assert 1 in result and 1 in done
        # 第二批（4-6）没了，但没影响第一批
        assert 4 not in result

    def test_progress_reports_resolved_counts(self) -> None:
        progress: list[tuple[int, int]] = []

        def fake_slice(_source: Path, pages: list[int]) -> bytes:
            fake_slice.current = pages  # type: ignore[attr-defined]
            return b"pdf"

        def parse_one(_path: Path) -> dict[int, Any]:
            pages = fake_slice.current  # type: ignore[attr-defined]
            return {index + 1: "x" for index in range(len(pages))}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cloud_batch, "slice_pdf", fake_slice)
            cloud_batch.parse_in_batches(
                source_path=Path("dummy.pdf"),
                page_numbers=[1, 2, 3, 4],
                parse_one=parse_one,
                on_progress=lambda r, t: progress.append((r, t)),
                size=2,
                concurrency=1,
            )

        # 两批 → 两条进度，最终 resolved == total
        assert progress[-1] == (4, 4)
