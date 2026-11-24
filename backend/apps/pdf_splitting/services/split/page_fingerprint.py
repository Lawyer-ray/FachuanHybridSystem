"""页级指纹：把一页 PDF 压成「版式签名」，用于识别重复页。

## 为什么需要

立案材料几乎总是一式三份：起诉状印三份、送达地址确认书印三份。40 页扫描件里
常常有 25 页是重复页。而取字（OCR）是本流水线最贵的一步——真实 40 页扫描件实测
本机 OCR 取字：fast 档 97s、balanced 档 418s。先把重复页认出来，只 OCR 代表作，
其余页直接继承文字，可以把这一步砍掉一大半。

## 口径（不是拍脑袋，是实测定的）

2026-11-24 用一份真实 40 页立案材料扫描件（6 份文书，其中 3 份回传了 3 份）测：

    逐页二值化 → 100dpi → 8×8 像素块墨占比 → 平均绝对差

    真副本：多页 0.008~0.024，单页 0.0243
    不同文书：≥0.044

为什么不是低分辨率灰度均值：36dpi/16×16 与 36dpi/24×24 在这批样本上**排序是反的**
（真副本 0.003–0.012、不同文书 0.008–0.017，完全重叠）——密排中文在粗网格上同构，
而平均灰度差被纸张亮度主导。二值化去掉纸底亮度，细粒度块才留得住版式。

## 与「案件卷宗侧副本识别」的关系

案件侧（`apps/cases/services/material/scan_archive_naming.py`）也有一套同样的阈值，
那边负责「落盘时把副本分到 `其余副本/` 目录」。两处独立：流水线不能 import cases
（会反向依赖业务 app），而且它们的失败后果不同——这里判错只是 OCR 省不掉或
文字串页（有 review_flag 兜底），那里判错会写错目录。阈值同源同理由，各自持有。
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pymupdf

#: 渲染分辨率：100dpi 下 8px 块 ≈ 2mm，一个汉字约占 2×2 块
FINGERPRINT_DPI = 100
#: 块边长（像素）
FINGERPRINT_POOL = 8
#: 两页判为「同一页」的最大平均绝对差（实测：真副本 ≤0.024，不同文书 ≥0.044）
SAME_PAGE_MAX_DISTANCE = 0.03


def page_signature(page: pymupdf.Page) -> list[float]:
    """单页指纹：100dpi 灰度 → 逐页二值化 → 8×8 块墨占比（行优先展平）。

    用 numpy 而非逐像素 Python 循环：实测 40 页从 2.9s 降到 0.8s，结果逐位相同
    （同样的阈值与块均值，只是把两重循环换成 reshape+mean）。
    """
    pixmap = page.get_pixmap(dpi=FINGERPRINT_DPI, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    low, high = int(gray.min()), int(gray.max())
    threshold = low + 0.5 * (high - low)
    ink = (gray <= threshold).astype(np.float32)
    rows, cols = ink.shape[0] // FINGERPRINT_POOL, ink.shape[1] // FINGERPRINT_POOL
    if rows == 0 or cols == 0:
        return []
    trimmed = ink[: rows * FINGERPRINT_POOL, : cols * FINGERPRINT_POOL]
    blocks = trimmed.reshape(rows, FINGERPRINT_POOL, cols, FINGERPRINT_POOL).mean(axis=(1, 3))
    return [float(value) for value in blocks.ravel()]


def signature_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """两份指纹的平均绝对差；长度不同视为完全不同（1.0）。"""
    if not left or not right or len(left) != len(right):
        return 1.0
    return float(np.abs(np.asarray(left, dtype=np.float32) - np.asarray(right, dtype=np.float32)).mean())


def find_duplicate_pages(
    signatures: Mapping[int, Sequence[float]],
    *,
    max_distance: float = SAME_PAGE_MAX_DISTANCE,
) -> dict[int, int]:
    """找出内容相同的页，返回 `{重复页号: 代表作页号}`。

    键是调用方给的页号（1 起），组内**首个出现的页当代表作**，保持输入顺序稳定。
    只认真副本（≤max_distance），宁漏不错：漏判只是多 OCR 一页，误判会把两页
    不同内容的文字合成一份。
    """
    representatives: list[tuple[int, Sequence[float]]] = []
    duplicates: dict[int, int] = {}
    for page_no, signature in signatures.items():
        for rep_no, rep_signature in representatives:
            if signature_distance(signature, rep_signature) <= max_distance:
                duplicates[page_no] = rep_no
                break
        else:
            representatives.append((page_no, signature))
    return duplicates
