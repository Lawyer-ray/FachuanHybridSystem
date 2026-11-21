"""可见帧归一化区域 → ``get_pixmap(clip=...)`` 矩形（``/Rotate`` 页唯一正确口径）。

## 实测结论（以本仓锁定的 ``pymupdf==2.1`` 为准，见 ``pyproject.toml:58``）

``Page.get_pixmap(clip=...)`` 的 ``clip`` 落在**旋转后的可见帧**坐标系：与
``page.rect``／``page.get_displaylist().rect`` 同帧，原点恒为 (0, 0)——``/MediaBox``
原点非 0、``/CropBox`` 小于 ``/MediaBox`` 时也一样归零。所以「归一化区域 × 可见帧」
**就是**正确 clip，不需要 ``page.derotation_matrix``／``page.rotation_matrix``。

实测（200×100 页、黑块只画在未旋转左上 ``(0,0)-(20,20)``）：

=========================  ==============  ==========================================
``/Rotate``                可见帧           黑块落点 / ``clip=(0,0,50,50)``
=========================  ==============  ==========================================
0                          ``200×100``      ``(0..20, 0..20)`` / 有墨
90                         ``100×200``      ``(79..100, 0..20)`` / **无墨**
270                        ``100×200``      ``(0..20, 179..200)`` / **无墨**
=========================  ==============  ==========================================

反向证据：把同一矩形按 ``derotation_matrix`` 换到未旋转坐标系再当 clip 传进去，
90/270 页上**裁不到墨**（漏裁）。即「用 ``page.rect`` 算 clip 是错的」这个说法不成立，
逐像素复算见 ``tests/ci/unit/pdf_splitting/test_page_rotation_clip.py``。

⚠️ ``docs/analysis/rotated-pages-2026-11-21/pipeline.md`` §0 结论 2（「clip 用未旋转
页面坐标系」）是把两条观测的标注写反了；更正见同目录 ``pipeline-correction.md``。

## 为什么抽成一处

``ocr_handler.ocr_page_region``（image rescue 裁一块送 OCR）与
``table_geometry_pass._measure_page_crop``（表格几何单页兜底）都要这段换算。两处各写一套，
口径一旦漂移就是「OCR 读 A 处、几何画 B 处」——看起来成功、其实指错地方的错误。
本模块是唯一实现，两个调用点只准调它。

## 帧的一致性（为什么不用反变换）

前端 ``frontend/src/lib/pdf.ts`` 的 ``page.getViewport({scale})`` 不传 rotation，
默认用 ``page.rotate``，也就是渲染帧 = 可见帧。裁图送 OCR／量测后，块坐标按 ``region``
的宽高归一化回页面（``_rescale_region_blocks`` / ``measure_table_crop``），与前端同帧，
因此**不需要**把结果转回未旋转坐标系。

## 与 ``page_rotation.py`` 的分工

``page_rotation.py`` 是「服务端转正帧 → 原页帧」的坐标反变换（θ 来自方向分类），
与本模块无关：这里不做任何旋转，只把**可见帧**的 0–1 区域换成该帧里的矩形。
"""

from __future__ import annotations

from collections.abc import Sequence

import pymupdf as fitz


def clip_rect_for_page(page: fitz.Page, region: Sequence[float]) -> fitz.Rect:
    """``region``（可见帧 0–1 的 ``[x0, y0, x1, y1]``）→ 该页 ``get_pixmap(clip=...)`` 矩形。

    可见帧 = ``page.rect``（``/Rotate`` 已应用、原点归零），与前端 pdf.js 同帧。
    ``region`` 的单位由调用方先收敛到 0–1：image rescue 的千分比要除以 1000，
    表格几何的 ``crop`` 本来就是 0–1。
    """
    x0, y0, x1, y1 = region
    frame = page.rect
    return fitz.Rect(
        frame.x0 + x0 * frame.width,
        frame.y0 + y0 * frame.height,
        frame.x0 + x1 * frame.width,
        frame.y0 + y1 * frame.height,
    )
