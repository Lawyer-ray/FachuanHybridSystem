"""归档用的页指纹（`archive-to-case-folder` 的副本判定入参）。

两条断言各自对应一种真实失败模式：

1. 同一页算两次必须逐位相同——否则「它自己与自己」都判不成副本，副本识别永远不成立。
2. 整页 +20 灰度后仍须远小于 ``SAME_PAGE_MAX_DISTANCE``——扫描曝光 / 纸底亮度差
   不能主导距离。不二值化时距离被纸底亮度吃掉（实测纸底差 6/255 就能把「同文书两份
   扫件」推得比「两份不同文书」还远），副本识别会整体反转。

用例数据只含虚构案件名，无真实当事人信息。
"""

from __future__ import annotations

import pymupdf as fitz

from apps.cases.services.material.scan_archive_naming import SAME_PAGE_MAX_DISTANCE, signature_distance
from apps.pdf_splitting.api.pdf_splitting_api import _page_signature

CASE = "张某诉某公司买卖合同纠纷一案"


def _document(*, brightness: int = 0, lines: int = 28) -> fitz.Document:
    """一页密排正文的 A4（纸底灰度 218 + brightness，模拟扫描曝光差异）。"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, color=None, fill=(218 + brightness) / 255)
    for line_no in range(lines):
        page.insert_text((60, 100 + line_no * 24), f"第{line_no}行 {CASE} 证据材料明细", fontsize=10, color=0.16)
    return doc


def test_signature_is_ink_fraction_per_block() -> None:
    """指纹是 8×8 块内墨点占比：取值 0..1、页面有墨、维度按页面尺寸展平。"""
    source = _document()
    try:
        page = source[0]
        signature = _page_signature(page)
        pixmap = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY, alpha=False)
    finally:
        source.close()

    assert len(signature) == (pixmap.width // 8) * (pixmap.height // 8)
    assert all(0.0 <= value <= 1.0 for value in signature)
    assert max(signature) > 0.0, "整页被当成纸底（二值化阈值或取块步长写错）"


def test_same_page_twice_has_zero_distance() -> None:
    """同一页算两次必须零距离。"""
    source = _document()
    try:
        first = _page_signature(source[0])
        second = _page_signature(source[0])
    finally:
        source.close()

    assert signature_distance(first, second) == 0.0


def test_brightness_shift_stays_within_tolerance() -> None:
    """整页亮度 +20 后仍判同页（抗曝光差异）。"""
    darkened = _document()
    brightened = _document(brightness=20)
    try:
        distance = signature_distance(_page_signature(darkened[0]), _page_signature(brightened[0]))
    finally:
        darkened.close()
        brightened.close()

    assert distance < 0.03, f"亮度差把距离推到 {distance:.4f}，副本判定会失效"
    assert distance <= SAME_PAGE_MAX_DISTANCE
