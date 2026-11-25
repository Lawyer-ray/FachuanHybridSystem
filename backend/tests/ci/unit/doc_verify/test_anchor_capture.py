"""基线捕获「组装」这一半的单测：字节流 → :class:`Baseline`，以及默认掩膜的边界。

样本同样现场合成，不依赖任何真实案卷。

锁住的三件事：
- 基线的 SHA-256 来自字节本身（幂等键的根）；
- 扫描件基线正文为空串、掩膜原样带出（**基线侧不做 OCR**）；
- 默认掩膜只给四个高风险文书的文末签署区，其它文书一条都不给。
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import pymupdf
import pytest

from apps.doc_verify.domain.contracts import Baseline
from apps.doc_verify.services.anchor.area_mask import default_masks
from apps.doc_verify.services.anchor.capture import capture_baseline


def _make_digital_pdf(page_texts: Sequence[str]) -> bytes:
    document = pymupdf.open()
    for index, body in enumerate(page_texts, start=1):
        page = document.new_page()
        page.insert_text((72, 100), f"page {index}: {body}", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def _make_scanned_pdf(page_count: int = 1) -> bytes:
    document = pymupdf.open()
    for index in range(page_count):
        page = document.new_page()
        page.draw_rect(pymupdf.Rect(80, 120, 320, 260), color=(0, 0, 0), fill=(0.15, 0.15, 0.15))
    data = document.tobytes()
    document.close()
    return data


class TestCaptureBaseline:
    def test_pdf_baseline_carries_pages_signatures_and_text(self) -> None:
        data = _make_digital_pdf(["alpha body", "beta body", "gamma body"])

        baseline = capture_baseline(data=data, file_name="起诉状.pdf", doc_type="起诉状", version="V4_20261106")

        assert isinstance(baseline, Baseline)
        assert baseline.doc_type == "起诉状"
        assert baseline.version == "V4_20261106"
        assert baseline.sha256 == hashlib.sha256(data).hexdigest()
        assert baseline.page_count == 3
        assert len(baseline.page_signatures) == 3
        assert "page 2: beta body" in baseline.text
        assert baseline.masks == ()

    def test_masks_are_copied_as_immutable_sequence(self) -> None:
        data = _make_digital_pdf(["alpha body"])
        masks: list[dict[str, Any]] = [
            {"kind": "signature_zone", "doc_type": "起诉状", "tail_lines": 3},
            {"kind": "seal_zone", "doc_type": "起诉状", "tail_lines": 1},
        ]

        baseline = capture_baseline(data=data, file_name="起诉状.pdf", doc_type="起诉状", masks=masks)

        assert isinstance(baseline.masks, tuple)
        assert baseline.masks == tuple(masks)

    def test_scanned_pdf_baseline_has_empty_text_and_keeps_masks(self) -> None:
        masks = default_masks("送达地址确认书")

        baseline = capture_baseline(
            data=_make_scanned_pdf(page_count=2),
            file_name="送达地址确认书.pdf",
            doc_type="送达地址确认书",
            masks=masks,
        )

        assert baseline.text == ""
        assert baseline.page_count == 2
        assert len(baseline.page_signatures) == 2
        assert baseline.masks == ({"kind": "signature_zone", "doc_type": "送达地址确认书", "tail_lines": 3},)

    def test_blank_doc_type_raises(self) -> None:
        with pytest.raises(ValueError, match="缺少文书名"):
            capture_baseline(data=_make_digital_pdf(["alpha body"]), file_name="无标题.pdf", doc_type="  ")

    def test_empty_bytes_raise(self) -> None:
        with pytest.raises(ValueError, match="字节为空"):
            capture_baseline(data=b"", file_name="空件.pdf", doc_type="起诉状")

    def test_one_character_change_changes_sha(self) -> None:
        original = _make_digital_pdf(["alpha body"])
        edited = _make_digital_pdf(["alpha bodY"])

        left = capture_baseline(data=original, file_name="起诉状.pdf", doc_type="起诉状")
        right = capture_baseline(data=edited, file_name="起诉状.pdf", doc_type="起诉状")

        assert left.sha256 != right.sha256


class TestDefaultMasks:
    @pytest.mark.parametrize("doc_type", ["起诉状", "授权委托书", "送达地址确认书", "退费账户确认书"])
    def test_high_risk_doc_types_get_signature_zone_mask(self, doc_type: str) -> None:
        assert default_masks(doc_type) == [{"kind": "signature_zone", "doc_type": doc_type, "tail_lines": 3}]

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert default_masks("  起诉状 ") == [{"kind": "signature_zone", "doc_type": "起诉状", "tail_lines": 3}]

    @pytest.mark.parametrize("doc_type", ["证据清单", "", "民事起诉状草稿"])
    def test_other_doc_types_get_no_mask(self, doc_type: str) -> None:
        assert default_masks(doc_type) == []
