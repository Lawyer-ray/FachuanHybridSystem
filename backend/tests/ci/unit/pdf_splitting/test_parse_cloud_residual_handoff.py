"""残余页接力下一个云端候选（2026-11-25 断路修复）。

## 断路是什么

`_parse_cloud` 原本是「任一候选返回非空字典就锁定并返回」，而「空页 / 退化页 /
候选没覆盖的页」是**返回之后**才判的（`_resolve_pending_pages`）。于是候选 1
（DeepSeek）吐了复读/空返回的页永远接不到候选 2（MinerU 小批），直接掉进本地逐页
`parallel_ocr` 慢路——一份 37 页材料里 26 页逐页兜底，吃掉了 20.7 分钟里的
大部分。

本文件锁住四条（都对应 `_parse_cloud` 的六条不变量）：

1. 候选 2 只收到**残余页号**（不是整本重跑，也不是只补第一页）；
2. 退化页自始至终不写云端页缓存（写进去 = 这页永久是垃圾）；
3. `degenerate_pages` 每页只记一次（多轮都判成退化也不重复计数）；
4. 全部候选都试完，残余页才进 `local_fallback_pages`（`parallel_ocr`）；
5. 同一候选不会对同一页调两次（「这页已试过哪几个候选」是显式状态）。

不调云端：`slice_pdf` 被替换成「把本批覆盖的原始页号编码成字节」，桩据此知道
每个候选到底收到了哪几页。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import cloud_batch
from apps.pdf_splitting.services.split.pipeline import PageTextExtractor, build_page_descriptor
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile

TEMPLATE_KEY = "filing_materials_v1"
PROFILE = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)
CLOUD_PROFILE = "balanced_deepseek_text_v2"
GOOD = "民事起诉状原告张三被告李四诉讼请求事实与理由"
#: 复读正文：同一行重复 60 次，命中 `degeneracy_reason` 的第一条判据。
LOOPED = "\n".join(["同一段话被模型反复吐出来"] * 60)


def _make_pdf(path: Path, pages: int) -> Path:
    """造一份无文本层的空白扫描件（只在切片/统计里被用到）。"""
    with fitz.open() as doc:
        for _ in range(pages):
            doc.new_page()
        doc.save(path.as_posix())
    return path


def _fake_slice(_source: Path, page_numbers: list[int]) -> bytes:
    """把本批覆盖的原始页号编码进「PDF 字节」——桩据此还原候选实际收到的页号。"""
    return ("pages:" + ",".join(str(no) for no in page_numbers)).encode()


def _decoded_pages(mini_pdf: Path) -> list[int]:
    raw = mini_pdf.read_text(encoding="utf-8")
    return [int(part) for part in raw.split(":", 1)[1].split(",")]


def _page(page_no: int, text: str, source_method: str) -> OCRPageResult:
    return OCRPageResult(page_no=page_no, text=text, source_method=source_method, ocr_failed=not text)


class _HandoffHandler:
    """候选脚本桩：`script[backend][页号]` 决定该候选对这一页返回什么。

    页号不在 `script[backend]` 里 = 这个候选**没覆盖**这一页（云端漏页的真实形态）。
    """

    def __init__(self, *, script: dict[str, dict[int, OCRPageResult]], fail: set[str] | None = None) -> None:
        self.script = script
        self.fail = fail or set()
        #: `(候选, 它收到的原始页号)`，按调用顺序
        self.cloud_calls: list[tuple[str, list[int]]] = []
        self.cloud_writes: list[int] = []
        self.local_writes: list[int] = []
        self.local_calls: list[list[int]] = []
        #: 事件顺序：云端候选在前、本地兜底在后
        self.events: list[str] = []

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        pages = _decoded_pages(pdf_path)
        self.cloud_calls.append((backend, pages))
        self.events.append(f"cloud:{backend}")
        if backend in self.fail:
            raise RuntimeError(f"{backend} down")
        table = self.script.get(backend, {})
        # 小 PDF 内是相对页号 1..n，`parse_in_batches` 负责重定基回整卷页号
        return {index + 1: table[page_no] for index, page_no in enumerate(pages) if page_no in table}

    def write_ocr_cache(
        self, *, pdf_hash: str, profile_key: str, result: OCRPageResult, page_no: int | None = None
    ) -> None:
        target = page_no if page_no is not None else result.page_no
        if profile_key == CLOUD_PROFILE:
            self.cloud_writes.append(target)
        else:
            self.local_writes.append(target)

    def parallel_ocr(
        self,
        *,
        pdf_path: Path,
        page_numbers: list[int],
        runtime_profile: OCRRuntimeProfile,
        **extra: Any,
    ) -> dict[int, OCRPageResult]:
        self.local_calls.append(list(page_numbers))
        self.events.append("local:parallel_ocr")
        return {
            page_no: OCRPageResult(
                page_no=page_no, text=f"本地 OCR 第{page_no}页正文", source_method="ocr", ocr_failed=False
            )
            for page_no in page_numbers
        }


def _stats(*, pending: list[int], candidates: list[str]) -> dict[str, Any]:
    return {
        "runtime_profile": PROFILE,
        "pdf_hash": "hash-handoff",
        "cloud_backend": candidates[0] if candidates else None,
        "cloud_candidates": list(candidates),
        "cloud_cache_profile": CLOUD_PROFILE,
        "cloud_succeeded": False,
        "pending_page_numbers": list(pending),
        "pending_ocr_count": 0,
        "cloud_error": "",
        "layout_mode": "fast_text",
        "degenerate_pages": [],
        "cache_degenerate_pages": [],
        "budget_skipped_pages": [],
    }


def _run(
    pdf: Path,
    handler: _HandoffHandler,
    monkeypatch: pytest.MonkeyPatch,
    *,
    page_total: int,
    candidates: list[str],
) -> tuple[dict[str, Any], list[Any]]:
    """第 1 页已经取好，2..N 全待取字 → 直接跑第二遍取字。

    只调 `_resolve_pending_pages`（不跑第一遍文本层/缓存扫描）：本文件要断言的是
    「云端多候选怎么接力」，把第一遍的取字来源混进来只会让失败点不可归因。
    """
    descriptors: list[Any] = [None] * page_total
    descriptors[0] = build_page_descriptor(
        page_no=1,
        text="第一页已有正文",
        source_method="text",
        ocr_failed=False,
        template_key=TEMPLATE_KEY,
    )
    pending = list(range(2, page_total + 1))
    stats = _stats(pending=pending, candidates=candidates)
    extractor = PageTextExtractor(ocr_handler=handler)
    monkeypatch.setattr(cloud_batch, "slice_pdf", _fake_slice)
    extractor._resolve_pending_pages(
        pdf,
        descriptors=descriptors,
        pdf_hash="hash-handoff",
        template_key=TEMPLATE_KEY,
        stats=stats,
    )
    return stats, descriptors


def _attempted(handler: _HandoffHandler) -> list[tuple[str, int]]:
    return [(backend, page_no) for backend, pages in handler.cloud_calls for page_no in pages]


class TestResidualHandoff:
    def test_候选2只收到残余页号_退化页不写缓存_计数不重复(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """候选 1 一半可用、一半是空/退化/漏页 → 候选 2 只补那三页，其余不重跑。"""
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=7)
        handler = _HandoffHandler(
            script={
                "deepseek": {
                    2: _page(2, GOOD, "deepseek_ocr"),
                    3: _page(3, "", "deepseek_empty"),  # 空返回
                    4: _page(4, LOOPED, "deepseek_ocr"),  # 复读循环
                    # 5 不在脚本里 = 候选没覆盖这一页
                    6: _page(6, GOOD, "deepseek_ocr"),
                    7: _page(7, GOOD, "deepseek_ocr"),
                },
                "mineru": {
                    3: _page(3, GOOD, "mineru_ocr"),
                    4: _page(4, LOOPED, "mineru_ocr"),  # 换了引擎还是复读
                    # 5 仍然没覆盖
                },
            }
        )

        stats, descriptors = _run(pdf, handler, monkeypatch, page_total=7, candidates=["deepseek", "mineru"])

        # ① 候选 2 只收到残余页号（空 / 退化 / 漏页），已可用的 2/6/7 不重跑
        assert handler.cloud_calls == [("deepseek", [2, 3, 4, 5, 6, 7]), ("mineru", [3, 4, 5])]
        # ② 同一候选不会对同一页调两次
        attempted = _attempted(handler)
        assert len(attempted) == len(set(attempted))

        # ③ 退化页（4）与始终没覆盖的页（5）一个字节都没进云端缓存档案；
        #    候选 2 补回来的第 3 页进了（否则下次重跑还要再付一次钱）
        assert 4 not in handler.cloud_writes
        assert 5 not in handler.cloud_writes
        assert set(handler.cloud_writes) == {2, 3, 6, 7}

        # ④ 退化页每页只记一次（两个候选都判成退化，也不能计成 2）
        assert stats["degenerate_pages"] == [4]

        # ⑤ 全部候选都试完，残余页才落本地兜底
        assert handler.local_calls == [[4, 5]]
        assert handler.events == ["cloud:deepseek", "cloud:mineru", "local:parallel_ocr"]

        # 取字结果归属：3 是候选 2 救回来的，4/5 是本地兜底
        assert descriptors[2].text == GOOD and descriptors[2].source_method == "mineru_ocr"
        assert descriptors[3].source_method == "ocr"
        assert descriptors[4].source_method == "ocr"

        # 主平台与容灾来源只记一次，不因接力被覆盖
        assert stats["cloud_backend"] == "deepseek"
        assert stats["cloud_succeeded"] is True
        assert stats["cloud_failover_from"] == []
        assert stats["cloud_error"] == ""

    def test_三个候选都试过仍救不回来的页也只调用一次每候选(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """第 4 页在第 1、2、3 轮都被判成退化：三轮各调一次，绝不回头再调同一候选。"""
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=7)
        handler = _HandoffHandler(
            script={
                "deepseek": {
                    2: _page(2, GOOD, "deepseek_ocr"),
                    3: _page(3, "", "deepseek_empty"),
                    4: _page(4, LOOPED, "deepseek_ocr"),
                    6: _page(6, GOOD, "deepseek_ocr"),
                    7: _page(7, GOOD, "deepseek_ocr"),
                },
                "mineru": {
                    3: _page(3, GOOD, "mineru_ocr"),
                    4: _page(4, LOOPED, "mineru_ocr"),
                },
                "textin": {
                    4: _page(4, LOOPED, "textin_ocr"),
                },
            }
        )

        stats, _descriptors = _run(pdf, handler, monkeypatch, page_total=7, candidates=["deepseek", "mineru", "textin"])

        assert [backend for backend, _pages in handler.cloud_calls] == ["deepseek", "mineru", "textin"]
        # 每个候选只拿到「它还没试过」的页：第 4/5 页逐轮缩小到最后一个候选
        assert handler.cloud_calls == [
            ("deepseek", [2, 3, 4, 5, 6, 7]),
            ("mineru", [3, 4, 5]),
            ("textin", [4, 5]),
        ]
        attempted = _attempted(handler)
        assert len(attempted) == len(set(attempted))
        # 三轮都判成退化，也只在第一次记一次
        assert stats["degenerate_pages"] == [4]
        assert handler.local_calls == [[4, 5]]

    def test_全部候选都不给可用结果时汇总错误并全部落本地兜底(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """候选 1 抛错、候选 2/3 返回空：残余页原样进本地兜底，原因写进 cloud_error。"""
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=7)
        handler = _HandoffHandler(script={}, fail={"deepseek"})

        stats, descriptors = _run(pdf, handler, monkeypatch, page_total=7, candidates=["deepseek", "mineru", "textin"])

        # 每个候选都只对整批试了一次（没有可用页可摘，残余集合不变）
        assert handler.cloud_calls == [
            ("deepseek", [2, 3, 4, 5, 6, 7]),
            ("mineru", [2, 3, 4, 5, 6, 7]),
            ("textin", [2, 3, 4, 5, 6, 7]),
        ]
        assert handler.local_calls == [[2, 3, 4, 5, 6, 7]]
        assert handler.cloud_writes == []
        assert descriptors[1].source_method == "ocr"

        assert stats["cloud_succeeded"] is False
        assert "deepseek" in stats["cloud_error"] and "mineru" in stats["cloud_error"]
        assert "返回空结果" in stats["cloud_error"]

    def test_主平台回了结果但一页不可用时平台归属改记真正出字的候选(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DeepSeek 整本空返回（实测形态）→ 所有页由 MinerU 出字，平台必须记 MinerU。

        `_actual_provider` 用 `cloud_backend` 决定坐标系量纲与摘要口径：把整本算到
        没出字的那个引擎头上会让绿框整体错位，而正文看着是对的（最难查的一类错）。
        """
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=4)
        handler = _HandoffHandler(
            script={
                # 候选 1 每页都「成功返回」但正文是空串
                "deepseek": {page_no: _page(page_no, "", "deepseek_empty") for page_no in range(2, 5)},
                "mineru": {page_no: _page(page_no, GOOD, "mineru_ocr") for page_no in range(2, 5)},
            }
        )

        stats, descriptors = _run(pdf, handler, monkeypatch, page_total=4, candidates=["deepseek", "mineru"])

        assert stats["cloud_backend"] == "mineru"
        assert stats["cloud_failover_from"] == ["deepseek"]
        assert stats["cloud_succeeded"] is True
        assert [descriptors[index].source_method for index in range(1, 4)] == ["mineru_ocr"] * 3
        assert handler.local_calls == []  # 全部页都被候选 2 救回来了
        assert set(handler.cloud_writes) == {2, 3, 4}
