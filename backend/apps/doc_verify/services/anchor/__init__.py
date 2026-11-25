"""基线捕获（IO 层）：字节流 → 基线形状 → 落库。

三个公开入口：

- :func:`extract_document` 只读：页数 / 逐页指纹 / 文本层（基线侧永不 OCR）；
- :func:`capture_baseline` 组装内存基线（含字节 SHA-256）；
- :func:`create_artifact` 落库，同幂等键只留一行、不覆盖既有基线。

默认掩膜见 :func:`default_masks`（高风险四类的文末签署区）。
"""

from __future__ import annotations

from apps.doc_verify.services.anchor.area_mask import default_masks
from apps.doc_verify.services.anchor.capture import capture_baseline
from apps.doc_verify.services.anchor.extract import extract_document, sha256_hex
from apps.doc_verify.services.anchor.persist import create_artifact

__all__ = [
    "capture_baseline",
    "create_artifact",
    "default_masks",
    "extract_document",
    "sha256_hex",
]
