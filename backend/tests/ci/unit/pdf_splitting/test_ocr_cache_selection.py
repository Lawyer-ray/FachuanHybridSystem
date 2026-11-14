"""OCR 页缓存写入幂等 + 读取择优。

背景（真实数据实测）：`default_storage.save` 遇同名不覆盖而是改名，
一页因此攒下几十份 `page_0001_xxxxxxxx.json` 残档，而读取只认固定名
`page_0001.json`——命中的是哪一次写的完全随机，可能是只有 32 字的那份。
所以：写入必须覆盖并清理残档；读取必须能在存量脏数据里挑出内容最多的那份。
"""

from __future__ import annotations

import json
import os
import time

import pytest
from django.core.files.storage import FileSystemStorage

from apps.pdf_splitting.services.split import ocr_handler
from apps.pdf_splitting.services.split.ocr_handler import OCRHandler
from apps.pdf_splitting.services.split.split_models import OCRPageResult

PDF_HASH = "hash576"
PROFILE_KEY = "accurate_mineru_text_v2"


def _cache_dir(root: str) -> str:
    return os.path.join(root, "pdf_splitting", "ocr_cache", PDF_HASH, PROFILE_KEY)


def _write_page_file(root: str, name: str, *, text: str, ocr_failed: bool, mtime: float | None = None) -> str:
    path = os.path.join(_cache_dir(root), name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"text": text, "ocr_failed": ocr_failed, "source_method": "ocr", "layout": None}, handle)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def cache_storage(tmp_path, monkeypatch):
    """把 ocr_handler 的 default_storage 换成 tmpdir 上的真实文件存储。"""
    storage = FileSystemStorage(location=str(tmp_path))
    monkeypatch.setattr(ocr_handler, "default_storage", storage)
    os.makedirs(_cache_dir(str(tmp_path)), exist_ok=True)
    return storage, str(tmp_path)


def _page_files(root: str) -> list[str]:
    return sorted(os.listdir(_cache_dir(root)))


class TestWriteOcrCacheIdempotent:
    def test_second_write_leaves_single_copy(self, cache_storage) -> None:
        _storage, root = cache_storage
        handler = OCRHandler()

        handler.write_ocr_cache(
            pdf_hash=PDF_HASH,
            profile_key=PROFILE_KEY,
            result=OCRPageResult(page_no=1, text="旧的一份", source_method="ocr", ocr_failed=False),
        )
        handler.write_ocr_cache(
            pdf_hash=PDF_HASH,
            profile_key=PROFILE_KEY,
            result=OCRPageResult(page_no=1, text="新的一份内容", source_method="ocr", ocr_failed=False),
        )

        assert _page_files(root) == ["page_0001.json"]
        with open(os.path.join(_cache_dir(root), "page_0001.json"), encoding="utf-8") as handle:
            assert json.load(handle)["text"] == "新的一份内容"

    def test_write_cleans_history_but_keeps_other_pages(self, cache_storage) -> None:
        _storage, root = cache_storage
        _write_page_file(root, "page_0001_0fm4T2l.json", text="残档", ocr_failed=False)
        _write_page_file(root, "page_0001_0mtixxY.json", text="残档", ocr_failed=False)
        _write_page_file(root, "page_00010.json", text="第 10 页", ocr_failed=False)

        OCRHandler().write_ocr_cache(
            pdf_hash=PDF_HASH,
            profile_key=PROFILE_KEY,
            result=OCRPageResult(page_no=1, text="写入", source_method="ocr", ocr_failed=False),
        )

        assert _page_files(root) == ["page_0001.json", "page_00010.json"]

    def test_read_falls_back_to_fixed_name_when_listdir_unavailable(self, cache_storage, monkeypatch) -> None:
        storage, root = cache_storage
        _write_page_file(root, "page_0001.json", text="固定名内容", ocr_failed=False)

        def _boom(_path: str) -> list[str]:
            return []

        monkeypatch.setattr(storage, "listdir", _boom)

        result = OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        assert result is not None
        assert result.text == "固定名内容"

    def test_cleanup_failure_does_not_break_write(self, cache_storage, monkeypatch) -> None:
        storage, root = cache_storage

        def _boom(_path: str) -> None:
            raise NotImplementedError("storage has no listdir")

        monkeypatch.setattr(storage, "listdir", _boom)

        OCRHandler().write_ocr_cache(
            pdf_hash=PDF_HASH,
            profile_key=PROFILE_KEY,
            result=OCRPageResult(page_no=1, text="写入", source_method="ocr", ocr_failed=False),
        )

        assert _page_files(root) == ["page_0001.json"]


class TestReadOcrCacheSelection:
    def test_picks_most_text_over_stale_short_copy(self, cache_storage) -> None:
        _storage, root = cache_storage
        _write_page_file(root, "page_0001.json", text="三十二字的失败版本" * 2, ocr_failed=False)
        _write_page_file(root, "page_0001_0fm4T2l.json", text="完好内容" * 500, ocr_failed=False)

        result = OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        assert result is not None
        assert result.text == "完好内容" * 500

    def test_self_heals_fixed_name_to_chosen_copy(self, cache_storage) -> None:
        _storage, root = cache_storage
        _write_page_file(root, "page_0001.json", text="短", ocr_failed=False)
        _write_page_file(root, "page_0001_0fm4T2l.json", text="长内容" * 100, ocr_failed=False)

        OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        with open(os.path.join(_cache_dir(root), "page_0001.json"), encoding="utf-8") as handle:
            assert json.load(handle)["text"] == "长内容" * 100

    def test_successful_copy_beats_failed_copy_with_more_text(self, cache_storage) -> None:
        _storage, root = cache_storage
        # 失败的那份也可能留下大量乱码文字：失败标记优先于文字量。
        _write_page_file(root, "page_0001_0fm4T2l.json", text="乱码" * 1000, ocr_failed=True)
        _write_page_file(root, "page_0001_0mtixxY.json", text="有效文本", ocr_failed=False)

        result = OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        assert result is not None
        assert result.text == "有效文本"
        assert result.ocr_failed is False

    def test_when_all_failed_takes_latest(self, cache_storage) -> None:
        _storage, root = cache_storage
        older = time.time() - 1000
        newer = time.time() - 10
        _write_page_file(root, "page_0001.json", text="失败-旧", ocr_failed=True, mtime=older)
        _write_page_file(root, "page_0001_0fm4T2l.json", text="失败-新", ocr_failed=True, mtime=newer)

        result = OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        assert result is not None
        assert result.text == "失败-新"

    def test_page_prefix_does_not_match_other_page(self, cache_storage) -> None:
        _storage, root = cache_storage
        # 第 10 页文字更多，但读第 1 页时绝不能拿到它。
        _write_page_file(root, "page_0001.json", text="第一页", ocr_failed=False)
        _write_page_file(root, "page_00010.json", text="第十页" * 500, ocr_failed=False)
        _write_page_file(root, "page_00010_abcdefg.json", text="第十页残档" * 500, ocr_failed=False)

        result = OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1)

        assert result is not None
        assert result.text == "第一页"

    def test_returns_none_when_page_absent(self, cache_storage) -> None:
        _storage, root = cache_storage
        _write_page_file(root, "page_00010.json", text="第十页", ocr_failed=False)

        assert OCRHandler().read_ocr_cache(pdf_hash=PDF_HASH, profile_key=PROFILE_KEY, page_no=1) is None
