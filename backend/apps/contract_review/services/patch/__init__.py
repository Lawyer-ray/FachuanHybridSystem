"""写 patch 的草案区：收集（不落盘）→ 冲突检测 → 单点应用。

三个文件各有唯一职责，别互相塞：

- `models.py`：`ContractWritePatch` 表（字段口径来自冻结契约 `WritePatch`）；
- `conflict.py`：纯函数，同一 subpath 内的区间相交 → `PatchConflict`；
- `service.py`：`collect_patch` / `apply_patches`（落盘只有这里一处）。
"""

from __future__ import annotations

from .conflict import detect_conflicts, patch_span
from .models import ContractWritePatch, PatchOwnerKind, PatchStatus
from .service import apply_patches, collect_patch, docx_full_text, to_write_patch

__all__ = [
    "ContractWritePatch",
    "PatchOwnerKind",
    "PatchStatus",
    "apply_patches",
    "collect_patch",
    "detect_conflicts",
    "docx_full_text",
    "patch_span",
    "to_write_patch",
]
