"""``/Rotate`` 页的裁图帧：可见帧 = ``get_pixmap(clip=)`` 帧 = pdf.js 渲染帧（逐像素钉住）。

## 守的是什么

``docs/analysis/rotated-pages-2026-11-21/pipeline.md`` §0 结论 2 断言「``clip`` 用的是未旋转
页面坐标系，所以用 ``page.rect`` 算 clip 是错的，要按 ``derotation_matrix`` 换算」。
实测（本仓锁定 ``pymupdf==2.1``，``pyproject.toml:58``）**相反**：``clip`` 就落在旋转后的
可见帧，与 ``page.rect``／``page.get_displaylist().rect`` 同帧、原点归零。两处调用
（``ocr_handler.ocr_page_region`` 与 ``table_geometry_pass._measure_page_crop``）
原来的写法本来就是对的；按 §0「修」一次会让旋转页**漏裁**（见第 ④ 组）。

四组锁：

1. **内容**：同一套图案按可见帧比例摆好，``/Rotate=0/90/270`` 三种页在**同一 region**
   下裁出的图逐像素相同（方形页样本级相等，非方形页按归一化墨迹位置相等）；
2. **帧**：整页 region 的 clip 恒等于 ``page.rect``（``/Rotate=90`` 时是 100×200，
   **不是**未旋转的 ``/MediaBox`` 200×100）；
3. **round-trip**：region → clip → 帧内归一化，回到原 region，误差 < 1e-6；
4. **同源**：两个裁图调用点必须指向同一个纯函数。

## 为什么图案要按可见帧摆

``draw_rect`` 用**未旋转**坐标系。要让旋转页的可见内容与 0° 页一致，画之前得先用
``page.derotation_matrix`` 把可见帧矩形换到未旋转坐标系——这正是「可见帧是唯一真相」
的反向用法。

## 跑法（红线：只能连测试库）

```bash
cd backend
DB_NAME=test_fachuan_dev_tg_a .venv/bin/python -m pytest tests/ci/unit/pdf_splitting/test_page_rotation_clip.py -q
```
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import ocr_handler, table_geometry_pass
from apps.pdf_splitting.services.split.clip_frame import clip_rect_for_page

#: 非方形页（200×100）：``/Rotate=90`` 的可见帧是 100×200，宽高互换才是真实口径。
_PAGE_SIZE = (200.0, 100.0)

#: 可见帧里的不对称图案（归一化）：左上小方块 / 右下横条 / 右上竖条 —— 三个一起才区分得出旋转。
_MARKER_SHAPES = ((0.10, 0.10, 0.30, 0.30), (0.40, 0.60, 0.90, 0.75), (0.70, 0.10, 0.85, 0.60))

#: 灰度深墨阈值：纯黑填充在白底上，抗锯齿边缘落在 128 以上。
_DARK = 128


@dataclass(frozen=True)
class _Crop:
    """裁图产物（只留宽高与灰度像素，脱离 PDF 文档后仍可用）。"""

    width: int
    height: int
    samples: bytes

    def ink_pixels(self) -> int:
        return sum(1 for value in self.samples if value < _DARK)

    def normalized_ink_bbox(self) -> tuple[float, float, float, float]:
        """墨迹外接矩形 / 裁图宽高（0–1）。"""
        xs: list[int] = []
        ys: list[int] = []
        for y in range(self.height):
            row = y * self.width
            for x in range(self.width):
                if self.samples[row + x] < _DARK:
                    xs.append(x)
                    ys.append(y)
        return (min(xs) / self.width, min(ys) / self.height, (max(xs) + 1) / self.width, (max(ys) + 1) / self.height)


def _visible_size(page_size: tuple[float, float], rotation: int) -> tuple[float, float]:
    """``/Rotate`` 后的可见帧尺寸（90/270 宽高互换）。"""
    return page_size if rotation in (0, 180) else (page_size[1], page_size[0])


def _pdf(
    path: Path,
    *,
    rotation: int,
    page_size: tuple[float, float] = _PAGE_SIZE,
    shapes: tuple[tuple[float, float, float, float], ...] = _MARKER_SHAPES,
) -> Path:
    """在可见帧里摆 ``shapes``（0–1）的黑方块，再把该页设成 ``rotation``。"""
    document = fitz.open()
    try:
        page = document.new_page(width=page_size[0], height=page_size[1])
        page.set_rotation(rotation)
        width, height = _visible_size(page_size, rotation)
        for x0, y0, x1, y1 in shapes:
            visible = fitz.Rect(x0 * width, y0 * height, x1 * width, y1 * height)
            # draw_rect 收未旋转坐标；可见帧 → 未旋转，才是「把图案摆在看得见的位置」
            target = visible * page.derotation_matrix if rotation else visible
            page.draw_rect(target, color=0, fill=(0, 0, 0))
        document.save(path)
    finally:
        document.close()
    return path


def _render(
    path: Path,
    *,
    rotation: int,
    region: tuple[float, float, float, float],
    page_size: tuple[float, float] = _PAGE_SIZE,
) -> _Crop:
    """按 ``region``（可见帧 0–1）裁一页出来。"""
    with fitz.open(_pdf(path, rotation=rotation, page_size=page_size)) as document:
        page = document.load_page(0)
        pixmap = page.get_pixmap(colorspace=fitz.csGRAY, clip=clip_rect_for_page(page, region))
        return _Crop(width=pixmap.width, height=pixmap.height, samples=bytes(pixmap.samples))


# ── ① 内容：同一 region 裁到的是同一张图 ─────────────────────────


@pytest.mark.parametrize("rotation", [90, 270])
@pytest.mark.parametrize("region", [(0.0, 0.0, 1.0, 1.0), (0.1, 0.1, 0.9, 0.9), (0.2, 0.5, 0.95, 0.85)])
def test_方形页上旋转页与0度页同区域裁出逐像素同一张图(
    tmp_path: Path, rotation: int, region: tuple[float, float, float, float]
) -> None:
    """方形页（100×100）：可见内容一样 → 裁图连字节都相等。"""
    square = (100.0, 100.0)
    base = _render(tmp_path / "r0.pdf", rotation=0, region=region, page_size=square)
    rotated = _render(tmp_path / f"r{rotation}.pdf", rotation=rotation, region=region, page_size=square)

    assert rotated.ink_pixels() > 0, "region 里得有墨，否则这条断言证明不了什么"
    assert (rotated.width, rotated.height) == (base.width, base.height), "方形页裁图尺寸必须相同"
    assert rotated.samples == base.samples, "同一可见 region 的裁图必须逐像素相同"


@pytest.mark.parametrize("rotation", [90, 270])
def test_非方形页旋转后裁图落在可见帧比例上(tmp_path: Path, rotation: int) -> None:
    """200×100 页：``/Rotate=90`` 裁图应是 100×200，且墨迹按可见帧比例落在同一处。

    这条挡的是「按未旋转的 ``/MediaBox`` 算 clip」——那样裁出来的图会把图案切掉或整块落空。
    """
    region = (0.0, 0.0, 1.0, 1.0)
    base = _render(tmp_path / "r0.pdf", rotation=0, region=region)
    rotated = _render(tmp_path / f"r{rotation}.pdf", rotation=rotation, region=region)

    assert (base.width, base.height) == (200, 100)
    assert (rotated.width, rotated.height) == (100, 200), "裁图尺寸跟可见帧（宽高互换），不跟 /MediaBox"
    assert rotated.ink_pixels() > 0
    for got, want in zip(rotated.normalized_ink_bbox(), base.normalized_ink_bbox(), strict=True):
        assert abs(got - want) <= 0.02, "墨迹的可见帧相对位置必须一致（±2% 页宽内）"


# ── ② 帧：整页 region 恒等于 page.rect ───────────────────────────


@pytest.mark.parametrize(
    ("rotation", "expected_size"), [(0, (200.0, 100.0)), (90, (100.0, 200.0)), (180, (200.0, 100.0)), (270, (100.0, 200.0))]
)
def test_整页区域等于可见帧矩形(tmp_path: Path, rotation: int, expected_size: tuple[float, float]) -> None:
    """``region=(0,0,1,1)`` 的 clip 就是 ``page.rect``；90/270 时宽高互换。"""
    with fitz.open(_pdf(tmp_path / f"r{rotation}.pdf", rotation=rotation)) as document:
        page = document.load_page(0)

        clip = clip_rect_for_page(page, (0.0, 0.0, 1.0, 1.0))

        assert clip == page.rect
        assert (clip.width, clip.height) == expected_size, "裁图帧跟 /Rotate 后的可见帧，不跟未旋转 /MediaBox"


# ── ③ round-trip：region → clip → region ────────────────────────


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_区域与裁图矩形互为逆变换(tmp_path: Path, rotation: int) -> None:
    """裁图矩形按可见帧归一化回去必须回到原 region（误差 < 1e-6）。"""
    with fitz.open(_pdf(tmp_path / f"r{rotation}.pdf", rotation=rotation)) as document:
        page = document.load_page(0)
        frame = page.rect
        for region in ((0.0, 0.0, 1.0, 1.0), (0.125, 0.25, 0.875, 0.75), (0.4, 0.0, 0.5, 1.0)):
            clip = clip_rect_for_page(page, region)
            back = (
                (clip.x0 - frame.x0) / frame.width,
                (clip.y0 - frame.y0) / frame.height,
                (clip.x1 - frame.x0) / frame.width,
                (clip.y1 - frame.y0) / frame.height,
            )
            for got, want in zip(back, region, strict=True):
                assert abs(got - want) < 1e-6, f"{rotation}° {region} round-trip 偏差 {abs(got - want)}"


# ── ④ 回归锁：§0 的「derotation 修法」会漏裁 ────────────────────


def test_按derotation换算的矩形反而裁不到墨(tmp_path: Path) -> None:
    """只有可见帧左上 1/4 里有墨的 90° 页：正确 clip 裁得到，换回未旋转坐标系的矩形裁不到。

    200×100 页 ``/Rotate=90`` → 可见帧 100×200、左上 1/4 = x 0–50 / y 0–100；
    该矩形按 ``derotation_matrix`` 换过去是 ``(0, 50, 100, 100)``，在可见帧里是**下半** ——
    墨块摆在可见 ``(10, 10)-(30, 40)`` 就落在它外面。
    """
    only_top_left = ((0.10, 0.05, 0.30, 0.20),)  # 可见帧 (10, 10)-(30, 40)
    with fitz.open(_pdf(tmp_path / "r90.pdf", rotation=90, shapes=only_top_left)) as document:
        page = document.load_page(0)
        clip = clip_rect_for_page(page, (0.0, 0.0, 0.5, 0.5))

        good = page.get_pixmap(colorspace=fitz.csGRAY, clip=clip)
        rejected = page.get_pixmap(colorspace=fitz.csGRAY, clip=clip * page.derotation_matrix)

        assert _Crop(good.width, good.height, bytes(good.samples)).ink_pixels() > 0, "可见帧左上 1/4 里就有墨"
        assert _Crop(rejected.width, rejected.height, bytes(rejected.samples)).ink_pixels() == 0, (
            "按 derotation_matrix 换到未旋转坐标系反而裁不到墨 —— 那正是 pipeline.md §0 的错结论"
        )


# ── ⑤ 同源：两个调用点用同一个实现 ─────────────────────────────


def test_两个裁图调用点共用同一实现() -> None:
    """OCR 补救与表格几何兜底必须调同一个纯函数，不许各写一套。"""
    assert ocr_handler.clip_rect_for_page is clip_rect_for_page
    assert table_geometry_pass.clip_rect_for_page is clip_rect_for_page
