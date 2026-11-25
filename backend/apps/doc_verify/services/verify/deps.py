"""跨 lane 依赖的唯一入口：比对引擎（lane A）与入站件提取（lane B）。

## 为什么必须在函数体内 import

两条依赖线与本层并行开发，模块此刻可能还不在树上。模块级 import 会把
「对方缺席」升级成「整个 `services.verify` 包 import 失败」——连不碰比对的
单测都会挂，而真正的缺口反而被一堆 ImportError 噪声盖住。

## 为什么这里不写兜底

缺模块就让它 ImportError。把「比对引擎不在」降级成一份空报告，等于对律师说
「没发现差异」——这正是本功能最危险的失败模式。宁可 500，不能假绿。

## 测试怎么替换

单测 monkeypatch 本模块的同名属性（`deps.compare_documents` /
`deps.extract_document`）。因此调用点一律写 `deps.xxx(...)`，
**不要** `from .deps import xxx`——那样替换不生效。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def compare_documents(baseline: Any, inbound: Any, *, tier: int = 0) -> Any:
    """出站基线 × 入站件 → `domain.contracts.Report`（lane A：`domain.compare`）。"""
    from apps.doc_verify.domain.compare import compare_documents as run_compare

    return run_compare(baseline, inbound, tier=tier)


def extract_document(data: bytes, file_name: str = "") -> Any:
    """回传件字节 → `domain.contracts.Inbound`（lane B：`services.anchor.capture`）。"""
    from apps.doc_verify.services.anchor.capture import extract_document as run_extract

    return run_extract(data, file_name)


def fill_text_with_ocr(
    *,
    data: bytes,
    inbound: Any,
    page_budget: int | None = None,
    hint_pages: Sequence[int] = (),
) -> Any:
    """入站件字节 + 已提取的入站件 → `OcrFillResult`（lane B：`services.anchor.ocr_fill`）。

    `page_budget=None` 一律原样往下传：**默认全量**，上限口径只存在于 ocr_fill 一处
    （在这里再写一个数字，就是给「两份口径迟早会漂」留门）。
    """
    from apps.doc_verify.services.anchor.ocr_fill import fill_text_with_ocr as run

    return run(
        data,
        page_count=inbound.page_count,
        existing_text=inbound.text,
        page_budget=page_budget,
        hint_pages=hint_pages,
    )
