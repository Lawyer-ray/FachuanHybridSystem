"""草稿导出（`services/export_draft_service.py` + `POST /export-draft`）。

律师可以不跑自动分段：自己切页、改名、旋转 180° 后直接归案。这种包的数据是全的
（段名与页区间在草稿里、源附件在收件箱里），但以前**一个导出按钮都没有**——下载
入口全挂在拆分任务的段上。这组用例钉的就是「按草稿切页打包」这条新链路：

1. 页区间切得对（按 pymupdf 读回每页文本）；
2. **旋转在切页之前烧进去**（源 /Rotate 90 + 人工 90 → 读回 180）；
3. 同一素材的多段**不重复烧旋转**（逐段 apply 会把 90 变成 180）；
4. 有 md 的段配同名 .md；同名段名不覆盖（`_2`）；
5. 坏段（越界 / 素材缺失）**跳过并计数**，其余照常导出；一段都导不出才报错。
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

import pymupdf as fitz
import pytest

from apps.core.exceptions import ValidationException
from apps.pdf_splitting.services.export_draft_service import (
    DraftExportSegment,
    build_export_zip,
    collect_files,
    parse_spec,
)


def _pdf(pages: int = 4, *, rotations: list[int] | None = None) -> bytes:
    doc = fitz.open()
    try:
        for no in range(1, pages + 1):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), f"PAGE-{no}")
            deg = (rotations or [])[no - 1] if rotations and no - 1 < len(rotations) else 0
            if deg:
                page.set_rotation(deg)
        return doc.tobytes()  # type: ignore[no-any-return]
    finally:
        doc.close()


class _Upload:
    """UploadedFile 的最小替身：只用到 name / size / read()。"""

    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self.size = len(content)
        self._content = content

    def read(self) -> bytes:
        return self._content


def _seg(**over: Any) -> DraftExportSegment:
    base: dict[str, Any] = dict(name="起诉状", part_index=0, page_start=1, page_end=2)
    base.update(over)
    return DraftExportSegment(**base)


def _unzip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _texts(pdf_bytes: bytes) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [doc.load_page(i).get_text().strip() for i in range(doc.page_count)]
    finally:
        doc.close()


class TestParseSpec:
    def test_parses_segments(self) -> None:
        spec = json.dumps(
            {"segments": [{"name": "起诉状", "part_index": 0, "page_start": 1, "page_end": 3, "md": "# hi"}]}
        )
        segments = parse_spec(spec)
        assert segments == [
            DraftExportSegment(name="起诉状", part_index=0, page_start=1, page_end=3, rotations="", md="# hi")
        ]

    def test_rejects_structural_errors(self) -> None:
        for raw in ["not json", "{}", '{"segments": []}', '{"segments": [{"part_index": "x"}]}']:
            with pytest.raises(ValidationException):
                parse_spec(raw)

    def test_rejects_bad_page_range(self) -> None:
        with pytest.raises(ValidationException):
            parse_spec(json.dumps({"segments": [{"part_index": 0, "page_start": 5, "page_end": 2}]}))

    def test_caps_segment_count(self) -> None:
        many = [{"part_index": 0, "page_start": 1, "page_end": 1} for _ in range(501)]
        with pytest.raises(ValidationException):
            parse_spec(json.dumps({"segments": many}))


class TestCollectFiles:
    def test_maps_by_part_prefix(self) -> None:
        files = collect_files([_Upload("part_0.pdf", b"%PDF-1"), _Upload("part_3.png", b"\x89PNG")])
        assert set(files) == {0, 3}
        assert files[3][0] == "part_3.png"

    def test_rejects_unexpected_names(self) -> None:
        # 静默跳过会让「包里少一份材料」变成查不出来的谜
        with pytest.raises(ValidationException):
            collect_files([_Upload("起诉状.pdf", b"%PDF-1")])


class TestBuildZip:
    def test_slices_pdf_by_page_range(self) -> None:
        content, skipped = build_export_zip({0: ("part_0.pdf", _pdf(4))}, [_seg(page_start=2, page_end=3)])
        assert skipped == 0
        entries = _unzip(content)
        assert list(entries) == ["01-起诉状.pdf"]
        assert _texts(entries["01-起诉状.pdf"]) == ["PAGE-2", "PAGE-3"]

    def test_burns_rotation_before_slicing(self) -> None:
        content, _ = build_export_zip(
            {0: ("part_0.pdf", _pdf(2))}, [_seg(part_index=0, page_start=1, page_end=2, rotations="2:90")]
        )
        doc = fitz.open(stream=_unzip(content)["01-起诉状.pdf"], filetype="pdf")
        try:
            assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [0, 90]
        finally:
            doc.close()

    def test_rotation_stacks_on_source_rotate(self) -> None:
        content, _ = build_export_zip(
            {0: ("part_0.pdf", _pdf(1, rotations=[90]))},
            [_seg(page_start=1, page_end=1, rotations="1:90")],
        )
        doc = fitz.open(stream=_unzip(content)["01-起诉状.pdf"], filetype="pdf")
        try:
            assert int(doc.load_page(0).rotation) == 180
        finally:
            doc.close()

    def test_multi_segment_same_part_applies_rotation_once(self) -> None:
        """同一份素材被切成两段、两段都带 ``1:90``：第 1 页只该烧一次。

        逐段 apply 的写法会把 90 变成 180（每段各转一遍），而屏幕上明明是竖直的——
        这是这条链路最隐蔽的错法，所以直接对第 1 页断言。
        """
        segments = [
            _seg(name="甲", page_start=1, page_end=1, rotations="1:90"),
            _seg(name="乙", page_start=2, page_end=2, rotations="1:90"),
        ]
        content, _ = build_export_zip({0: ("part_0.pdf", _pdf(2))}, segments)
        entries = _unzip(content)
        doc = fitz.open(stream=entries["01-甲.pdf"], filetype="pdf")
        try:
            assert int(doc.load_page(0).rotation) == 90  # 不是 180
        finally:
            doc.close()

    def test_md_is_paired_with_pdf(self) -> None:
        content, _ = build_export_zip({0: ("part_0.pdf", _pdf(2))}, [_seg(md="# 起诉状\n正文")])
        entries = _unzip(content)
        assert entries["01-起诉状.md"].decode() == "# 起诉状\n正文"

    def test_duplicate_names_do_not_overwrite(self) -> None:
        """同名的两段不能互相覆盖：序号前缀保证唯一，两段的页内容各自正确。"""
        segments = [_seg(name="证据"), _seg(name="证据", page_start=3, page_end=4)]
        content, _ = build_export_zip({0: ("part_0.pdf", _pdf(4))}, segments)
        entries = _unzip(content)
        assert set(entries) == {"01-证据.pdf", "02-证据.pdf"}
        assert _texts(entries["01-证据.pdf"]) == ["PAGE-1", "PAGE-2"]
        assert _texts(entries["02-证据.pdf"]) == ["PAGE-3", "PAGE-4"]

    def test_image_material_is_copied_verbatim(self) -> None:
        """图片没有页对象：前端已按旋转重编码，服务端原样收并保留扩展名。"""
        content, _ = build_export_zip({2: ("part_2.png", b"\x89PNGdata")}, [_seg(name="现场照片", part_index=2)])
        assert _unzip(content) == {"01-现场照片.png": b"\x89PNGdata"}

    def test_bad_segments_are_skipped_and_counted(self) -> None:
        segments = [
            _seg(name="正常", page_start=1, page_end=1),
            _seg(name="越界", page_start=1, page_end=99),  # 页超界 → 跳过
            _seg(name="缺素材", part_index=9),  # 素材没发 → 跳过
        ]
        content, skipped = build_export_zip({0: ("part_0.pdf", _pdf(2))}, segments)
        assert skipped == 2
        assert list(_unzip(content)) == ["01-正常.pdf"]

    def test_all_skipped_raises(self) -> None:
        with pytest.raises(ValidationException):
            build_export_zip({0: ("part_0.pdf", _pdf(2))}, [_seg(page_start=1, page_end=99)])

    def test_unsafe_segment_name_is_sanitised(self) -> None:
        content, _ = build_export_zip({0: ("part_0.pdf", _pdf(2))}, [_seg(name="../../卷宗/起诉状")])
        # 路径分隔符必须被替换：否则 zip 里会出现目录穿越条目
        assert list(_unzip(content)) == ["01-_.._卷宗_起诉状.pdf"]
