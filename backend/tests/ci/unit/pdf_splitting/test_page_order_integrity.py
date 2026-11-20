"""页号↔文本绑定不变量（2026-11-20「错页乱页」事故的回归网）。

## 事故一句话

93 页卷宗的 `pages.json` 里，p2/p52 都是「疾病诊断证明书」、p3/p53 都是「出院记录」、
p4/p54、p6/p56 同样相隔 50 页重复；缓存里同一段文字又落在 −4、+46、+65 等不同偏移上。
段检测拿到这份错位输入，44 段的段名整体跟着错，而**整条链路没有任何一处报错**。

## 三个缺陷（本文件逐条锁死）

1. `cloud_batch.run_batch` 只平移字典键、**不改 `value.page_no`**：
   写缓存时文件名取自 `result.page_no`（批内相对号），于是每批都往 1..n 这批文件名上
   写、**互相覆盖**，归属由「谁最后写完」决定。
2. 读缓存时 `_load_ocr_cache_entry` 把请求页号**强行盖回** result，中毒从此不可见，
   重跑把脏数据当真理读回来（这就是「修完重跑还是错」的原因）。
3. `final_pages` 组装时缺页被**静默压紧**（`[x for x in descriptors if x is not None]`），
   第 k 个元素的页号可能不是 k，下游按位置取值即整体歪掉。

对应三道防线：值重定基（1）、缓存自证页号（2）、产物完整性断言（3）。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from apps.pdf_splitting.services.split.cloud_batch import rebase_page_result
from apps.pdf_splitting.services.split.ocr_handler import OCRHandler, _load_ocr_cache_entry
from apps.pdf_splitting.services.split.pipeline import _assert_page_integrity
from apps.pdf_splitting.services.split.split_models import OCRPageResult


def _page(page_no: int, text: str = "正文") -> OCRPageResult:
    return OCRPageResult(
        page_no=page_no,
        text=text,
        source_method="mineru_ocr",
        ocr_failed=False,
        layout={"page_no": page_no, "text": text},
    )


def _page_no(page: Any) -> int:
    return int(getattr(page, "page_no", 0) or 0)


# ── 防线 1：值重定基 ────────────────────────────────────────────────────


class TestRebasePageResult:
    def test_moves_page_no_and_layout_page_no_together(self) -> None:
        """批内相对页 3 落到整卷第 53 页时，值里的两个页号都必须跟着走。

        只改外层 `page_no` 而漏掉 `layout["page_no"]`，下游按 layout 取版面框时
        又会落回相对号——绿框整体错位，而文字看着是对的，更难查。
        """
        rebased = rebase_page_result(_page(3), 53)
        assert _page_no(rebased) == 53
        assert rebased.layout is not None
        assert rebased.layout["page_no"] == 53

    def test_keeps_other_fields_untouched(self) -> None:
        rebased = rebase_page_result(_page(1, text="疾病诊断证明书"), 52)
        assert rebased.text == "疾病诊断证明书"
        assert rebased.source_method == "mineru_ocr"
        assert rebased.ocr_failed is False

    def test_does_not_mutate_the_original(self) -> None:
        """frozen dataclass 必须返回新对象：原地改会让同批其它引用一起漂移。"""
        original = _page(3)
        rebase_page_result(original, 53)
        assert original.page_no == 3

    def test_non_dataclass_value_passes_through(self) -> None:
        """值形状变了也不能炸整批（解析端返回 dict 的历史版本）。"""
        assert rebase_page_result({"page_no": 1}, 9) == {"page_no": 1}

    def test_layout_without_page_no_is_tolerated(self) -> None:
        page = replace(_page(2), layout={"text": "无页号"})
        rebased = rebase_page_result(page, 51)
        assert _page_no(rebased) == 51
        assert rebased.layout == {"text": "无页号"}


# ── 防线 2：缓存自证页号 ────────────────────────────────────────────────


class _MemoryStorage:
    """最小存储桩：`default_storage` 的 exists/open/mtime 三件套。"""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def exists(self, path: str) -> bool:
        return path in self.files

    def open(self, path: str) -> Any:
        import io

        return io.BytesIO(self.files[path])


class TestCacheSelfAttestsPageNo:
    def test_mismatched_entry_is_rejected(self) -> None:
        """文件名说第 3 页、条目里写着第 57 页 → 判为中毒，当作未命中。

        这就是事故里「重跑也不对」的根因：旧代码不看条目里的页号，直接把请求页号
        盖回去，于是别人的文字被当成这一页交出去，而且**读的时候毫无异常**。
        """
        storage = _MemoryStorage(
            {"c/page_0003.json": json.dumps({"page_no": 57, "text": "别人的正文"}).encode()}
        )
        assert _load_ocr_cache_entry(storage=storage, rel_path="c/page_0003.json", page_no=3) is None

    def test_layout_page_no_is_used_when_top_level_missing(self) -> None:
        """旧条目没有顶层 page_no：退用 layout 里的页号判毒化。"""
        storage = _MemoryStorage(
            {"c/page_0003.json": json.dumps({"text": "x", "layout": {"page_no": 57}}).encode()}
        )
        assert _load_ocr_cache_entry(storage=storage, rel_path="c/page_0003.json", page_no=3) is None

    def test_matching_entry_is_returned(self) -> None:
        storage = _MemoryStorage(
            {"c/page_0003.json": json.dumps({"page_no": 3, "text": "出院记录"}).encode()}
        )
        entry = _load_ocr_cache_entry(storage=storage, rel_path="c/page_0003.json", page_no=3)
        assert entry is not None and entry.result.text == "出院记录"

    def test_entry_without_any_page_no_is_accepted(self) -> None:
        """没有页号信息的老条目无从判断，只能采信（不因此把缓存废掉）。"""
        storage = _MemoryStorage({"c/page_0003.json": json.dumps({"text": "旧格式"}).encode()})
        entry = _load_ocr_cache_entry(storage=storage, rel_path="c/page_0003.json", page_no=3)
        assert entry is not None and entry.result.text == "旧格式"

    def test_write_embeds_authoritative_page_no(self, tmp_path: Path, settings: Any) -> None:
        """写入侧：权威页号必须写进条目，供下次自证。"""
        settings.MEDIA_ROOT = tmp_path
        handler = OCRHandler()
        handler.write_ocr_cache(
            pdf_hash="h" * 64, profile_key="p", result=_page(3, text="正文"), page_no=53
        )
        cache_file = tmp_path / "pdf_splitting/ocr_cache" / ("h" * 64) / "p" / "page_0053.json"
        assert cache_file.exists(), "必须按**权威页号**命名，不能按 result.page_no"
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        assert payload["page_no"] == 53
        assert payload["layout"]["page_no"] == 53


# ── 防线 3：产物完整性断言 ──────────────────────────────────────────────


class TestPageIntegrityAssertion:
    def test_accepts_complete_contiguous_pages(self) -> None:
        _assert_page_integrity([_page(n) for n in range(1, 4)], expected=3)

    def test_rejects_duplicate_page_numbers(self) -> None:
        """页号重复 = 同两页内容被写到同一页上（事故里的 p2/p52 即此形态）。"""
        with pytest.raises(ValueError, match="重复"):
            _assert_page_integrity([_page(1), _page(2), _page(2)], expected=3)

    def test_rejects_out_of_order(self) -> None:
        with pytest.raises(ValueError, match="递增"):
            _assert_page_integrity([_page(1), _page(3), _page(2)], expected=3)

    def test_rejects_missing_pages(self) -> None:
        """缺页若被静默压紧，第 k 个元素的页号就不再是 k —— 整体歪掉的起点。"""
        with pytest.raises(ValueError, match="应为"):
            _assert_page_integrity([_page(1), _page(2)], expected=3)

    def test_rejects_offset_numbering(self) -> None:
        with pytest.raises(ValueError, match="从 1 连续"):
            _assert_page_integrity([_page(0), _page(1)], expected=2)

    def test_empty_is_allowed(self) -> None:
        """没有页（任务被取消/零页）不归这条断言管。"""
        _assert_page_integrity([], expected=0)
