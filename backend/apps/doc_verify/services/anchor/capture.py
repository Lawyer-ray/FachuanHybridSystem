"""冻结出站件基线：字节流 → :class:`Baseline`。

锚在「出站那一刻」而不是「最新定稿」，是因为客户只会按收到的纸改：
律师后来出了 V4，客户回传的是按 V3 改的件，拿 V4 当基线会全盘误报。

本模块只做组装：页数 / 逐页指纹 / 文本层全部来自 :func:`extract_document`，
掩膜由调用方给（默认值见 :mod:`apps.doc_verify.services.anchor.area_mask`）。
**不自动补默认掩膜**：静默生效的策略最难在被质疑时解释清楚，
「这份基线掩掉了哪几行」必须能一字不差地答出来。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from apps.doc_verify.domain.contracts import Baseline
from apps.doc_verify.services.anchor.extract import extract_document, sha256_hex

logger = logging.getLogger(__name__)


def capture_baseline(
    *,
    data: bytes,
    file_name: str,
    doc_type: str,
    version: str = "",
    masks: Sequence[Mapping[str, Any]] = (),
) -> Baseline:
    """把一份出站字节流冻结成 :class:`Baseline`（内存形状，落库见 ``persist``）。

    出站件缺少文书名 / 字节为空 / 已知格式解析失败都抛 ``ValueError``：
    一条「什么都没冻住」的基线比没有基线更糟——它会让后来的核对报告说
    「未发现差异」，而那张报告底下没有任何可比的东西。
    """
    normalized_doc_type = str(doc_type or "").strip()
    if not normalized_doc_type:
        raise ValueError(f"出站件缺少文书名（doc_type），无法捕获基线：文件={file_name or '未命名'}")

    inbound = extract_document(data, file_name)
    baseline = Baseline(
        doc_type=normalized_doc_type,
        version=str(version or ""),
        # 幂等键就是它：从字节现算，不接受调用方传入
        sha256=sha256_hex(data),
        page_count=inbound.page_count,
        page_signatures=inbound.page_signatures,
        text=inbound.text,
        masks=tuple(dict(mask) for mask in masks),
    )
    logger.info(
        "基线已冻结: doc_type=%s version=%s 文件=%s sha=%s 页数=%d 指纹页数=%d 正文字数=%d 掩膜=%d",
        baseline.doc_type,
        baseline.version or "-",
        file_name or "未命名",
        baseline.sha256[:12],
        baseline.page_count,
        len(baseline.page_signatures),
        len(baseline.text),
        len(baseline.masks),
    )
    return baseline
