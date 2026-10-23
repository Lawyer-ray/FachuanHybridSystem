"""
证据文件存储兼容层。

历史原因：``documents`` 的迁移文件硬引用了
``apps.documents.models.evidence_storage.EvidenceFileStorage`` 与
``...evidence_file_storage``，因此本模块必须保留这些名字。

实际实现统一来自 ``apps.evidence.models.evidence_storage``，本模块只做继承与再导出，
不再维护第二套 location/base_url 逻辑（否则两处容易漂移，历史上曾导致
``/media/evidence/evidence/...`` 双前缀）。
"""

from __future__ import annotations

from apps.evidence.models.evidence_storage import EvidenceFileStorage as _BaseEvidenceFileStorage
from apps.evidence.models.evidence_storage import evidence_file_storage, get_evidence_storage

__all__ = ["EvidenceFileStorage", "evidence_file_storage", "get_evidence_storage"]


class EvidenceFileStorage(_BaseEvidenceFileStorage):
    """迁移兼容类：行为完全继承 evidence 模块的存储实现。"""
