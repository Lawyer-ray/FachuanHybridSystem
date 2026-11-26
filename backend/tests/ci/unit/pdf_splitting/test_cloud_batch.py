"""云端分批解析的单元测试。

背景：某个 164 页扫描卷宗任务整本一次性交给 MinerU，进程中途一死就
把 135 页成果全部归零，连续两次死在同位置。分批 + 每批落盘是根治办法。

这里锁住四条不变量：
1. 页号必须按**连续区间**切（否则切片与页码换算会错）；
2. 稀疏页号不能把无关页夹进批次；
3. 单批失败不能拖垮其他批（其他批的成果必须照常落盘）；
4. 页码必须映射回**原始页号**而不是小 PDF 内的相对页号。

第二批不变量（2026-11-25，网关 48 MiB 硬上限）：
5. 切批同时受**页数**与**字节**约束——任何一批都不得超过上限；
6. 单页本身超限时独占一批并告警，**不静默丢页**；
7. 页数上限内的批只切一刀（超限才二分，不为每个批全量重切）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pymupdf as fitz
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


def _make_heavy_pdf(path: Path, *, pages: int, side: int = 600) -> Path:
    """造一份「页数少但体积大」的 PDF：每页塞一张**不可压缩**的随机像素图。

    这是手机高清拍照件的形态（2–3 MiB/页）。随机像素用 deflate 压不动，
    所以每页体积 ≈ ``side × side × 3`` 字节，测试阈值可以按页精确标定。
    """
    with fitz.open() as doc:
        for _ in range(pages):
            page = doc.new_page()
            pix = fitz.Pixmap(fitz.csRGB, side, side, os.urandom(side * side * 3), 0)
            page.insert_image(page.rect, pixmap=pix)
        doc.save(path.as_posix())
    return path


def _page_count_parser(uploads: list[tuple[int, int]]) -> Any:
    """`parse_one` 桩：记录每段上传体（字节数, 页数），并对每页都返回正文。"""

    def parse_one(mini_path: Path) -> dict[int, Any]:
        with fitz.open(mini_path) as doc:
            count = doc.page_count
        uploads.append((mini_path.stat().st_size, count))
        return {index + 1: f"text@{index + 1}" for index in range(count)}

    return parse_one


class TestBatchByteLimit:
    """切批同时受页数与字节约束：网关对单批 PDF 有 48 MiB 硬上限（实测 66 MiB 413）。"""

    #: 一页随机像素 ≈ 600 × 600 × 3 字节 ≈ 1.03 MiB
    PAGE_BYTES = 600 * 600 * 3
    MIB = 1024 * 1024

    def test_默认上限低于网关硬上限(self) -> None:
        """32 MiB vs 48 MiB：留着 16 MiB 余量，不贴着拒绝阈值跑（理由见常量注释）。"""
        assert cloud_batch.DEFAULT_BATCH_MAX_MIB == 32
        assert 0 < cloud_batch.batch_max_bytes() < 48 * self.MIB

    def test_字节上限可由环境变量覆盖(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PDF_SPLIT_CLOUD_BATCH_MAX_MIB", "8")
        assert cloud_batch.batch_max_bytes() == 8 * self.MIB

    def test_页数少但体积大时按字节二分且每批不超限(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """6 页 / 6 MiB、页数上限给足（size=6）：只剩一批，必须靠字节二分才不超限。"""
        pdf = _make_heavy_pdf(tmp_path / "heavy.pdf", pages=6)
        limit = 3 * self.MIB  # 一批最多塞得下 2 页
        pages = list(range(1, 7))
        uploads: list[tuple[int, int]] = []
        done: list[list[int]] = []

        with caplog.at_level(logging.INFO, logger="apps.pdf_splitting"):
            result = cloud_batch.parse_in_batches(
                source_path=pdf,
                page_numbers=pages,
                parse_one=_page_count_parser(uploads),
                on_batch_done=lambda batch, _mapped: done.append(list(batch)),
                size=len(pages),
                concurrency=1,
                max_bytes=limit,
            )

        # 硬保证：每一次真正上传的小 PDF 都不超过上限
        assert uploads
        assert max(size for size, _count in uploads) <= limit
        # 不丢页不重页：上传段覆盖的页数之和 = 总页数，回调拼起来也正好是 1..6
        assert sum(count for _size, count in uploads) == len(pages)
        assert [page for batch in done for page in batch] == pages
        assert sorted(result) == pages
        # 拆分必须留痕（律师要能从日志看出「这批为什么切成四段」）
        assert any(record.msg == "pdf_split_batch_over_limit_split" for record in caplog.records)

    def test_单页本身超限时独占一批并告警(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """单页就超过上限：宁可冒一次 413，也不能静默丢页（丢页 = 整卷页序错位）。"""
        pdf = _make_heavy_pdf(tmp_path / "single.pdf", pages=2)
        limit = 900 * 1024  # 比单页 ~1.03 MiB 还小
        uploads: list[tuple[int, int]] = []
        done: list[list[int]] = []

        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            result = cloud_batch.parse_in_batches(
                source_path=pdf,
                page_numbers=[1, 2],
                parse_one=_page_count_parser(uploads),
                on_batch_done=lambda batch, _mapped: done.append(list(batch)),
                size=2,
                concurrency=1,
                max_bytes=limit,
            )

        # 超限页各自独占一批，且两页都在（清点不靠「有没有报错」）
        assert done == [[1], [2]]
        assert sorted(result) == [1, 2]
        warnings = [record for record in caplog.records if record.msg == "pdf_split_batch_single_page_over_limit"]
        assert len(warnings) == 2

    def test_上限内的批只切一刀(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """正常的批只切一次：超限才二分，不为每个批都把整本重切一遍。"""
        pdf = _make_heavy_pdf(tmp_path / "small.pdf", pages=4, side=200)  # 每页约 120 KiB
        calls: list[list[int]] = []
        real_slice = cloud_batch.slice_pdf

        def counting_slice(source_path: Path, page_numbers: list[int]) -> bytes:
            calls.append(list(page_numbers))
            return real_slice(source_path, page_numbers)

        monkeypatch.setattr(cloud_batch, "slice_pdf", counting_slice)

        cloud_batch.parse_in_batches(
            source_path=pdf,
            page_numbers=[1, 2, 3, 4],
            parse_one=_page_count_parser([]),
            size=2,
            concurrency=1,
            max_bytes=3 * self.MIB,
        )

        assert sorted(calls) == [[1, 2], [3, 4]]

    def test_同一页号集合的切批结果稳定(self, tmp_path: Path) -> None:
        """同一份源文件 + 同一批页号必须切出同样的段（不丢页、不重页、顺序不变）。"""
        pdf = _make_heavy_pdf(tmp_path / "stable.pdf", pages=5)
        limit = 3 * self.MIB

        def run() -> list[list[int]]:
            done: list[list[int]] = []
            cloud_batch.parse_in_batches(
                source_path=pdf,
                page_numbers=[1, 2, 3, 4, 5],
                parse_one=_page_count_parser([]),
                on_batch_done=lambda batch, _mapped: done.append(list(batch)),
                size=5,
                concurrency=1,
                max_bytes=limit,
            )
            return done

        first = run()
        assert first == run()
        assert [page for batch in first for page in batch] == [1, 2, 3, 4, 5]

    def test_整本在上限内时仍走直传不切片(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """上限内的小文档保持原行为：不切片、不落临时文件（单批快路径不能被字节检查吃掉）。"""
        pdf = _make_heavy_pdf(tmp_path / "tiny.pdf", pages=2, side=100)  # 每页约 30 KiB
        sliced: list[list[int]] = []

        def fail_slice(_source: Path, page_numbers: list[int]) -> bytes:
            sliced.append(list(page_numbers))
            return b""

        monkeypatch.setattr(cloud_batch, "slice_pdf", fail_slice)

        result = cloud_batch.parse_in_batches(
            source_path=pdf,
            page_numbers=[1, 2],
            parse_one=lambda _path: {1: "text@1", 2: "text@2"},
            concurrency=1,
        )

        assert sliced == []
        assert sorted(result) == [1, 2]
