"""证据文件存储（兼容再导出）。

历史上这里有一份独立的 ``EvidenceFileStorage`` 实现，与
``apps.evidence.models.evidence_storage`` 的同名类行为不一致
（括号处理、basename 处理不同，且缺少 ``deconstruct`` 导致本机路径可能写入迁移）。

现统一为单一实现：本模块只做再导出，保持既有 import 路径可用。
请勿在此重新定义类。
"""

from __future__ import annotations

from apps.evidence.models.evidence_storage import EvidenceFileStorage, evidence_file_storage, get_evidence_storage

__all__ = ["EvidenceFileStorage", "evidence_file_storage", "get_evidence_storage"]
